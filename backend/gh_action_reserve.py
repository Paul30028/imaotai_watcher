"""
Standalone entrypoint for running reservations from GitHub Actions instead of
the self-hosted Docker container.

Why this exists: the Docker deployment makes every request from whatever
network the container's host is on. If that network's IP gets rate-limited
by the real i茅台 backend (observed firsthand: repeated 429s that persisted
across a full day of testing from one home connection), every account behind
it is stuck regardless of how correct the request itself is. Running from
GitHub's own runners sidesteps that -- each run gets a fresh datacenter IP
unrelated to the user's home network. (Pattern confirmed against
397179459/iMaoTai-reserve, an actively scheduled Actions-based tool with
485+ stars.)

This is deliberately independent of the FastAPI app/SQLite database: it only
imports the plain-Python `core`/`utils` modules (no fastapi/sqlalchemy), so
it has nothing else to set up in a CI runner. Account data doesn't live in
the container's database here -- it's supplied via the IMAOTAI_ACCOUNTS env
var (a GitHub Actions secret), because a CI runner has no access to the
container's SQLite file. The one-time login step (phone -> SMS code -> token)
still happens through the existing Docker web UI; its output (device_id,
token, user_id) is what you copy into that secret.

Usage: run from the `backend/` directory (so `core`/`utils` resolve), with
IMAOTAI_ACCOUNTS set to a JSON array, e.g.:

[
  {
    "phone": "13800138000",
    "device_id": "...",
    "token": "...",
    "user_id": "...",
    "item_ids": ["10214"],
    "shop_id": "AUTO",
    "shop_type": 1,
    "province": "广东省",
    "city": "深圳市",
    "lat": "22.543099",
    "lng": "114.057868"
  }
]

shop_id "AUTO" resolves via pick_shop_id(shop_type, ...) same as the web
app's account config; a concrete shop id is used as-is instead.
"""
from __future__ import annotations

import json
import os
import random
import sys
import time

from core.imaotai_api import MoutaiError, pick_shop_id, reserve_item
from core.notifier import send_server_chan
from utils.logger import get_logger

logger = get_logger(__name__)

_MAX_RETRIES = 3
_RETRY_INTERVAL = 1  # seconds
_AUTH_ERROR_HINTS = ("token", "登录", "未登录", "身份")


def _looks_like_auth_error(message: str) -> bool:
    lowered = (message or "").lower()
    return any(hint.lower() in lowered for hint in _AUTH_ERROR_HINTS)


def _mask_phone(phone: str) -> str:
    return phone[:3] + "****" + phone[7:] if len(phone) == 11 else phone


def _reserve_one(account: dict, item_id: str) -> tuple[bool, str]:
    shop_id = account["shop_id"]
    if shop_id == "AUTO":
        try:
            shop_id = pick_shop_id(
                account["shop_type"], item_id, account["province"], account["city"],
                account["lat"], account["lng"],
            )
        except MoutaiError as e:
            return False, f"选店失败: {e}"

    message = ""
    for attempt in range(_MAX_RETRIES):
        try:
            result = reserve_item(
                item_id, shop_id, account["device_id"], account["token"], account["user_id"],
                account["lat"], account["lng"],
            )
            return True, result.get("data", {}).get("successDesc", "申购成功")
        except MoutaiError as e:
            message = str(e)
            logger.warning("[%s] 商品%s 第%d次失败: %s", _mask_phone(account["phone"]), item_id, attempt + 1, message)
            if _looks_like_auth_error(message):
                break
        except Exception as e:  # noqa: BLE001
            message = str(e)
            logger.warning("[%s] 商品%s 第%d次异常: %s", _mask_phone(account["phone"]), item_id, attempt + 1, e)
        if attempt < _MAX_RETRIES - 1:
            time.sleep(_RETRY_INTERVAL)
    return False, message


def run(accounts: list[dict]) -> tuple[int, int, list[str]]:
    total_success = 0
    total_fail = 0
    lines: list[str] = []

    for account in accounts:
        phone = _mask_phone(account.get("phone", "?"))
        for item_id in account.get("item_ids", []):
            ok, message = _reserve_one(account, item_id)
            status = "✅ 成功" if ok else "❌ 失败"
            line = f"{status} [{phone}] 商品{item_id}: {message}"
            logger.info(line)
            lines.append(line)
            if ok:
                total_success += 1
            else:
                total_fail += 1
            # 同一账号多个商品之间的间隔，与 Docker 版 core/purchase.py 保持一致
            time.sleep(random.randint(3, 5))

    return total_success, total_fail, lines


def main() -> int:
    raw = os.environ.get("IMAOTAI_ACCOUNTS", "")
    if not raw.strip():
        logger.error("IMAOTAI_ACCOUNTS 环境变量未设置或为空")
        return 1
    try:
        accounts = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error("IMAOTAI_ACCOUNTS 不是合法 JSON: %s", e)
        return 1
    if not isinstance(accounts, list) or not accounts:
        logger.error("IMAOTAI_ACCOUNTS 必须是非空的账号数组")
        return 1

    success, fail, lines = run(accounts)
    logger.info("完成：成功 %d，失败 %d", success, fail)

    send_key = os.environ.get("SERVERCHAN_KEY", "")
    if send_key:
        send_server_chan(
            send_key,
            f"i茅台申购完成：成功{success} 失败{fail}",
            "\n\n".join(lines) or "（本次没有配置任何商品）",
        )

    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
