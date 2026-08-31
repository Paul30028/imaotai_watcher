from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from api.deps import get_db, get_current_user
from models.models import PurchaseLog, Account
from schemas.schemas import LogsResponse, StatsResponse

router = APIRouter(prefix="/logs", tags=["logs"])


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
    # 单用户本地应用，这几条 COUNT 查询开销很小，不再需要额外缓存层。
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

    return StatsResponse(
        total_accounts=total_accounts,
        today_success=today_success,
        today_fail=today_fail,
        trend=trend,
    )
