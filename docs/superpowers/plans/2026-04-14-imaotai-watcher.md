# imaotai_watcher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建 i茅台自动申购系统，含 FastAPI 后端、APScheduler 独立调度器、React 前端和 Docker 部署。

**Architecture:** API 服务与调度器独立容器，共享外部 MySQL + Redis 实例。调度器通过 Redis BRPOP 接收手动触发，通过 Redis key TTL 上报心跳。

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy 2, pymysql, redis-py, APScheduler, python-jose, httpx, React 18, TypeScript, Vite, Ant Design 5, Zustand, Nginx, Docker Compose

---

## File Map

```
imaotai_watcher/
├── backend/
│   ├── config.py                   # Pydantic Settings，从 .env 读所有配置
│   ├── database.py                 # SQLAlchemy engine + SessionLocal
│   ├── redis_client.py             # redis-py 单例
│   ├── main.py                     # FastAPI app 工厂，注册所有 router
│   ├── models/
│   │   └── models.py               # ORM: User, Account, Product, PurchaseLog, SchedulerState, AppSetting
│   ├── schemas/
│   │   └── schemas.py              # Pydantic 请求/响应 schema
│   ├── api/
│   │   ├── deps.py                 # 公共依赖：get_db, get_current_user, require_admin
│   │   ├── auth.py                 # POST /auth/login, /auth/refresh
│   │   ├── accounts.py             # 账号 CRUD + verify + login
│   │   ├── products.py             # 商品 CRUD
│   │   ├── logs.py                 # 日志列表 + stats（Redis 缓存）
│   │   ├── scheduler_router.py     # 调度器 status/trigger/config
│   │   └── settings.py             # notify CRUD + test
│   ├── core/
│   │   ├── imaotai_api.py          # i茅台 HTTP 客户端（签名、重试）
│   │   ├── purchase.py             # 申购编排逻辑（多账号并发）
│   │   └── notifier.py             # Server酱推送
│   ├── scheduler/
│   │   └── main.py                 # APScheduler 独立进程 + Redis BRPOP 主循环
│   ├── utils/
│   │   ├── signature.py            # MD5 签名
│   │   ├── time_sync.py            # 获取 NTP 时间
│   │   └── logger.py               # logging 配置
│   ├── tests/
│   │   ├── conftest.py             # pytest fixtures
│   │   ├── test_signature.py
│   │   ├── test_notifier.py
│   │   ├── test_purchase.py
│   │   └── test_api_auth.py
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── api/
│   │   │   ├── client.ts           # axios 实例 + 拦截器
│   │   │   ├── auth.ts
│   │   │   ├── accounts.ts
│   │   │   ├── products.ts
│   │   │   ├── logs.ts
│   │   │   ├── scheduler.ts
│   │   │   └── settings.ts
│   │   ├── store/
│   │   │   └── authStore.ts        # Zustand：JWT + 用户信息
│   │   ├── components/
│   │   │   ├── AppLayout.tsx       # 侧边栏导航 + 顶栏
│   │   │   └── PrivateRoute.tsx    # 未登录跳转
│   │   ├── pages/
│   │   │   ├── Login.tsx
│   │   │   ├── Dashboard.tsx
│   │   │   ├── Accounts.tsx
│   │   │   ├── Products.tsx
│   │   │   ├── Logs.tsx
│   │   │   └── Settings.tsx
│   │   ├── App.tsx
│   │   └── main.tsx
│   ├── index.html
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── package.json
│   └── Dockerfile
├── nginx/
│   └── nginx.conf
├── docker-compose.yml
└── .env.example
```

---

## Phase 1: Backend Foundation

### Task 1: Project scaffold + config + requirements

**Files:**
- Create: `backend/config.py`
- Create: `backend/requirements.txt`
- Create: `backend/utils/logger.py`
- Create: `.env.example`

- [ ] **Step 1: 创建目录结构**

```bash
cd imaotai_watcher
mkdir -p backend/{api,core,models,schemas,scheduler,utils,tests}
touch backend/__init__.py backend/api/__init__.py backend/core/__init__.py
touch backend/models/__init__.py backend/schemas/__init__.py
touch backend/scheduler/__init__.py backend/utils/__init__.py backend/tests/__init__.py
```

- [ ] **Step 2: 创建 `backend/requirements.txt`**

```
fastapi==0.111.0
uvicorn[standard]==0.29.0
sqlalchemy==2.0.30
pymysql==1.1.1
cryptography==42.0.8
redis==5.0.4
pydantic==2.7.1
pydantic-settings==2.3.0
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
httpx==0.27.0
apscheduler==3.10.4
python-multipart==0.0.9
pytest==8.2.0
pytest-asyncio==0.23.7
httpx==0.27.0
```

- [ ] **Step 3: 创建 `backend/config.py`**

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # JWT
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24  # 24h

    # Admin bootstrap
    admin_username: str = "admin"
    admin_password: str

    # MySQL
    mysql_host: str
    mysql_port: int = 3306
    mysql_database: str
    mysql_user: str
    mysql_password: str

    # Redis
    redis_host: str
    redis_port: int = 6379
    redis_password: str = ""
    redis_db: int = 0

    @property
    def mysql_url(self) -> str:
        return (
            f"mysql+pymysql://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"
            "?charset=utf8mb4"
        )

    @property
    def redis_url(self) -> str:
        if self.redis_password:
            return f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
```

- [ ] **Step 4: 创建 `backend/utils/logger.py`**

```python
import logging
import sys


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger
```

- [ ] **Step 5: 创建 `.env.example`**

```
JWT_SECRET=change_me_random_string_32chars
ADMIN_USERNAME=admin
ADMIN_PASSWORD=change_me

MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_DATABASE=imaotai
MYSQL_USER=imaotai
MYSQL_PASSWORD=change_me

REDIS_HOST=127.0.0.1
REDIS_PORT=6379
REDIS_PASSWORD=
REDIS_DB=0
```

- [ ] **Step 6: Commit**

```bash
git add backend/ .env.example
git commit -m "feat: backend project scaffold + config"
```

---

### Task 2: Database models

**Files:**
- Create: `backend/database.py`
- Create: `backend/models/models.py`

- [ ] **Step 1: 创建 `backend/database.py`**

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from config import settings

engine = create_engine(
    settings.mysql_url,
    pool_pre_ping=True,
    pool_recycle=3600,
    echo=False,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass
```

- [ ] **Step 2: 创建 `backend/models/models.py`**

```python
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
```

- [ ] **Step 3: 编写初始化表 + 默认数据的脚本 `backend/init_db.py`**

```python
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
```

- [ ] **Step 4: Commit**

```bash
git add backend/database.py backend/models/ backend/init_db.py
git commit -m "feat: database models + init script"
```

---

### Task 3: Redis client + signing utils

**Files:**
- Create: `backend/redis_client.py`
- Create: `backend/utils/signature.py`
- Create: `backend/utils/time_sync.py`
- Create: `backend/tests/test_signature.py`

- [ ] **Step 1: 写签名算法测试 `backend/tests/test_signature.py`**

```python
from utils.signature import generate_sign, generate_device_id


def test_generate_sign_is_md5_hex():
    sign = generate_sign("device123", "1700000000")
    assert len(sign) == 32
    assert sign.isalnum()


def test_generate_sign_deterministic():
    s1 = generate_sign("device123", "1700000000")
    s2 = generate_sign("device123", "1700000000")
    assert s1 == s2


def test_generate_sign_differs_with_different_inputs():
    s1 = generate_sign("device123", "1700000000")
    s2 = generate_sign("device456", "1700000000")
    assert s1 != s2


def test_generate_device_id_format():
    device_id = generate_device_id()
    assert len(device_id) == 36  # UUID format with hyphens
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend && python -m pytest tests/test_signature.py -v
# Expected: ERROR - ModuleNotFoundError
```

- [ ] **Step 3: 创建 `backend/utils/signature.py`**

```python
import hashlib
import uuid

# i茅台 APP 签名密钥（公开逆向值）
_APP_SECRET = "2af72f100c356273d46284f6fd1dfc08"


def generate_sign(device_id: str, timestamp: str) -> str:
    """MD5(device_id + timestamp + APP_SECRET)"""
    raw = device_id + timestamp + _APP_SECRET
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def generate_device_id() -> str:
    """生成随机 UUID 作为设备 ID"""
    return str(uuid.uuid4())
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd backend && python -m pytest tests/test_signature.py -v
# Expected: 4 passed
```

- [ ] **Step 5: 创建 `backend/utils/time_sync.py`**

```python
import time


def get_timestamp() -> str:
    """返回当前 Unix 时间戳字符串（秒级）"""
    return str(int(time.time()))
```

- [ ] **Step 6: 创建 `backend/redis_client.py`**

```python
import redis
from config import settings

_client: redis.Redis | None = None


def get_redis() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            password=settings.redis_password or None,
            db=settings.redis_db,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
    return _client
```

- [ ] **Step 7: Commit**

```bash
git add backend/utils/ backend/redis_client.py backend/tests/test_signature.py
git commit -m "feat: signature utils, time_sync, redis client"
```

