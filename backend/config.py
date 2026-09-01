from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # JWT
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24  # 24h

    # Admin bootstrap
    admin_username: str = "admin"
    admin_password: str

    # SQLite file path. A single-file embedded database is enough for a
    # personal/self-hosted single-instance app -- no separate DB server to
    # run or configure. Override with a full SQLAlchemy URL if you really
    # want something else (e.g. "postgresql+psycopg://...").
    database_url: str = "sqlite:///./data/imaotai.db"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
