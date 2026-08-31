from utils.signature import md5_signature, aes_encrypt, aes_decrypt, generate_device_id


def test_md5_signature_is_md5_hex():
    sign = md5_signature("13800138000", 1700000000000)
    assert len(sign) == 32
    assert sign.isalnum()


def test_md5_signature_deterministic():
    s1 = md5_signature("13800138000", 1700000000000)
    s2 = md5_signature("13800138000", 1700000000000)
    assert s1 == s2


def test_md5_signature_differs_with_different_inputs():
    s1 = md5_signature("13800138000", 1700000000000)
    s2 = md5_signature("13900139000", 1700000000000)
    assert s1 != s2

    s3 = md5_signature("13800138000", 1700000000000)
    s4 = md5_signature("13800138000", 1700000000001)
    assert s3 != s4


def test_aes_encrypt_decrypt_roundtrip():
    plain = '{"itemId":"10214","sessionId":"678","userId":"12345","shopId":"233331084001"}'
    cipher_text = aes_encrypt(plain)
    assert cipher_text != plain
    assert aes_decrypt(cipher_text) == plain


def test_aes_encrypt_is_base64():
    import base64

    cipher_text = aes_encrypt("hello")
    # should not raise
    base64.b64decode(cipher_text)


def test_generate_device_id_format():
    device_id = generate_device_id()
    assert len(device_id) == 36  # UUID with hyphens
    assert device_id == device_id.lower()
