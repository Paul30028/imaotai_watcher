"""
Client for the real i茅台 (i-Moutai) app-backend HTTP API.

Endpoints, headers and the AES/MD5 signing scheme were reverse-engineered
from oddfar/campus-imaotai (IMTServiceImpl.java / IShopServiceImpl.java) and
validated independently (AES round-trip + MD5 signature unit tests).

This replaces the previous version of this module, which called an invented
endpoint contract (`/sendCode`, `/login`, `/shops?cityCode=`, `/reservation`)
that the real backend never accepted.
"""
from __future__ import annotations

import json
import math
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from utils.logger import get_logger
from utils.memcache import cache
from utils.signature import aes_encrypt, md5_signature

logger = get_logger(__name__)

_ITUNES_LOOKUP_URL = "https://itunes.apple.com/cn/lookup?id=1600482450"
_APP_BASE = "https://app.moutai519.com.cn"
_STATIC_BASE = "https://static.moutai519.com.cn/mt-backend"
_VCODE_URL = f"{_APP_BASE}/xhr/front/user/register/vcode"
_LOGIN_URL = f"{_APP_BASE}/xhr/front/user/register/login"
_RESOURCE_URL = f"{_STATIC_BASE}/xhr/front/mall/resource/get"
_SESSION_URL = f"{_STATIC_BASE}/xhr/front/mall/index/session/get/{{day_ts}}"
_PROVINCE_SHOPS_URL = f"{_STATIC_BASE}/xhr/front/mall/shop/list/slim/v3/{{session_id}}/{{province}}/{{item_id}}/{{day_ts}}"
_RESERVE_URL = f"{_APP_BASE}/xhr/front/mall/reservation/add"
_RESULTS_URL = f"{_APP_BASE}/xhr/front/mall/reservation/list/pageOne/queryV2"

# Fixed device-info header the app sends on every call, captured from a live
# app session. If requests start failing with an MT-Info related error, this
# needs to be re-extracted from a current app build.
_MT_INFO_HEADER = "028e7f96f6369cafe1d105579c5b9377"
_USER_AGENT = "iOS;16.3;Apple;?unrecognized?"
_MT_BUNDLE_ID = "com.moutai.mall"

# MT-R/MT-SN are opaque, base64-looking anti-fraud tokens. Cross-checked
# against AkenClub/ken-iMoutai-Script (an actively maintained, independently
# written Python client with confirmed real reservation successes): that
# client sends these two ONLY on the results-query endpoint, as this same
# static pair -- and never on vcode/login/reserve. So they're not required
# everywhere, and a hardcoded value is apparently accepted there in practice.
_MT_R_HEADER = "clips_OlU6TmFRag5rCXwbNAQ/Tz1SKlN8THcecBp/HGhHdw=="
_MT_SN_HEADER = "clips_ehwpSC0fLBggRnJAdxYgFiAYLxl9Si5PfEl/TC0afkw="
_PROXY = os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy") or None
_TIMEOUT = 10

_CACHE_TTL_VERSION = 24 * 3600
_CACHE_TTL_SESSION = 2 * 3600
_CACHE_TTL_SHOPS = 2 * 3600
_CACHE_TTL_PROVINCE = 60 * 60

_CACHE_PREFIX = "imaotai:cache:"


class MoutaiError(RuntimeError):
    """Raised when the i茅台 API returns a non-success code."""


# --------------------------------------------------------------------- #
# shared cache: in-process, since the scheduler now runs as a background
# thread inside the same API process instead of a separate container.
# --------------------------------------------------------------------- #
def _cache_get(key: str) -> Any | None:
    return cache.get(_CACHE_PREFIX + key)


def _cache_set(key: str, value: Any, ttl: int) -> None:
    cache.set(_CACHE_PREFIX + key, value, ttl)


def _day_start_ms() -> int:
    """Milliseconds since epoch for today 00:00 in UTC+8 (China)."""
    tz8 = timezone(timedelta(hours=8))
    start = datetime.now(tz8).replace(hour=0, minute=0, second=0, microsecond=0)
    return int(start.timestamp() * 1000)


_RETRY_DELAYS = [1, 2]  # seconds, applied after the first attempt


def _is_retryable(exc: Exception) -> bool:
    """4xx responses (bad request, auth, and critically 429 rate-limit) won't
    succeed on an identical retry -- retrying them just hammers an endpoint
    that already told us to back off. Only network-layer failures and 5xx
    server errors are worth retrying."""
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500
    return True


def _request(method: str, url: str, headers: dict, **kwargs) -> dict:
    last_exc: Exception | None = None
    for attempt, delay in enumerate([0] + _RETRY_DELAYS):
        if delay:
            time.sleep(delay)
        try:
            with httpx.Client(timeout=_TIMEOUT, proxy=_PROXY) as client:
                resp = client.request(method, url, headers=headers, **kwargs)
                resp.raise_for_status()
                return resp.json()
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            logger.warning("%s %s 第%d次失败: %s", method, url, attempt + 1, exc)
            if not _is_retryable(exc):
                break
    raise last_exc  # type: ignore[misc]


