import json
from unittest.mock import patch, MagicMock

import httpx
import pytest

import core.imaotai_api as imaotai_api
from core.imaotai_api import (
    MoutaiError,
    get_shops_by_province,
    login,
    pick_shop_id,
    query_results,
    reserve_item,
    send_verify_code,
)
from utils.signature import aes_decrypt


def _make_response(status_code: int) -> httpx.Response:
    request = httpx.Request("POST", "https://app.moutai519.com.cn/xhr/front/user/register/vcode")
    return httpx.Response(status_code, request=request, json={"code": status_code})


class TestRequestRetryBehavior:
    """A 4xx means the request itself won't succeed on retry -- most
    importantly 429 (rate limited), where retrying immediately just
    hammers an endpoint that already told us to back off. Only network
    failures and 5xx are worth retrying."""

    def test_429_is_not_retried(self):
        response = _make_response(429)
        with patch("core.imaotai_api.httpx.Client") as mock_client_cls, \
             patch("core.imaotai_api.time.sleep"):
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.request.return_value = response
            mock_client_cls.return_value = mock_client

            with pytest.raises(httpx.HTTPStatusError):
                imaotai_api._request("POST", "https://example.test/vcode", {})

        assert mock_client.request.call_count == 1

    def test_500_is_retried(self):
        response = _make_response(500)
        with patch("core.imaotai_api.httpx.Client") as mock_client_cls, \
             patch("core.imaotai_api.time.sleep"):
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.request.return_value = response
            mock_client_cls.return_value = mock_client

            with pytest.raises(httpx.HTTPStatusError):
                imaotai_api._request("POST", "https://example.test/vcode", {})

        assert mock_client.request.call_count == 3

    def test_network_error_is_retried(self):
        with patch("core.imaotai_api.httpx.Client") as mock_client_cls, \
             patch("core.imaotai_api.time.sleep"):
            mock_client = MagicMock()
            mock_client.__enter__.return_value = mock_client
            mock_client.request.side_effect = httpx.ConnectError("boom")
            mock_client_cls.return_value = mock_client

            with pytest.raises(httpx.ConnectError):
                imaotai_api._request("POST", "https://example.test/vcode", {})

        assert mock_client.request.call_count == 3


