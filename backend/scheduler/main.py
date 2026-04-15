"""
独立调度器进程。
- BackgroundScheduler 在后台线程执行定时申购
- 主线程循环更新 Redis 心跳 + BRPOP 等待手动触发
- 接收 'reschedule' 消息时从 DB 读取最新 schedule_time 重新配置 job
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from datetime import datetime
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
    """从 AppSetting 表获取 notify_send_key"""
    setting = db.query(AppSetting).filter(AppSetting.key == "notify_send_key").first()
    return setting.value if setting and setting.value else ""


def purchase_job() -> None:
    """定时申购任务"""
    logger.info("=== 开始申购任务 ===")
    db = SessionLocal()
    try:
        result = run_all_purchases(db)

        # 更新 last_run_at
        state = db.query(SchedulerState).filter(SchedulerState.id == 1).first()
        if state:
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


def reschedule(scheduler: BackgroundScheduler) -> None:
    """读取 DB 中的 schedule_time 并重新配置 cron job"""
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


def main() -> None:
    """主程序入口"""
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
            if message == b"reschedule":
                logger.info("收到 reschedule 指令，重新配置调度时间")
                reschedule(scheduler)
            else:
                logger.info("收到手动触发指令，立即执行申购")
                purchase_job()


if __name__ == "__main__":
    main()
