import sys
import os

# Set required env vars before any app module is imported
os.environ.setdefault("jwt_secret", "test_secret")
os.environ.setdefault("admin_password", "test_password")
os.environ.setdefault("mysql_host", "localhost")
os.environ.setdefault("mysql_database", "test_db")
os.environ.setdefault("mysql_user", "test_user")
os.environ.setdefault("mysql_password", "test_pass")
os.environ.setdefault("redis_host", "localhost")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from passlib.context import CryptContext

from database import Base
from api.deps import get_db
from models.models import User
from main import app

SQLALCHEMY_TEST_URL = "sqlite:///./test.db"
engine_test = create_engine(SQLALCHEMY_TEST_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine_test)
pwd_context_test = CryptContext(schemes=["bcrypt"], deprecated="auto")


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine_test)
    yield
    Base.metadata.drop_all(bind=engine_test)


@pytest.fixture
def db():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db):
    def override_get_db():
        try:
            yield db
        finally:
            pass
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def admin_user(db):
    user = User(
        username="testadmin",
        password_hash=pwd_context_test.hash("testpass"),
        role="admin",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def admin_token(client, admin_user):
    resp = client.post("/api/auth/login", json={"username": "testadmin", "password": "testpass"})
    return resp.json()["access_token"]
