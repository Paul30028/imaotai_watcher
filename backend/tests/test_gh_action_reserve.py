import json
from unittest.mock import patch

import gh_action_reserve as ghr
from core.imaotai_api import MoutaiError

_ACCOUNT = {
    "phone": "13800138000",
    "device_id": "device-1",
    "token": "tok",
    "user_id": "12345",
    "item_ids": ["10214"],
    "shop_id": "shop001",
    "shop_type": 1,
    "province": "广东省",
    "city": "深圳市",
    "lat": "22.54",
    "lng": "114.05",
}


@patch("gh_action_reserve.time.sleep", lambda *a: None)
class TestRun:
    def test_all_success(self):
        with patch("gh_action_reserve.reserve_item", return_value={"data": {"successDesc": "申购完成"}}):
            success, fail, lines = ghr.run([_ACCOUNT])
        assert (success, fail) == (1, 0)
        assert "成功" in lines[0]

    def test_reserve_failure_counts_and_does_not_raise(self):
        with patch("gh_action_reserve.reserve_item", side_effect=MoutaiError("库存不足")):
            success, fail, lines = ghr.run([_ACCOUNT])
        assert (success, fail) == (0, 1)
        assert "失败" in lines[0]

    def test_auth_error_stops_retrying_early(self):
        with patch("gh_action_reserve.reserve_item", side_effect=MoutaiError("token 已失效")) as mock_reserve:
            ghr.run([_ACCOUNT])
        assert mock_reserve.call_count == 1  # 不是 _MAX_RETRIES 次

    def test_shop_id_auto_resolves_via_pick_shop_id(self):
        account = {**_ACCOUNT, "shop_id": "AUTO"}
        with patch("gh_action_reserve.pick_shop_id", return_value="shop999") as mock_pick, \
             patch("gh_action_reserve.reserve_item", return_value={"data": {}}) as mock_reserve:
            ghr.run([account])
        mock_pick.assert_called_once_with(1, "10214", "广东省", "深圳市", "22.54", "114.05")
        assert mock_reserve.call_args[0][1] == "shop999"

    def test_fixed_shop_id_skips_pick_shop_id(self):
        with patch("gh_action_reserve.pick_shop_id") as mock_pick, \
             patch("gh_action_reserve.reserve_item", return_value={"data": {}}):
            ghr.run([_ACCOUNT])
        mock_pick.assert_not_called()


class TestMain:
    def test_missing_env_returns_1(self, monkeypatch):
        monkeypatch.delenv("IMAOTAI_ACCOUNTS", raising=False)
        assert ghr.main() == 1

    def test_invalid_json_returns_1(self, monkeypatch):
        monkeypatch.setenv("IMAOTAI_ACCOUNTS", "not json")
        assert ghr.main() == 1

    def test_empty_array_returns_1(self, monkeypatch):
        monkeypatch.setenv("IMAOTAI_ACCOUNTS", "[]")
        assert ghr.main() == 1

    def test_success_returns_0(self, monkeypatch):
        monkeypatch.setenv("IMAOTAI_ACCOUNTS", json.dumps([_ACCOUNT]))
        monkeypatch.delenv("SERVERCHAN_KEY", raising=False)
        with patch("gh_action_reserve.reserve_item", return_value={"data": {}}), \
             patch("gh_action_reserve.time.sleep", lambda *a: None):
            assert ghr.main() == 0

    def test_any_failure_returns_1_and_notifies(self, monkeypatch):
        monkeypatch.setenv("IMAOTAI_ACCOUNTS", json.dumps([_ACCOUNT]))
        monkeypatch.setenv("SERVERCHAN_KEY", "fake-key")
        with patch("gh_action_reserve.reserve_item", side_effect=MoutaiError("库存不足")), \
             patch("gh_action_reserve.time.sleep", lambda *a: None), \
             patch("gh_action_reserve.send_server_chan") as mock_notify:
            assert ghr.main() == 1
        mock_notify.assert_called_once()
