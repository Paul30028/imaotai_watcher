import hashlib
import uuid


def generate_mt_r(path: str, timestamp: str, device_id: str) -> str:
    """mt-r 签名：MD5(path + timestamp + device_id)"""
    raw = path + timestamp + device_id
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def generate_mt_k(path: str, timestamp: str, device_id: str, user_id: str = "") -> str:
    """mt-k 签名：MD5(path + timestamp + device_id + user_id)"""
    raw = path + timestamp + device_id + user_id
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def generate_device_id() -> str:
    """生成随机设备 ID"""
    return str(uuid.uuid4())
