from unittest.mock import patch, MagicMock
from core.purchase import purchase_for_account


def _make_account():
    acc = MagicMock()
    acc.id = 1
    acc.phone = "13800138000"
    acc.token = "test_token"
    acc.device_id = "test_device"
    acc.city_code = "500100"
    acc.status = "active"
    return acc


def _make_product(item_code="10941", item_name="飞天茅台"):
    p = MagicMock()
    p.item_code = item_code
    p.item_name = item_name
    p.enabled = True
    return p


def test_purchase_success_writes_log():
    account = _make_account()
    products = [_make_product()]
    db = MagicMock()

    with patch("core.purchase.get_current_session", return_value=1), \
         patch("core.purchase.get_shops", return_value=[{"shopCode": "shop001"}]), \
         patch("core.purchase.reserve", return_value={"code": 200, "message": "success"}):
        result = purchase_for_account(account, products, db)

    assert result["success"] == 1
    assert result["fail"] == 0
    db.add.assert_called_once()
    db.commit.assert_called_once()


def test_purchase_fail_retries_3_times():
    account = _make_account()
    products = [_make_product()]
    db = MagicMock()

    with patch("core.purchase.get_current_session", return_value=1), \
         patch("core.purchase.get_shops", return_value=[{"shopCode": "shop001"}]), \
         patch("core.purchase.reserve", side_effect=Exception("API error")), \
         patch("core.purchase.time.sleep"):
        result = purchase_for_account(account, products, db)

    assert result["fail"] == 1


def test_purchase_no_shops_skips_product():
    account = _make_account()
    products = [_make_product()]
    db = MagicMock()

    with patch("core.purchase.get_current_session", return_value=1), \
         patch("core.purchase.get_shops", return_value=[]):
        result = purchase_for_account(account, products, db)

    assert result["fail"] == 1
