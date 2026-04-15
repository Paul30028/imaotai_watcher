from fastapi import APIRouter, Depends, HTTPException
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
    parts = body.schedule_time.split(":")
    if len(parts) != 2 or not all(p.isdigit() for p in parts):
        raise HTTPException(status_code=400, detail="格式应为 HH:MM")
    state = db.query(SchedulerState).filter(SchedulerState.id == 1).first()
    if not state:
        state = SchedulerState(id=1)
        db.add(state)
    state.schedule_time = body.schedule_time
    db.commit()
    redis = get_redis()
    redis.lpush(TRIGGER_KEY, "reschedule")
    return MessageResponse(message=f"申购时间已更新为 {body.schedule_time}")