---

### Task 4: i茅台 API 客户端

**Files:**
- Create: `backend/core/imaotai_api.py`

i茅台 API 基础 URL：`https://api.moutai519.com.cn`  
公共请求头：`MT-Device-ID`、`MT-Timestamp`、`MT-Sign`、`MT-APP-Version`、`User-Agent`、`MT-Info`

- [ ] **Step 1: 创建 `backend/core/imaotai_api.py`**

```python
import time
import httpx
from utils.signature import generate_sign
from utils.time_sync import get_timestamp
from utils.logger import get_logger

logger = get_logger(__name__)

_BASE_URL = "https://api.moutai519.com.cn"
_APP_VERSION = "1.4.1"
_MT_INFO = "028e7f96f6369cafe1d105579c5b9377"


def _build_headers(device_id: str, token: str | None = None) -> dict:
    ts = get_timestamp()
    headers = {
        "MT-Device-ID": device_id,
        "MT-Timestamp": ts,
        "MT-Sign": generate_sign(device_id, ts),
        "MT-APP-Version": _APP_VERSION,
        "MT-Info": _MT_INFO,
        "User-Agent": "iOS;16.3;Apple;iPhone 15",
        "Content-Type": "application/json",
    }
    if token:
        headers["MT-Token-V3"] = token
    return headers


def _post(path: str, body: dict, device_id: str, token: str | None = None) -> dict:
    url = _BASE_URL + path
    headers = _build_headers(device_id, token)
    with httpx.Client(timeout=10) as client:
        resp = client.post(url, json=body, headers=headers)
        resp.raise_for_status()
        return resp.json()


def _get(path: str, device_id: str, token: str | None = None, params: dict | None = None) -> dict:
    url = _BASE_URL + path
    headers = _build_headers(device_id, token)
    with httpx.Client(timeout=10) as client:
        resp = client.get(url, headers=headers, params=params)
        resp.raise_for_status()
        return resp.json()


def send_verify_code(phone: str, device_id: str) -> dict:
    """发送短信验证码"""
    return _post(
        "/game/outside/user/sendVerifyCode/v2",
        {"mobile": phone},
        device_id,
    )


def login(phone: str, verify_code: str, device_id: str) -> dict:
    """验证码登录，返回 token 等信息"""
    return _post(
        "/game/outside/user/login/v2",
        {"mobile": phone, "verifyCode": verify_code, "deviceId": device_id},
        device_id,
    )


def get_current_session(device_id: str, token: str) -> int:
    """获取当前销售 sessionId"""
    data = _get("/game/outside/mall/sessions/v2", device_id, token)
    # 返回最新 session 的 id
    sessions = data.get("data", {}).get("sessions", [])
    if not sessions:
        raise ValueError("No active sessions found")
    return sessions[0]["sessionId"]


def get_shops(city_code: str, item_code: str, device_id: str, token: str) -> list[dict]:
    """获取指定城市+商品的门店列表"""
    data = _get(
        "/game/outside/mall/shop/list/slim/v4",
        device_id,
        token,
        params={"cityCode": city_code, "itemCode": item_code},
    )
    return data.get("data", {}).get("shopList", [])


def reserve(
    item_code: str,
    session_id: int,
    shop_code: str,
    device_id: str,
    token: str,
) -> dict:
    """提交申购"""
    return _post(
        "/game/outside/user/retailer/appoint/v2",
        {"itemCode": item_code, "sessionId": session_id, "shopCode": shop_code},
        device_id,
        token,
    )
```

- [ ] **Step 2: Commit**

```bash
git add backend/core/imaotai_api.py
git commit -m "feat: i茅台 API client with signing"
```

---

### Task 5: Server酱通知 + 申购核心逻辑

**Files:**
- Create: `backend/core/notifier.py`
- Create: `backend/core/purchase.py`
- Create: `backend/tests/test_notifier.py`
- Create: `backend/tests/test_purchase.py`

- [ ] **Step 1: 写通知测试 `backend/tests/test_notifier.py`**

```python
from unittest.mock import patch, MagicMock
from core.notifier import send_server_chan


def test_send_server_chan_calls_correct_url():
    with patch("httpx.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200)
        send_server_chan("test_key", "测试标题", "测试内容")
        call_args = mock_post.call_args
        assert "test_key" in call_args[0][0]
        assert call_args[1]["data"]["title"] == "测试标题"


def test_send_server_chan_no_key_skips():
    with patch("httpx.post") as mock_post:
        send_server_chan("", "标题", "内容")
        mock_post.assert_not_called()
```

- [ ] **Step 2: 运行确认失败**

```bash
cd backend && python -m pytest tests/test_notifier.py -v
# Expected: ERROR
```

- [ ] **Step 3: 创建 `backend/core/notifier.py`**

```python
import httpx
from utils.logger import get_logger

logger = get_logger(__name__)


def send_server_chan(send_key: str, title: str, content: str) -> None:
    """通过 Server酱 发送微信通知"""
    if not send_key:
        logger.warning("Server酱 SendKey 未配置，跳过通知")
        return
    url = f"https://sctapi.ftqq.com/{send_key}.send"
    try:
        resp = httpx.post(url, data={"title": title, "desp": content}, timeout=10)
        resp.raise_for_status()
        logger.info(f"Server酱 通知发送成功: {title}")
    except Exception as e:
        logger.error(f"Server酱 通知发送失败: {e}")
```

- [ ] **Step 4: 运行确认通过**

```bash
cd backend && python -m pytest tests/test_notifier.py -v
# Expected: 2 passed
```

- [ ] **Step 5: 写申购逻辑测试 `backend/tests/test_purchase.py`**

```python
from unittest.mock import patch, MagicMock
from core.purchase import purchase_for_account


def _make_account():
    acc = MagicMock()
    acc.id = 1
    acc.phone = "13800138000"
    acc.token = "test_token"
    acc.device_id = "test_device"
    acc.city_code = "500100"
    acc.status = "active"
    return acc


def _make_product(item_code="10941", item_name="飞天茅台"):
    p = MagicMock()
    p.item_code = item_code
    p.item_name = item_name
    p.enabled = True
    return p


def test_purchase_success_writes_log():
    account = _make_account()
    products = [_make_product()]
    db = MagicMock()

    with patch("core.purchase.get_current_session", return_value=1), \
         patch("core.purchase.get_shops", return_value=[{"shopCode": "shop001"}]), \
         patch("core.purchase.reserve", return_value={"code": 200, "message": "success"}):
        result = purchase_for_account(account, products, db)

    assert result["success"] == 1
    assert result["fail"] == 0
    db.add.assert_called_once()
    db.commit.assert_called_once()


def test_purchase_fail_retries_3_times():
    account = _make_account()
    products = [_make_product()]
    db = MagicMock()

    with patch("core.purchase.get_current_session", return_value=1), \
         patch("core.purchase.get_shops", return_value=[{"shopCode": "shop001"}]), \
         patch("core.purchase.reserve", side_effect=Exception("API error")), \
         patch("core.purchase.time.sleep"):
        result = purchase_for_account(account, products, db)

    assert result["fail"] == 1


def test_purchase_no_shops_skips_product():
    account = _make_account()
    products = [_make_product()]
    db = MagicMock()

    with patch("core.purchase.get_current_session", return_value=1), \
         patch("core.purchase.get_shops", return_value=[]):
        result = purchase_for_account(account, products, db)

    assert result["fail"] == 1
```

- [ ] **Step 6: 运行确认失败**

```bash
cd backend && python -m pytest tests/test_purchase.py -v
# Expected: ERROR
```

- [ ] **Step 7: 创建 `backend/core/purchase.py`**

