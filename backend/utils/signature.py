import hashlib
import uuid

# 茅台 APP signing secret key (public value from reverse engineering)
_APP_SECRET = "2af72f100c356273d46284f6fd1dfc08"


def generate_sign(device_id: str, timestamp: str) -> str:
    """Generate MD5 signature: MD5(device_id + timestamp + APP_SECRET)"""
    raw = device_id + timestamp + _APP_SECRET
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def generate_device_id() -> str:
    """Generate a random UUID as device ID"""
    return str(uuid.uuid4())
