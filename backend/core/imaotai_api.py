import httpx
from utils.signature import generate_sign
from utils.time_sync import get_timestamp
from utils.logger import get_logger

logger = get_logger(__name__)

_BASE_URL = "https://api.moutai519.com.cn"
_APP_VERSION = "1.4.1"
_MT_INFO = "028e7f96f6369cafe1d105579c5b9377"


def _build_headers(device_id: str, token: str | None = None) -> dict:
    ts = get_timestamp()
    headers = {
        "MT-Device-ID": device_id,
        "MT-Timestamp": ts,
        "MT-Sign": generate_sign(device_id, ts),
        "MT-APP-Version": _APP_VERSION,
        "MT-Info": _MT_INFO,
        "User-Agent": "iOS;16.3;Apple;iPhone 15",
        "Content-Type": "application/json",
    }
    if token:
        headers["MT-Token-V3"] = token
    return headers


def _post(path: str, body: dict, device_id: str, token: str | None = None) -> dict:
    url = _BASE_URL + path
    headers = _build_headers(device_id, token)
    with httpx.Client(timeout=10) as client:
        resp = client.post(url, json=body, headers=headers)
        resp.raise_for_status()
        return resp.json()


def _get(path: str, device_id: str, token: str | None = None, params: dict | None = None) -> dict:
    url = _BASE_URL + path
    headers = _build_headers(device_id, token)
    with httpx.Client(timeout=10) as client:
        resp = client.get(url, headers=headers, params=params)
        resp.raise_for_status()
        return resp.json()


def send_verify_code(phone: str, device_id: str) -> dict:
    """发送短信验证码"""
    return _post(
        "/game/outside/user/sendVerifyCode/v2",
        {"mobile": phone},
        device_id,
    )


def login(phone: str, verify_code: str, device_id: str) -> dict:
    """验证码登录，返回 token 等信息"""
    return _post(
        "/game/outside/user/login/v2",
        {"mobile": phone, "verifyCode": verify_code, "deviceId": device_id},
        device_id,
    )


def get_current_session(device_id: str, token: str) -> int:
    """获取当前销售 sessionId"""
    data = _get("/game/outside/mall/sessions/v2", device_id, token)
    sessions = data.get("data", {}).get("sessions", [])
    if not sessions:
        raise ValueError("No active sessions found")
    return sessions[0]["sessionId"]


def get_shops(city_code: str, item_code: str, device_id: str, token: str) -> list[dict]:
    """获取指定城市+商品的门店列表"""
    data = _get(
        "/game/outside/mall/shop/list/slim/v4",
        device_id,
        token,
        params={"cityCode": city_code, "itemCode": item_code},
    )
    return data.get("data", {}).get("shopList", [])


def reserve(
    item_code: str,
    session_id: int,
    shop_code: str,
    device_id: str,
    token: str,
) -> dict:
    """提交申购"""
    return _post(
        "/game/outside/user/retailer/appoint/v2",
        {"itemCode": item_code, "sessionId": session_id, "shopCode": shop_code},
        device_id,
        token,
    )