```python
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from sqlalchemy.orm import Session
from models.models import Account, Product, PurchaseLog
from core.imaotai_api import get_current_session, get_shops, reserve
from utils.logger import get_logger

logger = get_logger(__name__)

_MAX_RETRIES = 3
_RETRY_INTERVAL = 1  # seconds


def purchase_for_account(account: Account, products: list, db: Session) -> dict:
    """对单个账号执行申购，返回 {success: n, fail: n}"""
    success_count = 0
    fail_count = 0

    try:
        session_id = get_current_session(account.device_id, account.token)
    except Exception as e:
        logger.error(f"[{account.phone}] 获取 session 失败: {e}")
        return {"success": 0, "fail": len(products)}

    for product in products:
        if not product.enabled:
            continue

        status = "fail"
        message = ""

        try:
            shops = get_shops(account.city_code, product.item_code, account.device_id, account.token)
            if not shops:
                message = "该城市无可用门店"
                logger.warning(f"[{account.phone}] {product.item_name}: {message}")
            else:
                shop_code = shops[0]["shopCode"]
                for attempt in range(_MAX_RETRIES):
                    try:
                        result = reserve(product.item_code, session_id, shop_code, account.device_id, account.token)
                        if result.get("code") == 200:
                            status = "success"
                            message = result.get("message", "申购成功")
                            success_count += 1
                            break
                        else:
                            message = result.get("message", "申购失败")
                            logger.warning(f"[{account.phone}] {product.item_name} 第{attempt+1}次失败: {message}")
                    except Exception as e:
                        message = str(e)
                        logger.warning(f"[{account.phone}] {product.item_name} 第{attempt+1}次异常: {e}")
                    if attempt < _MAX_RETRIES - 1:
                        time.sleep(_RETRY_INTERVAL)

        except Exception as e:
            message = str(e)
            logger.error(f"[{account.phone}] {product.item_name} 异常: {e}")

        if status == "fail":
            fail_count += 1

        log = PurchaseLog(
            account_id=account.id,
            item_code=product.item_code,
            item_name=product.item_name,
            status=status,
            message=message,
        )
        db.add(log)
        db.commit()

    return {"success": success_count, "fail": fail_count}


def run_all_purchases(db: Session) -> dict:
    """并发执行所有 active 账号的申购"""
    accounts = db.query(Account).filter(Account.status == "active").all()
    if not accounts:
        logger.info("无 active 账号，跳过申购")
        return {"total_success": 0, "total_fail": 0}

    def get_products_for_account(acc: Account) -> list:
        account_products = (
            db.query(Product)
            .filter(Product.account_id == acc.id, Product.enabled == True)
            .all()
        )
        if account_products:
            return account_products
        # 回退全局默认
        return db.query(Product).filter(Product.account_id == None, Product.enabled == True).all()

    total_success = 0
    total_fail = 0

    with ThreadPoolExecutor(max_workers=min(len(accounts), 5)) as executor:
        futures = {
            executor.submit(purchase_for_account, acc, get_products_for_account(acc), db): acc
            for acc in accounts
        }
        for future in as_completed(futures):
            acc = futures[future]
            try:
                result = future.result()
                total_success += result["success"]
                total_fail += result["fail"]
                logger.info(f"[{acc.phone}] 完成: 成功{result['success']}，失败{result['fail']}")
            except Exception as e:
                logger.error(f"[{acc.phone}] 申购线程异常: {e}")

    return {"total_success": total_success, "total_fail": total_fail}
```

- [ ] **Step 8: 运行全部测试确认通过**

```bash
cd backend && python -m pytest tests/ -v
# Expected: all passed
```

- [ ] **Step 9: Commit**

```bash
git add backend/core/ backend/tests/
git commit -m "feat: notifier + purchase core logic with retry"
```

---

### Task 6: APScheduler 独立调度器进程

**Files:**
- Create: `backend/scheduler/main.py`

- [ ] **Step 1: 创建 `backend/scheduler/main.py`**

```python
"""
独立调度器进程。
- BackgroundScheduler 在后台线程执行定时申购
- 主线程循环更新 Redis 心跳 + BRPOP 等待手动触发
- 接收 'reschedule' 消息时从 DB 读取最新 schedule_time 重新配置 job
"""
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from database import SessionLocal
from models.models import SchedulerState, AppSetting
from core.purchase import run_all_purchases
from core.notifier import send_server_chan
from redis_client import get_redis
from utils.logger import get_logger

logger = get_logger("scheduler")

HEARTBEAT_KEY = "scheduler:heartbeat"
TRIGGER_KEY = "scheduler:trigger"
HEARTBEAT_TTL = 60  # seconds


def get_send_key(db) -> str:
    setting = db.query(AppSetting).filter(AppSetting.key == "notify_send_key").first()
    return setting.value if setting and setting.value else ""


def purchase_job():
    logger.info("=== 开始申购任务 ===")
    db = SessionLocal()
    try:
        result = run_all_purchases(db)

        # 更新 last_run_at
        state = db.query(SchedulerState).filter(SchedulerState.id == 1).first()
        if state:
            from datetime import datetime
            state.last_run_at = datetime.utcnow()
            db.commit()

        # 推送汇总通知
        send_key = get_send_key(db)
        title = f"i茅台申购完成：成功{result['total_success']}，失败{result['total_fail']}"
        content = f"成功：{result['total_success']}\n失败：{result['total_fail']}"
        send_server_chan(send_key, title, content)

        logger.info(f"=== 申购任务结束: {result} ===")
    except Exception as e:
        logger.error(f"申购任务异常: {e}")
    finally:
        db.close()


def get_schedule_time(db) -> tuple[int, int]:
    """从 DB 读取 schedule_time，返回 (hour, minute)"""
    state = db.query(SchedulerState).filter(SchedulerState.id == 1).first()
    t = (state.schedule_time if state else "09:00") or "09:00"
    h, m = t.split(":")
    return int(h), int(m)


def reschedule(scheduler: BackgroundScheduler):
    db = SessionLocal()
    try:
        hour, minute = get_schedule_time(db)
    finally:
        db.close()

    scheduler.remove_all_jobs()
    scheduler.add_job(
        purchase_job,
        CronTrigger(hour=hour, minute=minute),
        id="purchase",
        replace_existing=True,
    )
    logger.info(f"调度器已配置: 每天 {hour:02d}:{minute:02d} 执行")


def main():
    redis = get_redis()
    scheduler = BackgroundScheduler()
    scheduler.start()
    reschedule(scheduler)

    logger.info("调度器进程启动，等待任务...")

    while True:
        # 更新心跳
        redis.setex(HEARTBEAT_KEY, HEARTBEAT_TTL, "1")

        # 阻塞等待 trigger 消息，最多 30s
        result = redis.brpop(TRIGGER_KEY, timeout=30)
        if result:
            _, message = result
            if message == "reschedule":
                logger.info("收到 reschedule 指令，重新配置调度时间")
                reschedule(scheduler)
            else:
                logger.info("收到手动触发指令，立即执行申购")
                purchase_job()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```bash
git add backend/scheduler/main.py
git commit -m "feat: APScheduler independent process with Redis heartbeat and trigger"
```

---

## Phase 2: Backend API

### Task 7: FastAPI app + 认证 API

**Files:**
- Create: `backend/api/deps.py`
- Create: `backend/api/auth.py`
- Create: `backend/schemas/schemas.py`
- Create: `backend/main.py`
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/test_api_auth.py`

- [ ] **Step 1: 创建 `backend/schemas/schemas.py`**

```python
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


class SendVerifyRequest(BaseModel):
    phone: str


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
```

- [ ] **Step 2: 创建 `backend/api/deps.py`**

```python
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from config import settings
from database import SessionLocal
from models.models import User

bearer_scheme = HTTPBearer()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    token = credentials.credentials
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        username: str = payload.get("sub")
        if not username:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin required")
    return current_user
```

- [ ] **Step 3: 创建 `backend/api/auth.py`**

```python
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException
from jose import jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from datetime import datetime

from api.deps import get_db, get_current_user
from config import settings
from models.models import User
from schemas.schemas import LoginRequest, TokenResponse, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def create_access_token(username: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=settings.jwt_expire_minutes)
    return jwt.encode(
        {"sub": username, "exp": expire},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == body.username).first()
    if not user or not pwd_context.verify(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    return TokenResponse(access_token=create_access_token(user.username))


@router.post("/refresh", response_model=TokenResponse)
def refresh(current_user: User = Depends(get_current_user)):
    return TokenResponse(access_token=create_access_token(current_user.username))


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    return current_user
```

- [ ] **Step 4: 创建 `backend/main.py`**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api import auth, accounts, products, logs, scheduler_router, settings as settings_router