# --------------------------------------------------------------------- #
# app version
# --------------------------------------------------------------------- #
_FALLBACK_APP_VERSION = "1.9.7"


def get_app_version() -> str:
    """The real app sends its App Store version in MT-APP-Version on every
    call; a stale/missing one is a confirmed rejection cause (oddfar/
    campus-imaotai#394 -> #397: an HTML-scraping regex against the App
    Store page broke silently after Apple redesigned it to a JS-rendered
    SPA, sent MT-APP-Version: null, and got code 4821 back). That fix
    switched to the iTunes lookup API, which both AkenClub/ken-iMoutai-
    Script and 397179459/iMaoTai-reserve also use -- real JSON, not HTML
    scraping, so it isn't exposed to future page-markup changes the same
    way. Same approach here."""
    cached = _cache_get("version")
    if cached:
        return cached
    version = _FALLBACK_APP_VERSION
    try:
        with httpx.Client(timeout=_TIMEOUT, proxy=_PROXY) as client:
            resp = client.get(_ITUNES_LOOKUP_URL)
            resp.raise_for_status()
        results = resp.json().get("results") or []
        if results and results[0].get("version"):
            version = results[0]["version"]
        else:
            logger.warning("iTunes lookup 返回空结果，使用回退版本号 %s", version)
    except Exception as e:  # noqa: BLE001
        logger.warning("获取 App 版本号失败，使用回退版本号 %s: %s", version, e)
    _cache_set("version", version, _CACHE_TTL_VERSION)
    return version


def _auth_headers(device_id: str) -> dict:
    """vcode/login only need this minimal set -- confirmed against
    AkenClub/ken-iMoutai-Script (actively maintained, real confirmed
    reservation successes). The earlier full header set (MT-Bundle-ID,
    MT-Info, MT-K, MT-R, MT-Lat/Lng, ...) copied from a closed-source GUI
    reference was never actually required here and just added surface
    area for something to go wrong."""
    return {
        "MT-Device-ID": device_id,
        "MT-APP-Version": get_app_version(),
        "User-Agent": _USER_AGENT,
        "Content-Type": "application/json",
    }


def _reserve_headers(device_id: str, token: str, user_id: str, lat: str, lng: str) -> dict:
    return {
        "User-Agent": _USER_AGENT,
        "MT-Token": token,
        "MT-Network-Type": "WIFI",
        "MT-User-Tag": "0",
        "MT-K": str(int(time.time() * 1000)),
        "MT-Info": _MT_INFO_HEADER,
        "MT-APP-Version": get_app_version(),
        "Accept-Language": "zh-Hans-CN;q=1",
        "MT-Device-ID": device_id,
        "MT-Bundle-ID": _MT_BUNDLE_ID,
        "MT-Lng": lng,
        "MT-Lat": lat,
        "Content-Type": "application/json",
        "userId": str(user_id),
    }


def _query_headers(device_id: str, token: str) -> dict:
    return {
        "MT-Device-ID": device_id,
        "MT-APP-Version": get_app_version(),
        "MT-Token": token,
        "MT-Network-Type": "WIFI",
        "MT-User-Tag": "0",
        "MT-K": str(int(time.time() * 1000)),
        "MT-Bundle-ID": _MT_BUNDLE_ID,
        "MT-R": _MT_R_HEADER,
        "MT-SN": _MT_SN_HEADER,
    }


# --------------------------------------------------------------------- #
# auth
# --------------------------------------------------------------------- #
def send_verify_code(phone: str, device_id: str) -> None:
    ts = int(time.time() * 1000)
    body = {"mobile": phone, "md5": md5_signature(phone, ts), "timestamp": str(ts)}
    result = _request("POST", _VCODE_URL, _auth_headers(device_id), json=body)
    if str(result.get("code")) != "2000":
        raise MoutaiError(f"发送验证码失败: {result}")


def login(phone: str, verify_code: str, device_id: str) -> dict:
    """Returns {userId, token, cookie}."""
    ts = int(time.time() * 1000)
    body = {
        "mobile": phone,
        "vCode": verify_code,
        "md5": md5_signature(phone + verify_code, ts),
        "timestamp": str(ts),
        "MT-APP-Version": get_app_version(),
    }
    result = _request("POST", _LOGIN_URL, _auth_headers(device_id), json=body)
    if str(result.get("code")) != "2000":
        raise MoutaiError(f"登录失败: {result}")
    data = result["data"]
    return {
        "user_id": str(data.get("userId")),
        "token": data.get("token"),
        "cookie": data.get("cookie"),
    }


# --------------------------------------------------------------------- #
# catalogue: session id + today's items, full shop directory, per-province
# inventory
# --------------------------------------------------------------------- #
def get_session_data() -> dict:
    cached = _cache_get("session_data")
    if cached:
        return cached
    url = _SESSION_URL.format(day_ts=_day_start_ms())
    result = _request("GET", url, {"User-Agent": _USER_AGENT})
    if str(result.get("code")) != "2000":
        raise MoutaiError(f"获取场次信息失败: {result}")
    data = result["data"]
    _cache_set("session_data", data, _CACHE_TTL_SESSION)
    return data


