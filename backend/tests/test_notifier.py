from unittest.mock import patch, MagicMock
from core.notifier import send_server_chan


def test_send_server_chan_calls_correct_url():
    with patch("httpx.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200)
        send_server_chan("test_key", "测试标题", "测试内容")
        call_args = mock_post.call_args
        assert "test_key" in call_args[0][0]
        assert call_args[1]["data"]["title"] == "测试标题"


def test_send_server_chan_no_key_skips():
    with patch("httpx.post") as mock_post:
        send_server_chan("", "标题", "内容")
        mock_post.assert_not_called()
