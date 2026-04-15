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
