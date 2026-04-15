import httpx
from utils.logger import get_logger

logger = get_logger(__name__)


def send_server_chan(send_key: str, title: str, content: str) -> None:
    """通过 Server酱 发送微信通知"""
    if not send_key:
        logger.warning("Server酱 SendKey 未配置，跳过通知")
        return
    url = f"https://sctapi.ftqq.com/{send_key}.send"
    try:
        resp = httpx.post(url, data={"title": title, "desp": content}, timeout=10)
        resp.raise_for_status()
        logger.info(f"Server酱 通知发送成功: {title}")
    except Exception as e:
        logger.error(f"Server酱 通知发送失败: {e}")
