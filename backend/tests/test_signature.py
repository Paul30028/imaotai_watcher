from utils.signature import generate_sign, generate_device_id


def test_generate_sign_is_md5_hex():
    sign = generate_sign("device123", "1700000000")
    assert len(sign) == 32
    assert sign.isalnum()


def test_generate_sign_deterministic():
    s1 = generate_sign("device123", "1700000000")
    s2 = generate_sign("device123", "1700000000")
    assert s1 == s2


def test_generate_sign_differs_with_different_inputs():
    s1 = generate_sign("device123", "1700000000")
    s2 = generate_sign("device456", "1700000000")
    assert s1 != s2


def test_generate_device_id_format():
    device_id = generate_device_id()
    assert len(device_id) == 36  # UUID with hyphens
