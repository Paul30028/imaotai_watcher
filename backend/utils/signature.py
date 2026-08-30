"""
Signing/encryption helpers for the real i茅台 (i-Moutai) app backend.

Reverse-engineered from oddfar/campus-imaotai (IMTServiceImpl.java):
  - vcode/login calls are signed with MD5(salt + content + timestamp)
  - the reservation call additionally AES-256-CBC encrypts its own JSON body
    into an `actParam` field, using a key/iv that are baked into the app
    itself (not per-account secrets).

The previous version of this module (`generate_mt_r`/`generate_mt_k`) signed
against an invented endpoint contract that the real backend never accepted.
"""
import base64
import hashlib
import uuid

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

SALT = "2af72f100c356273d46284f6fd1dfc08"
AES_KEY = b"qbhajinldepmucsonaaaccgypwuvcjaa"
AES_IV = b"2018534749963515"


def md5_signature(content: str, timestamp: int | str) -> str:
    """MD5(salt + content + timestamp); content is `mobile` for /vcode and
    `mobile + vCode` for /login."""
    text = f"{SALT}{content}{timestamp}"
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def aes_encrypt(plain_text: str) -> str:
    cipher = AES.new(AES_KEY, AES.MODE_CBC, AES_IV)
    return base64.b64encode(cipher.encrypt(pad(plain_text.encode("utf-8"), AES.block_size))).decode("utf-8")


def aes_decrypt(cipher_text: str) -> str:
    cipher = AES.new(AES_KEY, AES.MODE_CBC, AES_IV)
    raw = base64.b64decode(cipher_text)
    return unpad(cipher.decrypt(raw), AES.block_size).decode("utf-8")


def generate_device_id() -> str:
    """Random device id, generated once per account at creation time and
    persisted from then on (the real backend ties a device id to a login
    session)."""
    return str(uuid.uuid4()).lower()
