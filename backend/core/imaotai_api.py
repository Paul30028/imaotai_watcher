import os

import httpx
from utils.signature import generate_mt_k, generate_mt_r
from utils.time_sync import get_timestamp
from utils.logger import get_logger

logger = get_logger(__name__)

_BASE_URL = "https://app.moutai519.com.cn"
_APP_VERSION = "1.7.6"
_PROXY = os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy") or None

_RETRY_DELAYS = [1, 2, 4]


def _build_headers(path: str, device_id: str, token: str | None = None, user_id: str = "") -> dict:
    ts = get_timestamp()
    headers = {
        "MT-Device-ID": device_id,
        "MT-APP-Version": _APP_VERSION,
        "mt-r": generate_mt_r(path, ts, device_id),
        "mt-k": generate_mt_k(path, ts, device_id, user_id),
        "Content-Type": "application/json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _post(path: str, body: dict, device_id: str, token: str | None = None, user_id: str = "") -> dict:
    url = _BASE_URL + path
    headers = _build_headers(path, device_id, token, user_id)
    last_exc: Exception | None = None
    for i, delay in enumerate([0] + _RETRY_DELAYS):
        if delay:
            import time
            time.sleep(delay)
        try:
            with httpx.Client(timeout=10, proxy=_PROXY) as client:
                resp = client.post(url, json=body, headers=headers)
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            last_exc = e
            logger.warning(f"POST {path} 第{i+1}次失败: {e}")
    raise last_exc  # type: ignore[misc]


def _get(path: str, device_id: str, token: str | None = None, user_id: str = "", params: dict | None = None) -> dict:
    url = _BASE_URL + path
    headers = _build_headers(path, device_id, token, user_id)
    last_exc: Exception | None = None
    for i, delay in enumerate([0] + _RETRY_DELAYS):
        if delay:
            import time
            time.sleep(delay)
        try:
            with httpx.Client(timeout=10, proxy=_PROXY) as client:
                resp = client.get(url, headers=headers, params=params)
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            last_exc = e
            logger.warning(f"GET {path} 第{i+1}次失败: {e}")
    raise last_exc  # type: ignore[misc]


def send_verify_code(phone: str, device_id: str) -> dict:
    """发送短信验证码"""
    return _post("/sendCode", {"mobile": phone}, device_id)


def login(phone: str, verify_code: str, device_id: str) -> dict:
    """验证码登录，返回包含 token 和 userId 的数据"""
    return _post(
        "/login",
        {"mobile": phone, "verifyCode": verify_code, "deviceId": device_id},
        device_id,
    )


def get_items(device_id: str, token: str, user_id: str) -> list[dict]:
    """获取可申购商品列表"""
    data = _get("/items", device_id, token, user_id)
    return data.get("data", {}).get("items", [])


def get_shops(city_code: str, device_id: str, token: str, user_id: str) -> list[dict]:
    """获取指定城市的门店列表"""
    data = _get("/shops", device_id, token, user_id, params={"cityCode": city_code})
    return data.get("data", {}).get("shops", [])


def reserve(item_id: str, shop_id: str, device_id: str, token: str, user_id: str) -> dict:
    """提交申购"""
    return _post(
        "/reservation",
        {"itemId": item_id, "shopId": shop_id},
        device_id,
        token,
        user_id,
    )
