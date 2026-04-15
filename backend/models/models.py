from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Text, ForeignKey, BigInteger
)
from sqlalchemy.orm import relationship
from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    password_hash = Column(String(128), nullable=False)
    role = Column(String(16), nullable=False, default="viewer")  # admin / viewer
    created_at = Column(DateTime, default=datetime.utcnow)


class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, index=True)
    phone = Column(String(16), unique=True, nullable=False, index=True)
    token = Column(Text, nullable=True)
    device_id = Column(String(64), nullable=False)
    city_code = Column(String(16), nullable=False)
    status = Column(String(16), nullable=False, default="active")  # active / expired
    last_login = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    products = relationship("Product", back_populates="account", foreign_keys="Product.account_id")
    logs = relationship("PurchaseLog", back_populates="account")


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True, index=True)
    item_code = Column(String(32), nullable=False)
    item_name = Column(String(128), nullable=False)
    enabled = Column(Boolean, default=True)

    account = relationship("Account", back_populates="products", foreign_keys=[account_id])


class PurchaseLog(Base):
    __tablename__ = "purchase_logs"

    id = Column(BigInteger, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False, index=True)
    item_code = Column(String(32), nullable=False)
    item_name = Column(String(128), nullable=False)
    status = Column(String(16), nullable=False)  # success / fail / retry
    message = Column(Text, nullable=True)
    purchased_at = Column(DateTime, default=datetime.utcnow, index=True)

    account = relationship("Account", back_populates="logs")


class SchedulerState(Base):
    __tablename__ = "scheduler_state"

    id = Column(Integer, primary_key=True, default=1)
    schedule_time = Column(String(8), nullable=False, default="09:00")
    last_run_at = Column(DateTime, nullable=True)
    next_run_at = Column(DateTime, nullable=True)


class AppSetting(Base):
    __tablename__ = "app_settings"

    key = Column(String(64), primary_key=True)
    value = Column(Text, nullable=True)
