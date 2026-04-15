import time


def get_timestamp() -> str:
    """Return current Unix timestamp as string (second precision)"""
    return str(int(time.time()))
