import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from config import settings

_is_sqlite = settings.database_url.startswith("sqlite:///")

if _is_sqlite:
    # sqlite:///./data/imaotai.db -> ./data/imaotai.db ; make sure the
    # containing directory exists before sqlite3 tries to create the file.
    db_path = settings.database_url.removeprefix("sqlite:///")
    if db_path not in (":memory:", ""):
        db_dir = os.path.dirname(db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

engine = create_engine(
    settings.database_url,
    # SQLite connections are per-thread by default; the app talks to the
    # DB from the API's request threads and the in-process scheduler
    # thread, so this needs to be relaxed (SQLAlchemy's own session
    # handling still keeps access serialized safely per Session).
    connect_args={"check_same_thread": False} if _is_sqlite else {},
    pool_pre_ping=True,
    echo=False,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass
