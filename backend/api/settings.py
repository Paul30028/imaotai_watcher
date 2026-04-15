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
