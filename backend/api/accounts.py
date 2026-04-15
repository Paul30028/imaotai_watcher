import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.deps import get_db, get_current_user, require_admin
from models.models import Account
from schemas.schemas import AccountCreate, AccountUpdate, AccountOut, VerifyLoginRequest, MessageResponse
from core.imaotai_api import send_verify_code, login as imaotai_login
from redis_client import get_redis
from utils.logger import get_logger

router = APIRouter(prefix="/accounts", tags=["accounts"])
logger = get_logger(__name__)

SMS_LIMIT_TTL = 60  # seconds


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
