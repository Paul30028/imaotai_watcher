from datetime import datetime
from pydantic import BaseModel


# ── Auth ──────────────────────────────────────────────
class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: int
    username: str
    role: str
    created_at: datetime

    class Config:
        from_attributes = True


# ── Account ───────────────────────────────────────────
class AccountCreate(BaseModel):
    phone: str
    province_name: str
    city_name: str
    lat: str
    lng: str
    shop_type: int = 1
    random_minute: bool = True
    fixed_minute: int | None = None


class AccountUpdate(BaseModel):
    province_name: str | None = None
    city_name: str | None = None
    lat: str | None = None
    lng: str | None = None
    shop_type: int | None = None
    random_minute: bool | None = None
    fixed_minute: int | None = None
    status: str | None = None


class AccountOut(BaseModel):
    id: int
    phone: str
    device_id: str
    user_id: str | None
    province_name: str
    city_name: str
    lat: str
    lng: str
    shop_type: int
    random_minute: bool
    fixed_minute: int | None
    target_minute: int | None
    status: str
    last_login: datetime | None
    created_at: datetime

    class Config:
        from_attributes = True


class VerifyLoginRequest(BaseModel):
    verify_code: str


# ── Product ───────────────────────────────────────────
class ProductCreate(BaseModel):
    account_id: int | None = None
    item_code: str
    item_name: str


class ProductUpdate(BaseModel):
    enabled: bool | None = None
    item_name: str | None = None


class ProductOut(BaseModel):
    id: int
    account_id: int | None
    item_code: str
    item_name: str
    enabled: bool

    class Config:
        from_attributes = True


class TodayItemOut(BaseModel):
    """当日在售商品，用于商品配置页下拉选择，而不是让用户手填 item_code。"""
    item_id: str
    item_code: str | None = None
    title: str | None = None


# ── Logs ──────────────────────────────────────────────
class PurchaseLogOut(BaseModel):
    id: int
    account_id: int
    item_code: str
    item_name: str
    status: str
    message: str | None
    purchased_at: datetime

    class Config:
        from_attributes = True


class LogsResponse(BaseModel):
    total: int
    items: list[PurchaseLogOut]


class StatsResponse(BaseModel):
    total_accounts: int
    today_success: int
    today_fail: int
    trend: list[dict]  # [{date, success, fail}]


# ── Scheduler ─────────────────────────────────────────
class SchedulerStatus(BaseModel):
    alive: bool
    schedule_time: str
    last_run_at: datetime | None
    next_run_at: datetime | None


class SchedulerConfig(BaseModel):
    schedule_time: str  # "HH:MM"


# ── Settings ──────────────────────────────────────────
class NotifySettings(BaseModel):
    send_key: str


class MessageResponse(BaseModel):
    message: str
