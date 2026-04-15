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