app = FastAPI(title="imaotai_watcher", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(accounts.router, prefix="/api")
app.include_router(products.router, prefix="/api")
app.include_router(logs.router, prefix="/api")
app.include_router(scheduler_router.router, prefix="/api")
app.include_router(settings_router.router, prefix="/api")


@app.get("/api/health")
def health():
    return {"status": "ok"}
```

- [ ] **Step 5: 创建测试 fixture `backend/tests/conftest.py`**

```python
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from passlib.context import CryptContext

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database import Base
from api.deps import get_db
from models.models import User
from main import app

SQLALCHEMY_TEST_URL = "sqlite:///./test.db"
engine = create_engine(SQLALCHEMY_TEST_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


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
        password_hash=pwd_context.hash("testpass"),
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
```

- [ ] **Step 6: 创建 `backend/tests/test_api_auth.py`**

```python
def test_login_success(client, admin_user):
    resp = client.post("/api/auth/login", json={"username": "testadmin", "password": "testpass"})
    assert resp.status_code == 200
    assert "access_token" in resp.json()


def test_login_wrong_password(client, admin_user):
    resp = client.post("/api/auth/login", json={"username": "testadmin", "password": "wrong"})
    assert resp.status_code == 401


def test_me_requires_token(client):
    resp = client.get("/api/auth/me")
    assert resp.status_code == 403  # missing bearer


def test_me_returns_user(client, admin_token):
    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    assert resp.json()["username"] == "testadmin"


def test_refresh_returns_new_token(client, admin_token):
    resp = client.post("/api/auth/refresh", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    assert "access_token" in resp.json()
```

- [ ] **Step 7: 运行测试**

```bash
cd backend && python -m pytest tests/test_api_auth.py -v
# Expected: 5 passed
```

- [ ] **Step 8: Commit**

```bash
git add backend/schemas/ backend/api/deps.py backend/api/auth.py backend/main.py backend/tests/
git commit -m "feat: FastAPI app + JWT auth API"
```

---

### Task 8: 账号 API

**Files:**
- Create: `backend/api/accounts.py`

- [ ] **Step 1: 创建 `backend/api/accounts.py`**

```python
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.deps import get_db, get_current_user, require_admin
from models.models import Account
from schemas.schemas import AccountCreate, AccountUpdate, AccountOut, VerifyLoginRequest, MessageResponse
from core.imaotai_api import send_verify_code, login as imaotai_login
from redis_client import get_redis
from utils.logger import get_logger
from datetime import datetime

router = APIRouter(prefix="/accounts", tags=["accounts"])
logger = get_logger(__name__)

SMS_LIMIT_TTL = 60  # 秒


@router.get("", response_model=list[AccountOut])
def list_accounts(db: Session = Depends(get_db), _=Depends(get_current_user)):
    return db.query(Account).order_by(Account.created_at.desc()).all()


@router.post("", response_model=AccountOut)
def create_account(body: AccountCreate, db: Session = Depends(get_db), _=Depends(require_admin)):
    if db.query(Account).filter(Account.phone == body.phone).first():
        raise HTTPException(status_code=400, detail="手机号已存在")
    account = Account(
        phone=body.phone,
        city_code=body.city_code,
        device_id=str(uuid.uuid4()),
        status="active",
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


@router.put("/{account_id}", response_model=AccountOut)
def update_account(account_id: int, body: AccountUpdate, db: Session = Depends(get_db), _=Depends(require_admin)):
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="账号不存在")
    if body.city_code is not None:
        account.city_code = body.city_code
    if body.status is not None:
        account.status = body.status
    db.commit()
    db.refresh(account)
    return account


@router.delete("/{account_id}", response_model=MessageResponse)
def delete_account(account_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="账号不存在")
    db.delete(account)
    db.commit()
    return MessageResponse(message="删除成功")


@router.post("/{account_id}/verify", response_model=MessageResponse)
def send_verify(account_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="账号不存在")

    redis = get_redis()
    limit_key = f"sms:limit:{account.phone}"
    if redis.exists(limit_key):
        raise HTTPException(status_code=429, detail="60秒内只能发送一次验证码")

    try:
        send_verify_code(account.phone, account.device_id)
        redis.setex(limit_key, SMS_LIMIT_TTL, "1")
        return MessageResponse(message="验证码已发送")
    except Exception as e:
        logger.error(f"发送验证码失败: {e}")
        raise HTTPException(status_code=502, detail=f"发送验证码失败: {e}")


@router.post("/{account_id}/login", response_model=AccountOut)
def account_login(account_id: int, body: VerifyLoginRequest, db: Session = Depends(get_db), _=Depends(require_admin)):
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="账号不存在")

    try:
        result = imaotai_login(account.phone, body.verify_code, account.device_id)
        token = result.get("data", {}).get("token") or result.get("token")
        if not token:
            raise HTTPException(status_code=400, detail=f"登录失败: {result}")
        account.token = token
        account.status = "active"
        account.last_login = datetime.utcnow()
        db.commit()
        db.refresh(account)
        return account
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"登录失败: {e}")
```

- [ ] **Step 2: Commit**

```bash
git add backend/api/accounts.py
git commit -m "feat: accounts API with SMS rate limiting"
```

---

### Task 9: 商品 API

**Files:**
- Create: `backend/api/products.py`

- [ ] **Step 1: 创建 `backend/api/products.py`**

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.deps import get_db, get_current_user, require_admin
from models.models import Product
from schemas.schemas import ProductCreate, ProductUpdate, ProductOut, MessageResponse

router = APIRouter(prefix="/products", tags=["products"])


@router.get("", response_model=list[ProductOut])
def list_products(account_id: int | None = None, db: Session = Depends(get_db), _=Depends(get_current_user)):
    query = db.query(Product)
    if account_id is not None:
        query = query.filter(Product.account_id == account_id)
    else:
        query = query.filter(Product.account_id == None)
    return query.all()


@router.post("", response_model=ProductOut)
def create_product(body: ProductCreate, db: Session = Depends(get_db), _=Depends(require_admin)):
    product = Product(
        account_id=body.account_id,
        item_code=body.item_code,
        item_name=body.item_name,
        enabled=True,
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@router.put("/{product_id}", response_model=ProductOut)
def update_product(product_id: int, body: ProductUpdate, db: Session = Depends(get_db), _=Depends(require_admin)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="商品不存在")
    if body.enabled is not None:
        product.enabled = body.enabled
    if body.item_name is not None:
        product.item_name = body.item_name
    db.commit()
    db.refresh(product)
    return product


@router.delete("/{product_id}", response_model=MessageResponse)
def delete_product(product_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="商品不存在")
    db.delete(product)
    db.commit()
    return MessageResponse(message="删除成功")
```

- [ ] **Step 2: Commit**

```bash
git add backend/api/products.py
git commit -m "feat: products API"
```

---

### Task 10: 日志 API + 调度器 API + 设置 API

**Files:**
- Create: `backend/api/logs.py`
- Create: `backend/api/scheduler_router.py`
- Create: `backend/api/settings.py`

- [ ] **Step 1: 创建 `backend/api/logs.py`**

```python
import json
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from api.deps import get_db, get_current_user
from models.models import PurchaseLog, Account
from redis_client import get_redis
from schemas.schemas import LogsResponse, PurchaseLogOut, StatsResponse

router = APIRouter(prefix="/logs", tags=["logs"])

STATS_CACHE_KEY = "cache:stats"
STATS_CACHE_TTL = 300  # 5 minutes


@router.get("", response_model=LogsResponse)
def list_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    account_id: int | None = None,
    status: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    query = db.query(PurchaseLog)
    if account_id:
        query = query.filter(PurchaseLog.account_id == account_id)
    if status:
        query = query.filter(PurchaseLog.status == status)
    if date_from:
        query = query.filter(PurchaseLog.purchased_at >= datetime.fromisoformat(date_from))
    if date_to:
        query = query.filter(PurchaseLog.purchased_at <= datetime.fromisoformat(date_to))

    total = query.count()
    items = query.order_by(PurchaseLog.purchased_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return LogsResponse(total=total, items=items)


@router.get("/stats", response_model=StatsResponse)
def get_stats(db: Session = Depends(get_db), _=Depends(get_current_user)):
    redis = get_redis()
    cached = redis.get(STATS_CACHE_KEY)
    if cached:
        return StatsResponse(**json.loads(cached))

    today = datetime.utcnow().date()
    today_start = datetime.combine(today, datetime.min.time())

    total_accounts = db.query(Account).count()
    today_success = db.query(PurchaseLog).filter(
        PurchaseLog.purchased_at >= today_start,
        PurchaseLog.status == "success",
    ).count()
    today_fail = db.query(PurchaseLog).filter(
        PurchaseLog.purchased_at >= today_start,
        PurchaseLog.status == "fail",
    ).count()

    # 近7日趋势
    trend = []
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        day_start = datetime.combine(day, datetime.min.time())
        day_end = day_start + timedelta(days=1)
        s = db.query(PurchaseLog).filter(
            PurchaseLog.purchased_at >= day_start,
            PurchaseLog.purchased_at < day_end,
            PurchaseLog.status == "success",
        ).count()
        f = db.query(PurchaseLog).filter(
            PurchaseLog.purchased_at >= day_start,
            PurchaseLog.purchased_at < day_end,
            PurchaseLog.status == "fail",
        ).count()
        trend.append({"date": day.isoformat(), "success": s, "fail": f})

    result = StatsResponse(
        total_accounts=total_accounts,
        today_success=today_success,
        today_fail=today_fail,
        trend=trend,
    )
    redis.setex(STATS_CACHE_KEY, STATS_CACHE_TTL, result.model_dump_json())
    return result
```

- [ ] **Step 2: 创建 `backend/api/scheduler_router.py`**

```python
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.deps import get_db, get_current_user, require_admin
from models.models import SchedulerState
from redis_client import get_redis
from schemas.schemas import SchedulerStatus, SchedulerConfig, MessageResponse

router = APIRouter(prefix="/scheduler", tags=["scheduler"])

HEARTBEAT_KEY = "scheduler:heartbeat"
TRIGGER_KEY = "scheduler:trigger"


@router.get("/status", response_model=SchedulerStatus)
def scheduler_status(db: Session = Depends(get_db), _=Depends(get_current_user)):
    redis = get_redis()
    alive = bool(redis.exists(HEARTBEAT_KEY))
    state = db.query(SchedulerState).filter(SchedulerState.id == 1).first()
    return SchedulerStatus(
        alive=alive,
        schedule_time=state.schedule_time if state else "09:00",
        last_run_at=state.last_run_at if state else None,
        next_run_at=state.next_run_at if state else None,
    )


@router.post("/trigger", response_model=MessageResponse)
def trigger_purchase(_=Depends(require_admin)):
    redis = get_redis()
    redis.lpush(TRIGGER_KEY, "manual")
    return MessageResponse(message="已发送手动触发指令")


@router.put("/config", response_model=MessageResponse)
def update_config(body: SchedulerConfig, db: Session = Depends(get_db), _=Depends(require_admin)):
    # 验证格式
    parts = body.schedule_time.split(":")
    if len(parts) != 2 or not all(p.isdigit() for p in parts):
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="格式应为 HH:MM")

    state = db.query(SchedulerState).filter(SchedulerState.id == 1).first()
    if not state:
        state = SchedulerState(id=1)
        db.add(state)
    state.schedule_time = body.schedule_time
    db.commit()

    # 通知调度器重新配置
    redis = get_redis()
    redis.lpush(TRIGGER_KEY, "reschedule")
    return MessageResponse(message=f"申购时间已更新为 {body.schedule_time}")
```

- [ ] **Step 3: 创建 `backend/api/settings.py`**

```python
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.deps import get_db, get_current_user, require_admin
from models.models import AppSetting
from schemas.schemas import NotifySettings, MessageResponse
from core.notifier import send_server_chan

router = APIRouter(prefix="/settings", tags=["settings"])

NOTIFY_KEY = "notify_send_key"


def _get_setting(db: Session, key: str) -> str:
    setting = db.query(AppSetting).filter(AppSetting.key == key).first()
    return setting.value if setting and setting.value else ""


def _set_setting(db: Session, key: str, value: str):
    setting = db.query(AppSetting).filter(AppSetting.key == key).first()
    if setting:
        setting.value = value
    else:
        db.add(AppSetting(key=key, value=value))
    db.commit()


@router.get("/notify", response_model=NotifySettings)
def get_notify(db: Session = Depends(get_db), _=Depends(get_current_user)):
    return NotifySettings(send_key=_get_setting(db, NOTIFY_KEY))


@router.put("/notify", response_model=MessageResponse)
def update_notify(body: NotifySettings, db: Session = Depends(get_db), _=Depends(require_admin)):
    _set_setting(db, NOTIFY_KEY, body.send_key)
    return MessageResponse(message="通知配置已更新")


@router.post("/notify/test", response_model=MessageResponse)
def test_notify(db: Session = Depends(get_db), _=Depends(require_admin)):
    send_key = _get_setting(db, NOTIFY_KEY)
    send_server_chan(send_key, "i茅台抢购 - 测试通知", "如果收到此消息，说明通知配置正常。")
    return MessageResponse(message="测试通知已发送")
```

- [ ] **Step 4: 运行所有后端测试**

```bash
cd backend && python -m pytest tests/ -v
# Expected: all passed
```

- [ ] **Step 5: Commit**

```bash
git add backend/api/
git commit -m "feat: logs, scheduler, settings API"
```

---

## Phase 3: Frontend

### Task 11: React + TypeScript 脚手架

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tsconfig.json`
- Create: `frontend/index.html`
- Create: `frontend/src/main.tsx`

- [ ] **Step 1: 初始化前端项目**

```bash
cd imaotai_watcher
npm create vite@latest frontend -- --template react-ts
cd frontend
```

- [ ] **Step 2: 安装依赖**

```bash
cd frontend
npm install antd @ant-design/icons @ant-design/charts axios zustand react-router-dom
npm install --save-dev @types/react @types/react-dom
```

- [ ] **Step 3: 更新 `frontend/vite.config.ts` 配置代理**

```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
```

- [ ] **Step 4: 更新 `frontend/src/main.tsx`**

```tsx
import React from 'react'
import ReactDOM from 'react-dom/client'
import { ConfigProvider } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import App from './App'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ConfigProvider locale={zhCN}>
      <App />
    </ConfigProvider>
  </React.StrictMode>,
)
```

- [ ] **Step 5: 创建 `frontend/src/index.css`**

```css
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }
```

- [ ] **Step 6: Commit**

```bash
cd ..
git add frontend/
git commit -m "feat: React + TypeScript frontend scaffold"
```

---

### Task 12: Auth store + axios client + PrivateRoute

**Files:**
- Create: `frontend/src/store/authStore.ts`
- Create: `frontend/src/api/client.ts`
- Create: `frontend/src/api/auth.ts`
- Create: `frontend/src/components/PrivateRoute.tsx`

- [ ] **Step 1: 创建 `frontend/src/store/authStore.ts`**

```typescript
import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface AuthState {
  token: string | null
  username: string | null
  role: string | null
  setAuth: (token: string, username: string, role: string) => void
  clearAuth: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      username: null,
      role: null,
      setAuth: (token, username, role) => set({ token, username, role }),
      clearAuth: () => set({ token: null, username: null, role: null }),
    }),
    { name: 'auth-storage' }
  )
)
```

- [ ] **Step 2: 创建 `frontend/src/api/client.ts`**

```typescript
import axios from 'axios'
import { useAuthStore } from '../store/authStore'

