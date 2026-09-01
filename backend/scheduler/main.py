"""
调度逻辑：i茅台官方申购入口只在每天 9:00-9:59 这一个小时内开放，所有账号在
同一秒并发打接口容易被限流，所以真实策略是：每个账号在这一小时内随机（或
固定）分配一个分钟，逐分钟轮询、到点才触发该账号的申购（对应
campus-imaotai 的 updateUserMinuteBatch + reservationBatchTask）。本模块驱动
四类定时任务：

  01:10                    为当日所有 active 账号分配 target_minute
  <窗口小时>:00-59 逐分钟   检查是否有账号命中当前分钟，命中则申购
  refresh_times（默认多个早晨时间点） 预热 version/session/shop 缓存
  results_query_time（默认 18:05）    查询官方公布的申购结果并回填日志

调度器现在作为 FastAPI 应用生命周期内的一个后台线程运行（见 main.py 的
lifespan），不再是独立的容器/进程，也就不需要用 Redis 心跳/队列在进程间
通信了——"立即申购"直接开一个后台线程执行，"重新排班"直接调用
reschedule()，都是同进程内的普通函数调用。
"""
import random
import threading
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from database import SessionLocal
from models.models import Account, SchedulerState
from core.purchase import run_all_purchases, run_purchase_for_accounts, confirm_all_results
from core.imaotai_api import refresh_catalogue_cache
from core.notifier import send_server_chan
from utils.logger import get_logger

logger = get_logger("scheduler")

# i茅台的申购窗口是按北京时间定义的（固定 9:00-9:59），与容器/宿主机的系统时区
# 无关（很多云主机默认是 UTC）。用固定偏移量而不是 IANA 时区名，这样不依赖
# tzdata 是否安装在镜像里，所有 cron 触发和"当前分钟"判断都显式基于这个时区。
CN_TZ = timezone(timedelta(hours=8))

_scheduler: BackgroundScheduler | None = None


def get_send_key(db) -> str:
    from models.models import AppSetting

    setting = db.query(AppSetting).filter(AppSetting.key == "notify_send_key").first()
    return setting.value if setting and setting.value else ""


def get_state(db) -> SchedulerState:
    state = db.query(SchedulerState).filter(SchedulerState.id == 1).first()
    if not state:
        state = SchedulerState(id=1)
        db.add(state)
        db.commit()
        db.refresh(state)
    return state


def _parse_hhmm(value: str, default: tuple[int, int] | None) -> tuple[int, int] | None:
    try:
        h, m = value.split(":")
        return int(h), int(m)
    except Exception:  # noqa: BLE001
        return default


# --------------------------------------------------------------------- #
# jobs
# --------------------------------------------------------------------- #
def assign_daily_minutes_job() -> None:
    """每天窗口开始前，为所有 active 账号分配今天的 target_minute。"""
    today = datetime.now(CN_TZ).date().isoformat()
    db = SessionLocal()
    try:
        accounts = db.query(Account).filter(Account.status == "active").all()
        for account in accounts:
            if account.target_minute_date == today:
                continue
            if account.random_minute:
                account.target_minute = random.randint(1, 59)
            else:
                account.target_minute = account.fixed_minute or 5
            account.target_minute_date = today
        db.commit()
        logger.info(f"已为 {len(accounts)} 个账号分配今日申购分钟")
    finally:
        db.close()


def purchase_tick_job() -> None:
    """窗口小时内每分钟触发一次，只对命中当前分钟的账号申购。"""
    now = datetime.now(CN_TZ)
    today = now.date().isoformat()
    db = SessionLocal()
    try:
        accounts = (
            db.query(Account)
            .filter(
                Account.status == "active",
                Account.target_minute == now.minute,
                Account.target_minute_date == today,
            )
            .all()
        )
        if not accounts:
            return
        logger.info(f"=== 分钟 {now.minute:02d} 命中 {len(accounts)} 个账号，开始申购 ===")
        result = run_purchase_for_accounts(accounts, db)

        state = get_state(db)
        state.last_run_at = datetime.utcnow()
        db.commit()

        send_key = get_send_key(db)
        title = f"i茅台申购：成功{result['total_success']}，失败{result['total_fail']}"
        content = f"账号数：{len(accounts)}\n成功：{result['total_success']}\n失败：{result['total_fail']}"
        send_server_chan(send_key, title, content)
        logger.info(f"=== 分钟 {now.minute:02d} 申购结束: {result} ===")
    except Exception as e:
        logger.error(f"申购任务异常: {e}")
    finally:
        db.close()


