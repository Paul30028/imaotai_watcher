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
    cookie = Column(Text, nullable=True)
    user_id = Column(String(64), nullable=True)   # i茅台 userId，签名/下单需要
    device_id = Column(String(64), nullable=False)

    # 真实接口按"省份+城市+经纬度"选门店，不是行政区划代码
    province_name = Column(String(32), nullable=False, default="")
    city_name = Column(String(32), nullable=False, default="")
    lat = Column(String(32), nullable=False, default="")
    lng = Column(String(32), nullable=False, default="")
    # 1: 预约本市出货量最大的门店   2: 预约位置最近的门店
    shop_type = Column(Integer, nullable=False, default=1)

    # 每日 9 点申购窗口内，该账号被随机/固定分配到的分钟(1-59)，用于错峰申购
    random_minute = Column(Boolean, nullable=False, default=True)
    fixed_minute = Column(Integer, nullable=True)
    target_minute = Column(Integer, nullable=True)       # 当日实际生效的分钟
    target_minute_date = Column(String(10), nullable=True)  # 分配对应的日期 YYYY-MM-DD，跨天失效

    status = Column(String(16), nullable=False, default="active")  # active / expired
    last_login = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    products = relationship("Product", back_populates="account", foreign_keys="Product.account_id")
    logs = relationship("PurchaseLog", back_populates="account")


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True, index=True)
    item_code = Column(String(32), nullable=False)  # 当日在售商品的 itemId
    item_name = Column(String(128), nullable=False)
    enabled = Column(Boolean, default=True)

    account = relationship("Account", back_populates="products", foreign_keys=[account_id])


class PurchaseLog(Base):
    __tablename__ = "purchase_logs"

    id = Column(BigInteger, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False, index=True)
    item_code = Column(String(32), nullable=False)
    item_name = Column(String(128), nullable=False)
    status = Column(String(16), nullable=False)  # success / fail / retry / confirmed
    message = Column(Text, nullable=True)
    purchased_at = Column(DateTime, default=datetime.utcnow, index=True)

    account = relationship("Account", back_populates="logs")


class SchedulerState(Base):
    __tablename__ = "scheduler_state"

    id = Column(Integer, primary_key=True, default=1)
    # 仅取 HH 作为申购窗口小时（i茅台固定 9:00-9:59 开放），分钟部分不再使用，
    # 各账号在这一小时内按 random_minute/fixed_minute 错峰触发
    schedule_time = Column(String(8), nullable=False, default="09:00")
    results_query_time = Column(String(8), nullable=False, default="18:05")
    refresh_times = Column(String(64), nullable=False, default="07:10,07:55,08:10,08:55")
    last_run_at = Column(DateTime, nullable=True)
    next_run_at = Column(DateTime, nullable=True)


class AppSetting(Base):
    __tablename__ = "app_settings"

    key = Column(String(64), primary_key=True)
    value = Column(Text, nullable=True)
