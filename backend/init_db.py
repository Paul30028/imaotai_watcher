"""Run once to create tables and seed admin user."""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from database import engine, Base, SessionLocal
from models.models import User, SchedulerState
from passlib.context import CryptContext
from config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def init():
    Base.metadata.create_all(bind=engine)
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