def manual_purchase_job() -> None:
    """手动"立即申购"：不看 target_minute，对全部 active 账号立即执行。"""
    logger.info("=== 手动触发：开始申购任务 ===")
    db = SessionLocal()
    try:
        result = run_all_purchases(db)
        state = get_state(db)
        state.last_run_at = datetime.utcnow()
        db.commit()
        send_key = get_send_key(db)
        title = f"i茅台申购完成（手动触发）：成功{result['total_success']}，失败{result['total_fail']}"
        content = f"成功：{result['total_success']}\n失败：{result['total_fail']}"
        send_server_chan(send_key, title, content)
        logger.info(f"=== 手动申购任务结束: {result} ===")
    except Exception as e:
        logger.error(f"手动申购任务异常: {e}")
    finally:
        db.close()


def refresh_job() -> None:
    logger.info("「刷新数据」开始刷新版本号、场次、门店缓存")
    try:
        refresh_catalogue_cache()
        logger.info("「刷新数据」完成")
    except Exception as e:
        logger.error(f"「刷新数据」执行报错: {e}")


def results_query_job() -> None:
    logger.info("=== 开始查询申购结果 ===")
    db = SessionLocal()
    try:
        result = confirm_all_results(db)
        logger.info(f"=== 申购结果查询结束: {result} ===")
    except Exception as e:
        logger.error(f"申购结果查询异常: {e}")
    finally:
        db.close()


# --------------------------------------------------------------------- #
# scheduling
# --------------------------------------------------------------------- #
def reschedule(scheduler: BackgroundScheduler) -> None:
    """读取 DB 中的调度配置并重新配置全部 job。"""
    db = SessionLocal()
    try:
        state = get_state(db)
        window_hour, _ = _parse_hhmm(state.schedule_time, (9, 0))
        results_hour, results_minute = _parse_hhmm(state.results_query_time, (18, 5))
        refresh_points = [
            _parse_hhmm(t.strip(), None)
            for t in (state.refresh_times or "").split(",")
            if t.strip()
        ]
        refresh_points = [p for p in refresh_points if p]
    finally:
        db.close()

    scheduler.remove_all_jobs()

    scheduler.add_job(
        assign_daily_minutes_job,
        CronTrigger(hour=1, minute=10, timezone=CN_TZ),
        id="assign_minutes",
        replace_existing=True,
    )
    scheduler.add_job(
        purchase_tick_job,
        CronTrigger(hour=window_hour, minute="*", timezone=CN_TZ),
        id="purchase_tick",
        replace_existing=True,
    )
    scheduler.add_job(
        results_query_job,
        CronTrigger(hour=results_hour, minute=results_minute, timezone=CN_TZ),
        id="results_query",
        replace_existing=True,
    )
    for i, (h, m) in enumerate(refresh_points):
        scheduler.add_job(
            refresh_job, CronTrigger(hour=h, minute=m, timezone=CN_TZ), id=f"refresh_{i}", replace_existing=True
        )

    logger.info(
        f"调度器已配置: 申购窗口={window_hour:02d}点, "
        f"结果查询={results_hour:02d}:{results_minute:02d}, "
        f"刷新时间点={refresh_points}"
    )


# --------------------------------------------------------------------- #
# lifecycle -- called from main.py's FastAPI lifespan
# --------------------------------------------------------------------- #
def start_scheduler() -> BackgroundScheduler:
    """启动调度器（应用启动时调用一次），返回的实例由本模块自己持有，
    is_alive()/apply_reschedule()/trigger_manual_purchase() 都基于它。"""
    global _scheduler
    _scheduler = BackgroundScheduler()
    _scheduler.start()
    reschedule(_scheduler)
    logger.info("调度器已启动（应用内后台线程）")
    return _scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None


def is_alive() -> bool:
    return _scheduler is not None and _scheduler.running


def apply_reschedule() -> None:
    """配置变更（如申购窗口小时）后调用，立即按新配置重新排班。"""
    if _scheduler is not None:
        reschedule(_scheduler)


def trigger_manual_purchase() -> None:
    """"立即申购"：在后台线程里跑，不阻塞发起请求的 HTTP 线程。"""
    threading.Thread(target=manual_purchase_job, daemon=True).start()
