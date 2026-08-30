import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from sqlalchemy.orm import Session

from database import SessionLocal
from models.models import Account, Product, PurchaseLog
from core.imaotai_api import pick_shop_id, reserve_item, query_results, MoutaiError
from core.notifier import send_server_chan
from utils.logger import get_logger

logger = get_logger(__name__)

_MAX_RETRIES = 3
_RETRY_INTERVAL = 1  # seconds
_AUTH_ERROR_HINTS = ("token", "登录", "未登录", "身份")


def _looks_like_auth_error(message: str) -> bool:
    lowered = (message or "").lower()
    return any(hint.lower() in lowered for hint in _AUTH_ERROR_HINTS)


def _get_send_key(db: Session) -> str:
    from models.models import AppSetting

    setting = db.query(AppSetting).filter(AppSetting.key == "notify_send_key").first()
    return setting.value if setting and setting.value else ""


def purchase_for_account(account: Account, products: list[Product], db: Session) -> dict:
    """对单个账号执行申购，返回 {success: n, fail: n}"""
    success_count = 0
    fail_count = 0

    for product in products:
        if not product.enabled:
            continue

        status = "fail"
        message = ""

        for attempt in range(_MAX_RETRIES):
            try:
                shop_id = pick_shop_id(
                    account.shop_type, product.item_code, account.province_name, account.city_name,
                    account.lat, account.lng,
                )
                result = reserve_item(
                    product.item_code, shop_id, account.device_id, account.token, account.user_id,
                    account.lat, account.lng,
                )
                status = "success"
                message = result.get("data", {}).get("successDesc", "申购成功")
                success_count += 1
                break
            except MoutaiError as e:
                message = str(e)
                logger.warning(f"[{account.phone}] {product.item_name} 第{attempt + 1}次失败: {message}")
                if _looks_like_auth_error(message):
                    break  # 认证失效重试也没用，直接跳出改走过期分支
            except Exception as e:
                message = str(e)
                logger.warning(f"[{account.phone}] {product.item_name} 第{attempt + 1}次异常: {e}")
            if attempt < _MAX_RETRIES - 1:
                time.sleep(_RETRY_INTERVAL)

        # 同一账号多个商品之间的间隔，模拟人工操作节奏、降低风控概率
        time.sleep(random.randint(3, 5))

        if status == "fail":
            fail_count += 1
            if _looks_like_auth_error(message) and account.status != "expired":
                account.status = "expired"
                db.add(account)
                send_server_chan(
                    _get_send_key(db),
                    f"{account.phone} - i茅台账号已失效",
                    f"申购时检测到 token 失效，请在账号管理页重新登录。\n错误信息：{message}",
                )

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


def _products_for_account(db: Session, account: Account) -> list[Product]:
    account_products = (
        db.query(Product).filter(Product.account_id == account.id, Product.enabled == True).all()  # noqa: E712
    )
    if account_products:
        return account_products
    return db.query(Product).filter(Product.account_id.is_(None), Product.enabled == True).all()  # noqa: E712


def _purchase_for_account_id(account_id: int) -> dict:
    """线程安全的单账号申购入口：每个线程使用自己独立的 DB Session，
    避免多线程共享同一个 SQLAlchemy Session（Session 本身非线程安全）。"""
    thread_db = SessionLocal()
    try:
        account = thread_db.query(Account).filter(Account.id == account_id).first()
        if not account:
            return {"success": 0, "fail": 0}
        products = _products_for_account(thread_db, account)
        return purchase_for_account(account, products, thread_db)
    finally:
        thread_db.close()


def run_purchase_for_accounts(accounts: list[Account], db: Session) -> dict:
    """对给定账号列表并发执行申购（供调度器按每账号 target_minute 触发调用，
    也供"立即申购"手动触发全量账号调用）。`db` 仅用于调用方读取账号列表，
    实际申购在各自线程内使用独立 Session 执行。"""
    if not accounts:
        return {"total_success": 0, "total_fail": 0}

    account_ids = [acc.id for acc in accounts]
    phones = {acc.id: acc.phone for acc in accounts}

    total_success = 0
    total_fail = 0
    with ThreadPoolExecutor(max_workers=min(len(account_ids), 5)) as executor:
        futures = {executor.submit(_purchase_for_account_id, aid): aid for aid in account_ids}
        for future in as_completed(futures):
            aid = futures[future]
            phone = phones.get(aid, str(aid))
            try:
                result = future.result()
                total_success += result["success"]
                total_fail += result["fail"]
                logger.info(f"[{phone}] 完成: 成功{result['success']}，失败{result['fail']}")
            except Exception as e:
                logger.error(f"[{phone}] 申购线程异常: {e}")

    db.expire_all()  # 各线程各自提交，让调用方 db 重新读取最新状态（如 account.status）
    return {"total_success": total_success, "total_fail": total_fail}


def run_all_purchases(db: Session) -> dict:
    """并发执行所有 active 账号的申购（手动触发 / 兼容旧调用方）。"""
    accounts = db.query(Account).filter(Account.status == "active").all()
    if not accounts:
        logger.info("无 active 账号，跳过申购")
        return {"total_success": 0, "total_fail": 0}
    return run_purchase_for_accounts(accounts, db)


def confirm_results_for_account(account: Account, db: Session) -> int:
    """调用官方申购结果查询接口，把 24 小时内公布的成功记录写入日志。
    返回本次新写入的确认记录数。"""
    if not account.token:
        return 0
    try:
        rows = query_results(account.device_id, account.token)
    except MoutaiError as e:
        logger.error(f"[{account.phone}] 查询申购结果失败: {e}")
        return 0

    written = 0
    for row in rows:
        if row.get("status") != 2:
            continue
        item_name = row.get("itemName", "")
        already = (
            db.query(PurchaseLog)
            .filter(
                PurchaseLog.account_id == account.id,
                PurchaseLog.item_name == item_name,
                PurchaseLog.status == "confirmed",
            )
            .first()
        )
        if already:
            continue
        db.add(
            PurchaseLog(
                account_id=account.id,
                item_code=str(row.get("itemId", "")),
                item_name=item_name,
                status="confirmed",
                message=f"官方结果确认：预约时间 {row.get('reservationTime')}",
            )
        )
        written += 1
    if written:
        db.commit()
    return written


def confirm_all_results(db: Session) -> dict:
    accounts = db.query(Account).filter(Account.status == "active").all()
    total = 0
    for account in accounts:
        total += confirm_results_for_account(account, db)
    if total:
        send_server_chan(_get_send_key(db), "i茅台申购结果确认", f"今日新确认 {total} 条申购成功记录，详情见申购日志。")
    return {"confirmed": total}