const client = axios.create({ baseURL: '/api' })

client.interceptors.request.use((config) => {
  const token = useAuthStore.getState().token
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

client.interceptors.response.use(
  (res) => res,
  (error) => {
    if (error.response?.status === 401) {
      useAuthStore.getState().clearAuth()
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

export default client
```

- [ ] **Step 3: 创建 `frontend/src/api/auth.ts`**

```typescript
import client from './client'

export const login = (username: string, password: string) =>
  client.post<{ access_token: string }>('/auth/login', { username, password })

export const getMe = () =>
  client.get<{ id: number; username: string; role: string }>('/auth/me')

export const refresh = () =>
  client.post<{ access_token: string }>('/auth/refresh')
```

- [ ] **Step 4: 创建 `frontend/src/components/PrivateRoute.tsx`**

```tsx
import { Navigate } from 'react-router-dom'
import { useAuthStore } from '../store/authStore'

export default function PrivateRoute({ children }: { children: React.ReactNode }) {
  const token = useAuthStore((s) => s.token)
  return token ? <>{children}</> : <Navigate to="/login" replace />
}
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/store/ frontend/src/api/ frontend/src/components/PrivateRoute.tsx
git commit -m "feat: auth store, axios client, PrivateRoute"
```

---

### Task 13: 其余 API 模块

**Files:**
- Create: `frontend/src/api/accounts.ts`
- Create: `frontend/src/api/products.ts`
- Create: `frontend/src/api/logs.ts`
- Create: `frontend/src/api/scheduler.ts`
- Create: `frontend/src/api/settings.ts`

- [ ] **Step 1: 创建各 API 模块**

`frontend/src/api/accounts.ts`:
```typescript
import client from './client'

export interface Account {
  id: number; phone: string; device_id: string; city_code: string
  status: 'active' | 'expired'; last_login: string | null; created_at: string
}

export const listAccounts = () => client.get<Account[]>('/accounts')
export const createAccount = (phone: string, city_code: string) =>
  client.post<Account>('/accounts', { phone, city_code })
export const updateAccount = (id: number, data: { city_code?: string; status?: string }) =>
  client.put<Account>(`/accounts/${id}`, data)
export const deleteAccount = (id: number) => client.delete(`/accounts/${id}`)
export const sendVerifyCode = (id: number) => client.post(`/accounts/${id}/verify`)
export const accountLogin = (id: number, verify_code: string) =>
  client.post<Account>(`/accounts/${id}/login`, { verify_code })
```

`frontend/src/api/products.ts`:
```typescript
import client from './client'

export interface Product {
  id: number; account_id: number | null; item_code: string; item_name: string; enabled: boolean
}

export const listProducts = (account_id?: number) =>
  client.get<Product[]>('/products', { params: account_id != null ? { account_id } : {} })
export const createProduct = (data: { account_id?: number; item_code: string; item_name: string }) =>
  client.post<Product>('/products', data)
export const updateProduct = (id: number, data: { enabled?: boolean; item_name?: string }) =>
  client.put<Product>(`/products/${id}`, data)
export const deleteProduct = (id: number) => client.delete(`/products/${id}`)
```

`frontend/src/api/logs.ts`:
```typescript
import client from './client'

export interface PurchaseLog {
  id: number; account_id: number; item_code: string; item_name: string
  status: string; message: string | null; purchased_at: string
}

export interface StatsData {
  total_accounts: number; today_success: number; today_fail: number
  trend: { date: string; success: number; fail: number }[]
}

export const listLogs = (params: {
  page?: number; page_size?: number; account_id?: number; status?: string
  date_from?: string; date_to?: string
}) => client.get<{ total: number; items: PurchaseLog[] }>('/logs', { params })

export const getStats = () => client.get<StatsData>('/logs/stats')
```

`frontend/src/api/scheduler.ts`:
```typescript
import client from './client'

export interface SchedulerStatus {
  alive: boolean; schedule_time: string; last_run_at: string | null; next_run_at: string | null
}

export const getSchedulerStatus = () => client.get<SchedulerStatus>('/scheduler/status')
export const triggerPurchase = () => client.post('/scheduler/trigger')
export const updateSchedulerConfig = (schedule_time: string) =>
  client.put('/scheduler/config', { schedule_time })
```

`frontend/src/api/settings.ts`:
```typescript
import client from './client'

export const getNotifySettings = () => client.get<{ send_key: string }>('/settings/notify')
export const updateNotifySettings = (send_key: string) =>
  client.put('/settings/notify', { send_key })
export const testNotify = () => client.post('/settings/notify/test')
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/api/
git commit -m "feat: frontend API modules"
```

---

### Task 14: AppLayout + App routing

**Files:**
- Create: `frontend/src/components/AppLayout.tsx`
- Create: `frontend/src/App.tsx`

- [ ] **Step 1: 创建 `frontend/src/components/AppLayout.tsx`**

```tsx
import { Layout, Menu, Avatar, Typography, Space } from 'antd'
import {
  DashboardOutlined, UserOutlined, ShoppingOutlined,
  FileTextOutlined, SettingOutlined, LogoutOutlined,
} from '@ant-design/icons'
import { useNavigate, useLocation, Outlet } from 'react-router-dom'
import { useAuthStore } from '../store/authStore'

const { Sider, Content, Header } = Layout
const { Text } = Typography

const menuItems = [
  { key: '/dashboard', icon: <DashboardOutlined />, label: '仪表盘' },
  { key: '/accounts', icon: <UserOutlined />, label: '账号管理' },
  { key: '/products', icon: <ShoppingOutlined />, label: '商品配置' },
  { key: '/logs', icon: <FileTextOutlined />, label: '申购日志' },
  { key: '/settings', icon: <SettingOutlined />, label: '系统设置' },
]

export default function AppLayout() {
  const navigate = useNavigate()
  const location = useLocation()
  const { username, clearAuth } = useAuthStore()

  const handleLogout = () => {
    clearAuth()
    navigate('/login')
  }

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider theme="dark" width={200}>
        <div style={{ padding: '16px', textAlign: 'center', color: '#fff', fontSize: 16, fontWeight: 'bold' }}>
          i茅台抢购
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[location.pathname]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
        />
      </Sider>
      <Layout>
        <Header style={{ background: '#fff', padding: '0 24px', display: 'flex', justifyContent: 'flex-end', alignItems: 'center' }}>
          <Space>
            <Avatar icon={<UserOutlined />} />
            <Text>{username}</Text>
            <LogoutOutlined onClick={handleLogout} style={{ cursor: 'pointer', color: '#999' }} />
          </Space>
        </Header>
        <Content style={{ margin: '24px', background: '#fff', padding: 24, borderRadius: 8, minHeight: 360 }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  )
}
```

- [ ] **Step 2: 创建 `frontend/src/App.tsx`**

```tsx
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import PrivateRoute from './components/PrivateRoute'
import AppLayout from './components/AppLayout'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Accounts from './pages/Accounts'
import Products from './pages/Products'
import Logs from './pages/Logs'
import Settings from './pages/Settings'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/" element={<PrivateRoute><AppLayout /></PrivateRoute>}>
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="dashboard" element={<Dashboard />} />
          <Route path="accounts" element={<Accounts />} />
          <Route path="products" element={<Products />} />
          <Route path="logs" element={<Logs />} />
          <Route path="settings" element={<Settings />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/AppLayout.tsx frontend/src/App.tsx
git commit -m "feat: AppLayout + routing"
```

---

### Task 15: Login 页面

**Files:**
- Create: `frontend/src/pages/Login.tsx`

- [ ] **Step 1: 创建 `frontend/src/pages/Login.tsx`**

```tsx
import { Form, Input, Button, Card, Typography, message } from 'antd'
import { UserOutlined, LockOutlined } from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import { login, getMe } from '../api/auth'
import { useAuthStore } from '../store/authStore'

const { Title } = Typography

export default function Login() {
  const navigate = useNavigate()
  const setAuth = useAuthStore((s) => s.setAuth)
  const [form] = Form.useForm()

  const handleSubmit = async (values: { username: string; password: string }) => {
    try {
      const { data } = await login(values.username, values.password)
      // 临时设置 token 后获取用户信息
      useAuthStore.setState({ token: data.access_token })
      const { data: me } = await getMe()
      setAuth(data.access_token, me.username, me.role)
      navigate('/dashboard')
    } catch {
      message.error('用户名或密码错误')
    }
  }

  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh', background: '#f0f2f5' }}>
      <Card style={{ width: 400 }}>
        <div style={{ textAlign: 'center', marginBottom: 32 }}>
          <Title level={3}>i茅台抢购系统</Title>
        </div>
        <Form form={form} onFinish={handleSubmit} size="large">
          <Form.Item name="username" rules={[{ required: true, message: '请输入用户名' }]}>
            <Input prefix={<UserOutlined />} placeholder="用户名" />
          </Form.Item>
          <Form.Item name="password" rules={[{ required: true, message: '请输入密码' }]}>
            <Input.Password prefix={<LockOutlined />} placeholder="密码" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" block>登录</Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/Login.tsx
git commit -m "feat: login page"
```

---

### Task 16: Dashboard 页面

**Files:**
- Create: `frontend/src/pages/Dashboard.tsx`

- [ ] **Step 1: 创建 `frontend/src/pages/Dashboard.tsx`**

```tsx
import { useEffect, useState, useRef } from 'react'
import { Row, Col, Card, Statistic, Table, Tag, Typography, Badge } from 'antd'
import { CheckCircleOutlined, CloseCircleOutlined, UserOutlined, ClockCircleOutlined } from '@ant-design/icons'
import { Line } from '@ant-design/charts'
import { getStats, listLogs, StatsData, PurchaseLog } from '../api/logs'
import { getSchedulerStatus } from '../api/scheduler'

const { Title } = Typography

const statusTag = (status: string) => {
  if (status === 'success') return <Tag color="success">成功</Tag>
  if (status === 'fail') return <Tag color="error">失败</Tag>
  return <Tag>重试</Tag>
}

export default function Dashboard() {
  const [stats, setStats] = useState<StatsData | null>(null)
  const [logs, setLogs] = useState<PurchaseLog[]>([])
  const [schedulerAlive, setSchedulerAlive] = useState(false)
  const timerRef = useRef<number>()

  const fetchData = async () => {
    const [statsRes, logsRes, schedulerRes] = await Promise.all([
      getStats(),
      listLogs({ page: 1, page_size: 20 }),
      getSchedulerStatus(),
    ])
    setStats(statsRes.data)
    setLogs(logsRes.data.items)
    setSchedulerAlive(schedulerRes.data.alive)
  }

  useEffect(() => {
    fetchData()
    timerRef.current = window.setInterval(fetchData, 30_000)
    return () => clearInterval(timerRef.current)
  }, [])

  const trendData = stats?.trend.flatMap((d) => [
    { date: d.date, count: d.success, type: '成功' },
    { date: d.date, count: d.fail, type: '失败' },
  ]) ?? []

  const columns = [
    { title: '时间', dataIndex: 'purchased_at', key: 'time', render: (v: string) => new Date(v).toLocaleString() },
    { title: '账号', dataIndex: 'account_id', key: 'account' },
    { title: '商品', dataIndex: 'item_name', key: 'item' },
    { title: '状态', dataIndex: 'status', key: 'status', render: statusTag },
    { title: '信息', dataIndex: 'message', key: 'message', ellipsis: true },
  ]

  return (
    <div>
      <Title level={4}>仪表盘</Title>
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col span={6}>
          <Card>
            <Statistic title="账号总数" value={stats?.total_accounts ?? '-'} prefix={<UserOutlined />} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="今日成功" value={stats?.today_success ?? '-'} valueStyle={{ color: '#52c41a' }} prefix={<CheckCircleOutlined />} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="今日失败" value={stats?.today_fail ?? '-'} valueStyle={{ color: '#ff4d4f' }} prefix={<CloseCircleOutlined />} />
          </Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="调度器状态"
              value={schedulerAlive ? '运行中' : '离线'}
              valueStyle={{ color: schedulerAlive ? '#52c41a' : '#ff4d4f' }}
              prefix={schedulerAlive ? <Badge status="processing" /> : <Badge status="error" />}
            />
          </Card>
        </Col>
      </Row>

      <Card title="近7日申购趋势" style={{ marginBottom: 24 }}>
        <Line
          data={trendData}
          xField="date"
          yField="count"
          seriesField="type"
          color={['#52c41a', '#ff4d4f']}
          height={260}
        />
      </Card>

      <Card title="最近申购记录">
        <Table dataSource={logs} columns={columns} rowKey="id" pagination={false} size="small" />
      </Card>
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/Dashboard.tsx
git commit -m "feat: dashboard page with charts and auto-refresh"
```

---

### Task 17: Accounts 页面

**Files:**
- Create: `frontend/src/pages/Accounts.tsx`

- [ ] **Step 1: 创建 `frontend/src/pages/Accounts.tsx`**

```tsx
import { useEffect, useState } from 'react'
import { Table, Button, Tag, Space, Modal, Form, Input, message, Popconfirm, Typography } from 'antd'
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons'
import { listAccounts, createAccount, deleteAccount, sendVerifyCode, accountLogin, Account } from '../api/accounts'

const { Title } = Typography

type Step = 'phone' | 'code'

export default function Accounts() {
  const [accounts, setAccounts] = useState<Account[]>([])
  const [loading, setLoading] = useState(false)
  const [modalOpen, setModalOpen] = useState(false)
  const [step, setStep] = useState<Step>('phone')
  const [pendingAccount, setPendingAccount] = useState<Account | null>(null)
  const [form] = Form.useForm()

  const fetchAccounts = async () => {
    setLoading(true)
    const { data } = await listAccounts()
    setAccounts(data)
    setLoading(false)
  }

  useEffect(() => { fetchAccounts() }, [])

  const handleAddPhone = async (values: { phone: string; city_code: string }) => {
    try {
      const { data } = await createAccount(values.phone, values.city_code)
      await sendVerifyCode(data.id)
      setPendingAccount(data)
      setStep('code')
      message.success('验证码已发送')
    } catch (e: any) {
      message.error(e.response?.data?.detail || '操作失败')
    }
  }

  const handleVerifyCode = async (values: { verify_code: string }) => {
    if (!pendingAccount) return
    try {
      await accountLogin(pendingAccount.id, values.verify_code)
      message.success('账号登录成功')
      setModalOpen(false)
      setStep('phone')
      form.resetFields()
      setPendingAccount(null)
      fetchAccounts()
    } catch (e: any) {
      message.error(e.response?.data?.detail || '验证码错误')
    }
  }

  const handleResendCode = async () => {
    if (!pendingAccount) return
    try {
      await sendVerifyCode(pendingAccount.id)
      message.success('验证码已重新发送')
    } catch (e: any) {
      message.error(e.response?.data?.detail || '发送失败')
    }
  }

  const handleDelete = async (id: number) => {
    await deleteAccount(id)
    message.success('已删除')
    fetchAccounts()
  }

  const columns = [
    { title: '手机号', dataIndex: 'phone', key: 'phone' },
    { title: '城市码', dataIndex: 'city_code', key: 'city_code' },
    {
      title: '状态', dataIndex: 'status', key: 'status',
      render: (s: string) => s === 'active' ? <Tag color="success">正常</Tag> : <Tag color="error">Token过期</Tag>
    },
    { title: '最近登录', dataIndex: 'last_login', key: 'last_login', render: (v: string) => v ? new Date(v).toLocaleString() : '-' },
    {
      title: '操作', key: 'action',
      render: (_: unknown, record: Account) => (
        <Space>
          <Popconfirm title="确认删除？" onConfirm={() => handleDelete(record.id)}>
            <Button danger size="small">删除</Button>
          </Popconfirm>
        </Space>
      )
    },
  ]

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <Title level={4}>账号管理</Title>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={fetchAccounts}>刷新</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => { setModalOpen(true); setStep('phone') }}>添加账号</Button>
        </Space>
      </div>
      <Table dataSource={accounts} columns={columns} rowKey="id" loading={loading} />

      <Modal
        title={step === 'phone' ? '添加账号' : '输入验证码'}
        open={modalOpen}
        footer={null}
        onCancel={() => { setModalOpen(false); setStep('phone'); form.resetFields(); setPendingAccount(null) }}
      >
        {step === 'phone' ? (
          <Form form={form} onFinish={handleAddPhone} layout="vertical">
            <Form.Item name="phone" label="手机号" rules={[{ required: true }]}>
              <Input placeholder="13800138000" />
            </Form.Item>
            <Form.Item name="city_code" label="城市代码" rules={[{ required: true }]} extra="例：500100（重庆）">
              <Input placeholder="500100" />
            </Form.Item>
            <Button type="primary" htmlType="submit" block>发送验证码</Button>
          </Form>
        ) : (
          <Form form={form} onFinish={handleVerifyCode} layout="vertical">
            <Form.Item name="verify_code" label="验证码" rules={[{ required: true }]}>
              <Input placeholder="请输入6位验证码" maxLength={6} />
            </Form.Item>
            <Space style={{ width: '100%' }} direction="vertical">
              <Button type="primary" htmlType="submit" block>登录</Button>
              <Button onClick={handleResendCode} block>重新发送验证码</Button>
            </Space>
          </Form>
        )}
      </Modal>
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/Accounts.tsx
git commit -m "feat: accounts page with 2-step SMS login modal"
```

---

### Task 18: Products 页面

**Files:**
- Create: `frontend/src/pages/Products.tsx`

- [ ] **Step 1: 创建 `frontend/src/pages/Products.tsx`**

```tsx
import { useEffect, useState } from 'react'
import { Tabs, Table, Switch, Button, Space, Modal, Form, Input, message, Popconfirm, Typography, Select } from 'antd'
import { PlusOutlined } from '@ant-design/icons'
import { listProducts, createProduct, updateProduct, deleteProduct, Product } from '../api/products'
import { listAccounts, Account } from '../api/accounts'

const { Title } = Typography

export default function Products() {
  const [products, setProducts] = useState<Product[]>([])
  const [accounts, setAccounts] = useState<Account[]>([])
  const [activeAccountId, setActiveAccountId] = useState<number | undefined>(undefined)
  const [modalOpen, setModalOpen] = useState(false)
  const [form] = Form.useForm()

  const fetchProducts = async (accountId?: number) => {
    const { data } = await listProducts(accountId)
    setProducts(data)
  }

  useEffect(() => {
    listAccounts().then(({ data }) => setAccounts(data))
    fetchProducts(undefined)
  }, [])

  const handleTabChange = (key: string) => {
    const id = key === 'global' ? undefined : Number(key)
    setActiveAccountId(id)
    fetchProducts(id)
  }

  const handleToggle = async (id: number, enabled: boolean) => {
    await updateProduct(id, { enabled })
    fetchProducts(activeAccountId)
  }

  const handleDelete = async (id: number) => {
    await deleteProduct(id)
    message.success('已删除')
    fetchProducts(activeAccountId)
  }

  const handleAdd = async (values: { item_code: string; item_name: string }) => {
    await createProduct({ ...values, account_id: activeAccountId })
    message.success('已添加')
    setModalOpen(false)
    form.resetFields()
    fetchProducts(activeAccountId)
  }

  const columns = [
    { title: '商品名称', dataIndex: 'item_name', key: 'item_name' },
    { title: '商品编码', dataIndex: 'item_code', key: 'item_code' },
    {
      title: '启用', dataIndex: 'enabled', key: 'enabled',
      render: (v: boolean, r: Product) => <Switch checked={v} onChange={(checked) => handleToggle(r.id, checked)} />
    },
    {
      title: '操作', key: 'action',
      render: (_: unknown, record: Product) => (
        <Popconfirm title="确认删除？" onConfirm={() => handleDelete(record.id)}>
          <Button danger size="small">删除</Button>
        </Popconfirm>
      )
    },
  ]

  const tabItems = [
    { key: 'global', label: '全局默认' },
    ...accounts.map((a) => ({ key: String(a.id), label: a.phone })),
  ]

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <Title level={4}>商品配置</Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalOpen(true)}>添加商品</Button>
      </div>
      <Tabs items={tabItems} onChange={handleTabChange} />
      <Table dataSource={products} columns={columns} rowKey="id" />

      <Modal title="添加商品" open={modalOpen} footer={null} onCancel={() => { setModalOpen(false); form.resetFields() }}>
        <Form form={form} onFinish={handleAdd} layout="vertical">
          <Form.Item name="item_code" label="商品编码" rules={[{ required: true }]} extra="例：10941（飞天茅台500ml）">
            <Input placeholder="10941" />
          </Form.Item>
          <Form.Item name="item_name" label="商品名称" rules={[{ required: true }]}>
            <Input placeholder="飞天茅台500ml" />
          </Form.Item>
          <Button type="primary" htmlType="submit" block>添加</Button>
        </Form>
      </Modal>
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/Products.tsx
git commit -m "feat: products page with account tab switching"
```

---

### Task 19: Logs 页面

**Files:**
- Create: `frontend/src/pages/Logs.tsx`

- [ ] **Step 1: 创建 `frontend/src/pages/Logs.tsx`**

```tsx
import { useEffect, useState } from 'react'
import { Table, Tag, Space, Select, DatePicker, Button, Typography } from 'antd'
import { SearchOutlined, ReloadOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { listLogs, PurchaseLog } from '../api/logs'
import { listAccounts, Account } from '../api/accounts'

const { Title } = Typography
const { RangePicker } = DatePicker

export default function Logs() {
  const [logs, setLogs] = useState<PurchaseLog[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [accounts, setAccounts] = useState<Account[]>([])
  const [filters, setFilters] = useState<{
    page: number; account_id?: number; status?: string; date_from?: string; date_to?: string
  }>({ page: 1 })

  const fetchLogs = async (f = filters) => {
    setLoading(true)
    const { data } = await listLogs({ ...f, page_size: 20 })
    setLogs(data.items)
    setTotal(data.total)
    setLoading(false)
  }

  useEffect(() => {
    listAccounts().then(({ data }) => setAccounts(data))
    fetchLogs()
  }, [])

  const columns = [
    { title: '时间', dataIndex: 'purchased_at', key: 'time', render: (v: string) => new Date(v).toLocaleString() },
    { title: '账号ID', dataIndex: 'account_id', key: 'account' },
    { title: '商品', dataIndex: 'item_name', key: 'item' },
    { title: '编码', dataIndex: 'item_code', key: 'code' },
    {
      title: '状态', dataIndex: 'status', key: 'status',
      render: (s: string) => s === 'success' ? <Tag color="success">成功</Tag> : <Tag color="error">失败</Tag>
    },
    { title: 'API信息', dataIndex: 'message', key: 'message', ellipsis: true },
  ]

  return (
    <div>
      <Title level={4}>申购日志</Title>
      <Space style={{ marginBottom: 16 }} wrap>
        <Select
          allowClear placeholder="筛选账号" style={{ width: 160 }}
          options={accounts.map((a) => ({ label: a.phone, value: a.id }))}
          onChange={(v) => setFilters((f) => ({ ...f, account_id: v, page: 1 }))}
        />
        <Select
          allowClear placeholder="筛选状态" style={{ width: 120 }}
          options={[{ label: '成功', value: 'success' }, { label: '失败', value: 'fail' }]}
          onChange={(v) => setFilters((f) => ({ ...f, status: v, page: 1 }))}
        />
        <RangePicker
          onChange={(dates) => {
            if (dates) {
              setFilters((f) => ({
                ...f,
                date_from: dates[0]?.toISOString(),
                date_to: dates[1]?.toISOString(),
                page: 1,
              }))
            } else {
              setFilters((f) => ({ ...f, date_from: undefined, date_to: undefined, page: 1 }))
            }
          }}
        />
        <Button icon={<SearchOutlined />} type="primary" onClick={() => fetchLogs()}>查询</Button>
        <Button icon={<ReloadOutlined />} onClick={() => { setFilters({ page: 1 }); fetchLogs({ page: 1 }) }}>重置</Button>
      </Space>
      <Table
        dataSource={logs}
        columns={columns}
        rowKey="id"
        loading={loading}
        pagination={{
          total,
          pageSize: 20,
          current: filters.page,
          onChange: (page) => { const f = { ...filters, page }; setFilters(f); fetchLogs(f) },
        }}
      />
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/Logs.tsx
git commit -m "feat: logs page with filtering and pagination"
```

---

### Task 20: Settings 页面

**Files:**
- Create: `frontend/src/pages/Settings.tsx`

- [ ] **Step 1: 创建 `frontend/src/pages/Settings.tsx`**

```tsx
import { useEffect, useState } from 'react'
import { Form, Input, Button, Card, TimePicker, message, Space, Modal, Typography, Divider } from 'antd'
import { ExclamationCircleOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { getNotifySettings, updateNotifySettings, testNotify } from '../api/settings'
import { getSchedulerStatus, updateSchedulerConfig, triggerPurchase } from '../api/scheduler'

const { Title } = Typography
const { confirm } = Modal

export default function Settings() {
  const [notifyForm] = Form.useForm()
  const [scheduleForm] = Form.useForm()
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    getNotifySettings().then(({ data }) => notifyForm.setFieldValue('send_key', data.send_key))
    getSchedulerStatus().then(({ data }) => {
      const [h, m] = data.schedule_time.split(':')
      scheduleForm.setFieldValue('schedule_time', dayjs().hour(Number(h)).minute(Number(m)))
    })
  }, [])

  const handleSaveNotify = async (values: { send_key: string }) => {
    setLoading(true)
    await updateNotifySettings(values.send_key)
    message.success('通知配置已保存')
    setLoading(false)
  }

  const handleTestNotify = async () => {
    await testNotify()
    message.success('测试通知已发送，请查看微信')
  }

  const handleSaveSchedule = async (values: { schedule_time: dayjs.Dayjs }) => {
    const timeStr = values.schedule_time.format('HH:mm')
    await updateSchedulerConfig(timeStr)
    message.success(`申购时间已设置为 ${timeStr}`)
  }

  const handleTrigger = () => {
    confirm({
      title: '确认手动触发申购？',
      icon: <ExclamationCircleOutlined />,
      content: '将立即对所有 active 账号执行申购，请确认。',
      onOk: async () => {
        await triggerPurchase()
        message.success('申购指令已发送，调度器将立即执行')
      },
    })
  }

  return (
    <div>
      <Title level={4}>系统设置</Title>

      <Card title="申购时间配置" style={{ marginBottom: 24 }}>
        <Form form={scheduleForm} onFinish={handleSaveSchedule} layout="inline">
          <Form.Item name="schedule_time" label="每日申购时间">
            <TimePicker format="HH:mm" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit">保存</Button>
          </Form.Item>
        </Form>
      </Card>

      <Card title="通知设置（Server酱）" style={{ marginBottom: 24 }}>
        <Form form={notifyForm} onFinish={handleSaveNotify} layout="vertical" style={{ maxWidth: 500 }}>
          <Form.Item name="send_key" label="SendKey" extra="在 https://sct.ftqq.com 获取">
            <Input placeholder="SCT..." />
          </Form.Item>
          <Space>
            <Button type="primary" htmlType="submit" loading={loading}>保存</Button>
            <Button onClick={handleTestNotify}>发送测试通知</Button>
          </Space>
        </Form>
      </Card>

      <Card title="手动操作">
        <Button danger size="large" onClick={handleTrigger}>立即触发申购</Button>
      </Card>
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pages/Settings.tsx
git commit -m "feat: settings page - schedule time, notify config, manual trigger"
```

---

## Phase 4: Docker Deployment

### Task 21: Dockerfile + docker-compose + nginx

**Files:**
- Create: `backend/Dockerfile`
- Create: `frontend/Dockerfile`
- Create: `nginx/nginx.conf`
- Create: `docker-compose.yml`

- [ ] **Step 1: 创建 `backend/Dockerfile`**

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 默认启动 API，scheduler 通过 docker-compose command 覆盖
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: 创建 `frontend/Dockerfile`**

```dockerfile
# Stage 1: build
FROM node:18-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# Stage 2: serve
FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
# nginx.conf 由 docker-compose volume 挂载覆盖
EXPOSE 80
```

- [ ] **Step 3: 创建 `nginx/nginx.conf`**

```nginx
server {
    listen 80;
    server_name _;

    root /usr/share/nginx/html;
    index index.html;

    # 前端路由（React Router）
    location / {
        try_files $uri $uri/ /index.html;
    }

    # API 反代
    location /api/ {
        proxy_pass http://api:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 60s;
    }
}
```

- [ ] **Step 4: 创建 `docker-compose.yml`**

```yaml
version: '3.9'

services:
  api:
    build: ./backend
    restart: unless-stopped
    env_file: .env
    depends_on: []
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  scheduler:
    build: ./backend
    restart: unless-stopped
    env_file: .env
    command: ["python", "scheduler/main.py"]

  nginx:
    build: ./frontend
    restart: unless-stopped
    ports:
      - "80:80"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/conf.d/default.conf:ro
    depends_on:
      - api
```

- [ ] **Step 5: 首次启动前初始化数据库**

```bash
# 在 backend 目录，确保 .env 已配置
cd backend
cp ../.env.example ../.env
# 编辑 .env 填入 MySQL/Redis 连接信息和密钥
python init_db.py
# Expected: DB initialized.
```

- [ ] **Step 6: 构建并启动**

```bash
cd imaotai_watcher
docker-compose build
docker-compose up -d
# 验证
curl http://localhost/api/health
# Expected: {"status":"ok"}
```

- [ ] **Step 7: 验证调度器心跳**

```bash
# 等待 30s 后调度器写入心跳
docker-compose logs scheduler | tail -5
# Expected: 调度器进程启动，等待任务...
```

- [ ] **Step 8: Commit**

```bash
git add backend/Dockerfile frontend/Dockerfile nginx/ docker-compose.yml
git commit -m "feat: Docker deployment - api + scheduler + nginx"
```

---

## Self-Review Checklist

| Spec 要求 | 覆盖任务 |
|-----------|---------|
| 多账号并发申购 | Task 5（ThreadPoolExecutor） |
| 失败重试3次间隔1s | Task 5（purchase.py） |
| 精确定时09:00 | Task 6（APScheduler CronTrigger） |
| Server酱通知 | Task 5（notifier.py）、Task 10 |
| JWT 登录鉴权 | Task 7（auth.py + deps.py） |
| admin/viewer 权限 | Task 7（require_admin） |
| 验证码防刷 Redis TTL | Task 8（accounts.py） |
| 统计接口 Redis 缓存 | Task 10（logs.py） |
| 调度器心跳 Redis TTL | Task 6（scheduler/main.py） |
| 手动触发 Redis BRPOP | Task 6 + Task 10 |
| 申购时间可配置 | Task 10（scheduler_router.py） |
| Docker Compose 3容器 | Task 21 |
| MySQL 外部实例配置 | Task 1（config.py .env） |
| Redis 外部实例配置 | Task 1（config.py .env） |
| React Dashboard 折线图 | Task 16 |
| 账号管理页 SMS 2步 | Task 17 |
| 商品 Tab 切换 | Task 18 |
| 日志分页筛选 | Task 19 |
| 设置页触发申购 | Task 20 |
