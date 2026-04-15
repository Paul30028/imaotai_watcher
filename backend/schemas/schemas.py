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
    city_code: str


class AccountUpdate(BaseModel):
    city_code: str | None = None
    status: str | None = None


class AccountOut(BaseModel):
    id: int
    phone: str
    device_id: str
    city_code: str
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