@patch("core.imaotai_api._cache_set", lambda *a, **k: None)
@patch("core.imaotai_api._cache_get", lambda *a, **k: None)
@patch("core.imaotai_api.get_app_version", lambda: "1.7.6")
class TestRealApiContract:
    def test_send_verify_code_success(self):
        with patch("core.imaotai_api._request", return_value={"code": 2000}) as mock_req:
            send_verify_code("13800138000", "device-1")
        args, kwargs = mock_req.call_args
        assert args[0] == "POST"
        assert args[1] == imaotai_api._VCODE_URL
        body = kwargs["json"]
        assert body["mobile"] == "13800138000"
        assert "md5" in body and "timestamp" in body

    def test_send_verify_code_failure_raises(self):
        with patch("core.imaotai_api._request", return_value={"code": 4000, "message": "手机号格式错误"}):
            try:
                send_verify_code("bad", "device-1")
                assert False, "should have raised"
            except MoutaiError:
                pass

    def test_login_success_parses_token_cookie_userid(self):
        resp = {"code": "2000", "data": {"userId": 12345, "token": "tok", "cookie": "ck"}}
        with patch("core.imaotai_api._request", return_value=resp):
            result = login("13800138000", "123456", "device-1")
        assert result == {"user_id": "12345", "token": "tok", "cookie": "ck"}

    def test_login_failure_raises(self):
        with patch("core.imaotai_api._request", return_value={"code": 4001, "message": "验证码错误"}):
            try:
                login("13800138000", "000000", "device-1")
                assert False, "should have raised"
            except MoutaiError:
                pass

    def test_get_shops_by_province_filters_by_item_id(self):
        resp = {
            "code": "2000",
            "data": {
                "shops": [
                    {
                        "shopId": "shop001",
                        "items": [
                            {"itemId": "10214", "count": 3, "inventory": 8},
                            {"itemId": "99999", "count": 1, "inventory": 1},
                        ],
                    },
                    {"shopId": "shop002", "items": [{"itemId": "10214", "count": 1, "inventory": 2}]},
                ]
            },
        }
        with patch("core.imaotai_api._request", return_value=resp), \
             patch("core.imaotai_api.get_session_id", return_value="678"):
            rows = get_shops_by_province("广东省", "10214")
        assert {r["shopId"] for r in rows} == {"shop001", "shop002"}
        assert all(r["itemId"] == "10214" for r in rows)

    def test_get_shops_by_province_error_raises(self):
        with patch("core.imaotai_api._request", return_value={"code": 5000, "message": "系统繁忙"}), \
             patch("core.imaotai_api.get_session_id", return_value="678"):
            try:
                get_shops_by_province("广东省", "10214")
                assert False, "should have raised"
            except MoutaiError:
                pass

    def test_pick_shop_id_type1_prefers_city_max_inventory(self):
        province_items = [
            {"shopId": "shop-far", "itemId": "10214", "count": 1, "inventory": 3},
            {"shopId": "shop-city-a", "itemId": "10214", "count": 1, "inventory": 5},
            {"shopId": "shop-city-b", "itemId": "10214", "count": 1, "inventory": 9},
        ]
        all_shops = {
            "shop-far": {"cityName": "广州市", "provinceName": "广东省", "lat": "23.13", "lng": "113.26"},
            "shop-city-a": {"cityName": "深圳市", "provinceName": "广东省", "lat": "22.55", "lng": "114.06"},
            "shop-city-b": {"cityName": "深圳市", "provinceName": "广东省", "lat": "22.54", "lng": "114.05"},
        }
        with patch("core.imaotai_api.get_shops_by_province", return_value=province_items), \
             patch("core.imaotai_api.get_all_shops", return_value=all_shops):
            shop_id = pick_shop_id(1, "10214", "广东省", "深圳市", "22.543099", "114.057868")
        assert shop_id == "shop-city-b"  # 深圳市内库存最高

    def test_pick_shop_id_type2_uses_nearest_in_province(self):
        province_items = [
            {"shopId": "shop-near", "itemId": "10214", "count": 1, "inventory": 1},
            {"shopId": "shop-far", "itemId": "10214", "count": 1, "inventory": 99},
        ]
        all_shops = {
            "shop-near": {"cityName": "深圳市", "provinceName": "广东省", "lat": "22.543099", "lng": "114.057868"},
            "shop-far": {"cityName": "广州市", "provinceName": "广东省", "lat": "30.0", "lng": "120.0"},
        }
        with patch("core.imaotai_api.get_shops_by_province", return_value=province_items), \
             patch("core.imaotai_api.get_all_shops", return_value=all_shops):
            shop_id = pick_shop_id(2, "10214", "广东省", "深圳市", "22.543099", "114.057868")
        assert shop_id == "shop-near"

    def test_pick_shop_id_falls_back_to_nearest_when_city_missing(self):
        province_items = [{"shopId": "shop-other-city", "itemId": "10214", "count": 1, "inventory": 5}]
        all_shops = {
            "shop-other-city": {"cityName": "广州市", "provinceName": "广东省", "lat": "23.13", "lng": "113.26"},
        }
        with patch("core.imaotai_api.get_shops_by_province", return_value=province_items), \
             patch("core.imaotai_api.get_all_shops", return_value=all_shops):
            shop_id = pick_shop_id(1, "10214", "广东省", "深圳市", "22.543099", "114.057868")
        assert shop_id == "shop-other-city"

    def test_reserve_item_encrypts_actparam_and_sets_headers(self):
        resp = {"code": 2000, "data": {"successDesc": "申购完成"}}
        with patch("core.imaotai_api._request", return_value=resp) as mock_req, \
             patch("core.imaotai_api.get_session_id", return_value="678"):
            result = reserve_item("10214", "shop001", "device-1", "tok", "12345", "22.54", "114.05")

        assert result["code"] == 2000
        args, kwargs = mock_req.call_args
        method, url, headers = args
        assert method == "POST"
        assert url == imaotai_api._RESERVE_URL
        assert headers["MT-Token"] == "tok"
        assert headers["MT-Info"] == imaotai_api._MT_INFO_HEADER
        assert headers["MT-Lat"] == "22.54"

        body = kwargs["json"]
        assert body["shopId"] == "shop001"
        assert body["sessionId"] == "678"
        decrypted = json.loads(aes_decrypt(body["actParam"]))
        assert decrypted["shopId"] == "shop001"
        assert decrypted["itemInfoList"] == [{"count": 1, "itemId": "10214"}]

    def test_reserve_item_failure_raises_with_message(self):
        with patch("core.imaotai_api._request", return_value={"code": 4009, "message": "库存不足"}), \
             patch("core.imaotai_api.get_session_id", return_value="678"):
            try:
                reserve_item("10214", "shop001", "device-1", "tok", "12345", "22.54", "114.05")
                assert False, "should have raised"
            except MoutaiError as e:
                assert "库存不足" in str(e)

    def test_query_results_filters_status(self):
        resp = {
            "code": "2000",
            "data": {
                "reservationItemVOS": [
                    {"status": 2, "itemName": "飞天茅台", "reservationTime": 1690000000000},
                    {"status": 1, "itemName": "未开奖商品"},
                ]
            },
        }
        with patch("core.imaotai_api._request", return_value=resp):
            rows = query_results("device-1", "tok")
        assert len(rows) == 2  # 过滤逻辑放在业务层(core.purchase)，这里只做原样透传
