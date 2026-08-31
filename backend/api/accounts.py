from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.deps import get_db, get_current_user, require_admin
from models.models import Account
from schemas.schemas import AccountCreate, AccountUpdate, AccountOut, VerifyLoginRequest, MessageResponse, TodayItemOut
from core.imaotai_api import send_verify_code, login as imaotai_login, get_today_items, MoutaiError
from utils.signature import generate_device_id
from utils.memcache import cache
from utils.logger import get_logger

router = APIRouter(prefix="/accounts", tags=["accounts"])
logger = get_logger(__name__)

SMS_LIMIT_TTL = 60  # seconds


@router.get("", response_model=list[AccountOut])
def list_accounts(db: Session = Depends(get_db), _=Depends(get_current_user)):
    return db.query(Account).order_by(Account.created_at.desc()).all()


@router.get("/today-items", response_model=list[TodayItemOut])
def today_items(_=Depends(get_current_user)):
    """当日在售商品列表，供商品配置页下拉选择使用。"""
    try:
        items = get_today_items()
    except Exception as e:
        # 既覆盖业务层的 MoutaiError（非2000返回码），也覆盖底层网络异常
        # （超时/连接失败等），避免把原始堆栈暴露给前端。
        logger.error(f"获取今日商品列表失败: {e}")
        raise HTTPException(status_code=502, detail=f"获取今日商品列表失败: {e}")
    return [
        TodayItemOut(item_id=str(i.get("itemId")), item_code=i.get("itemCode"), title=i.get("title"))
        for i in items
    ]


@router.post("", response_model=AccountOut)
def create_account(body: AccountCreate, db: Session = Depends(get_db), _=Depends(require_admin)):
    if db.query(Account).filter(Account.phone == body.phone).first():
        raise HTTPException(status_code=400, detail="手机号已存在")
    account = Account(
        phone=body.phone,
        province_name=body.province_name,
        city_name=body.city_name,
        lat=body.lat,
        lng=body.lng,
        shop_type=body.shop_type,
        random_minute=body.random_minute,
        fixed_minute=body.fixed_minute,
        device_id=generate_device_id(),
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
    for field in ("province_name", "city_name", "lat", "lng", "shop_type", "random_minute", "fixed_minute", "status"):
        value = getattr(body, field)
        if value is not None:
            setattr(account, field, value)
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
    limit_key = f"sms:limit:{account.phone}"
    if cache.exists(limit_key):
        raise HTTPException(status_code=429, detail="60秒内只能发送一次验证码")
    try:
        send_verify_code(account.phone, account.device_id)
        cache.set(limit_key, True, SMS_LIMIT_TTL)
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
        data = imaotai_login(account.phone, body.verify_code, account.device_id)
        if not data.get("token"):
            raise HTTPException(status_code=400, detail=f"登录失败: {data}")
        account.token = data["token"]
        account.cookie = data.get("cookie")
        account.user_id = data["user_id"]
        account.status = "active"
        account.last_login = datetime.utcnow()
        db.commit()
        db.refresh(account)
        return account
    except HTTPException:
        raise
    except MoutaiError as e:
        raise HTTPException(status_code=400, detail=f"登录失败: {e}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"登录失败: {e}")
