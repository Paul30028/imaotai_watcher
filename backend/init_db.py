"""Run once (also on every app startup) to create tables, seed the admin
user, and apply lightweight column migrations for existing databases.

There's no Alembic in this project; for a SQLite-backed single-user app
this small an `ADD COLUMN` pass is enough and avoids pulling in a whole
migration framework for a handful of additive columns. Uses SQLAlchemy's
inspector rather than raw INFORMATION_SCHEMA queries so it isn't tied to
one specific database engine.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import inspect, text
from database import engine, Base, SessionLocal
from models.models import User, SchedulerState
from passlib.context import CryptContext
from config import settings
from utils.logger import get_logger

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
logger = get_logger(__name__)

# columns introduced when the imaotai API layer was corrected to match the
# real i茅台 backend (see backend/core/imaotai_api.py)
_ACCOUNT_MIGRATIONS = [
    ("cookie", "TEXT"),
    ("province_name", "VARCHAR(32) NOT NULL DEFAULT ''"),
    ("city_name", "VARCHAR(32) NOT NULL DEFAULT ''"),
    ("lat", "VARCHAR(32) NOT NULL DEFAULT ''"),
    ("lng", "VARCHAR(32) NOT NULL DEFAULT ''"),
    ("shop_type", "INTEGER NOT NULL DEFAULT 1"),
    ("random_minute", "BOOLEAN NOT NULL DEFAULT 1"),
    ("fixed_minute", "INTEGER"),
    ("target_minute", "INTEGER"),
    ("target_minute_date", "VARCHAR(10)"),
]
_SCHEDULER_STATE_MIGRATIONS = [
    ("results_query_time", "VARCHAR(8) NOT NULL DEFAULT '18:05'"),
    ("refresh_times", "VARCHAR(64) NOT NULL DEFAULT '07:10,07:55,08:10,08:55'"),
]


def _add_missing_columns(conn, table: str, columns: list[tuple[str, str]]) -> None:
    existing = {col["name"] for col in inspect(conn).get_columns(table)}
    for name, ddl in columns:
        if name in existing:
            continue
        logger.info(f"迁移: {table} 增加列 {name}")
        conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))


def migrate_schema() -> None:
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as conn:
        if "accounts" in existing_tables:
            _add_missing_columns(conn, "accounts", _ACCOUNT_MIGRATIONS)
        if "scheduler_state" in existing_tables:
            _add_missing_columns(conn, "scheduler_state", _SCHEDULER_STATE_MIGRATIONS)
        # city_code predates the real-API rewrite and is no longer read;
        # left in place (not dropped) so a downgrade never loses data.


def init():
    Base.metadata.create_all(bind=engine)
    migrate_schema()
    db = SessionLocal()
    try:
        if not db.query(User).filter(User.username == settings.admin_username).first():
            admin = User(
                username=settings.admin_username,
                password_hash=pwd_context.hash(settings.admin_password),
                role="admin",
            )
            db.add(admin)
        if not db.query(SchedulerState).filter(SchedulerState.id == 1).first():
            db.add(SchedulerState(id=1, schedule_time="09:00"))
        db.commit()
        print("DB initialized.")
    finally:
        db.close()


if __name__ == "__main__":
    init()