def get_session_id() -> str:
    return str(get_session_data()["sessionId"])


def get_today_items() -> list[dict]:
    """[{itemId, itemCode, title, ...}] on sale today."""
    return get_session_data().get("itemList", [])


def get_all_shops() -> dict[str, dict]:
    """shopId -> {provinceName, cityName, districtName, fullAddress, lat, lng, name, tenantName}"""
    cached = _cache_get("shops")
    if cached:
        return cached
    resource = _request("GET", _RESOURCE_URL, {"User-Agent": _USER_AGENT})
    shop_url = resource["data"]["mtshops_pc"]["url"]
    with httpx.Client(timeout=_TIMEOUT, proxy=_PROXY) as client:
        shops = client.get(shop_url).json()
    _cache_set("shops", shops, _CACHE_TTL_SHOPS)
    return shops


def get_shops_by_province(province: str, item_id: str) -> list[dict]:
    """[{shopId, itemId, count, inventory}] carrying item_id in province, today."""
    cache_key = f"province:{province}:{get_session_id()}:{item_id}"
    cached = _cache_get(cache_key)
    if cached:
        return cached
    url = _PROVINCE_SHOPS_URL.format(
        session_id=get_session_id(), province=province, item_id=item_id, day_ts=_day_start_ms()
    )
    result = _request("GET", url, {"User-Agent": _USER_AGENT})
    if str(result.get("code")) != "2000":
        raise MoutaiError(f"查询所在省市投放信息失败: {result}")
    rows = []
    for shop in result["data"].get("shops", []):
        for item in shop.get("items", []):
            if str(item.get("itemId")) == str(item_id):
                rows.append(
                    {
                        "shopId": shop["shopId"],
                        "itemId": item["itemId"],
                        "count": item.get("count", 0),
                        "inventory": item.get("inventory", 0),
                    }
                )
    _cache_set(cache_key, rows, _CACHE_TTL_PROVINCE)
    return rows


# --------------------------------------------------------------------- #
# shop selection
# --------------------------------------------------------------------- #
def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6378137.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = p1 - p2
    dlng = math.radians(lng1) - math.radians(lng2)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlng / 2) ** 2
    return 2 * math.asin(math.sqrt(a)) * r


def pick_shop_id(shop_type: int, item_id: str, province: str, city: str, lat: str, lng: str) -> str:
    province_items = get_shops_by_province(province, item_id)
    if not province_items:
        raise MoutaiError("该省份今日无该商品在售门店")
    candidate_ids = {row["shopId"] for row in province_items}
    all_shops = get_all_shops()
    candidates = {sid: all_shops[sid] for sid in candidate_ids if sid in all_shops}

    shop_id = None
    if shop_type == 1:
        city_rows = [
            row for row in province_items if city in (candidates.get(row["shopId"], {}).get("cityName") or "")
        ]
        city_rows.sort(key=lambda r: r["inventory"], reverse=True)
        if city_rows:
            shop_id = city_rows[0]["shopId"]

    if not shop_id:
        province_shops = [(sid, s) for sid, s in candidates.items() if province in (s.get("provinceName") or "")]
        if not province_shops:
            raise MoutaiError("申购时根据类型获取的门店为空")
        my_lat, my_lng = float(lat), float(lng)
        province_shops.sort(key=lambda pair: _haversine_m(my_lat, my_lng, float(pair[1]["lat"]), float(pair[1]["lng"])))
        shop_id = province_shops[0][0]

    return shop_id


# --------------------------------------------------------------------- #
# reservation
# --------------------------------------------------------------------- #
def reserve_item(
    item_id: str,
    shop_id: str,
    device_id: str,
    token: str,
    user_id: str,
    lat: str,
    lng: str,
) -> dict:
    payload = {
        "itemInfoList": [{"count": 1, "itemId": item_id}],
        "sessionId": get_session_id(),
        "userId": user_id,
        "shopId": shop_id,
    }
    payload["actParam"] = aes_encrypt(json.dumps(payload, separators=(",", ":")))

    headers = _reserve_headers(device_id, token, user_id, lat, lng)
    result = _request("POST", _RESERVE_URL, headers, json=payload)
    if str(result.get("code")) != "2000":
        raise MoutaiError(result.get("message", str(result)))
    return result


def query_results(device_id: str, token: str) -> list[dict]:
    headers = _query_headers(device_id, token)
    result = _request("GET", _RESULTS_URL, headers)
    if str(result.get("code")) != "2000":
        raise MoutaiError(result.get("message", str(result)))
    return result.get("data", {}).get("reservationItemVOS", []) or []


def refresh_catalogue_cache() -> None:
    """Force a re-fetch of version/session/shop data (used by the morning
    warm-up jobs so the reservation window doesn't pay the fetch cost)."""
    cache.delete(_CACHE_PREFIX + "version", _CACHE_PREFIX + "session_data", _CACHE_PREFIX + "shops")
    get_app_version()
    get_session_id()
    get_all_shops()
