from unittest.mock import patch, MagicMock
from core.purchase import purchase_for_account
from core.imaotai_api import MoutaiError


def _make_account():
    acc = MagicMock()
    acc.id = 1
    acc.phone = "13800138000"
    acc.token = "test_token"
    acc.device_id = "test_device"
    acc.user_id = "12345"
    acc.province_name = "广东省"
    acc.city_name = "深圳市"
    acc.lat = "22.543099"
    acc.lng = "114.057868"
    acc.shop_type = 1
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

    with patch("core.purchase.pick_shop_id", return_value="shop001"), \
         patch("core.purchase.reserve_item", return_value={"code": 2000, "data": {"successDesc": "申购成功"}}), \
         patch("core.purchase.time.sleep"):
        result = purchase_for_account(account, products, db)

    assert result["success"] == 1
    assert result["fail"] == 0
    db.add.assert_called_once()
    db.commit.assert_called_once()


def test_purchase_fail_retries_3_times():
    account = _make_account()
    products = [_make_product()]
    db = MagicMock()

    with patch("core.purchase.pick_shop_id", return_value="shop001"), \
         patch("core.purchase.reserve_item", side_effect=MoutaiError("库存不足")), \
         patch("core.purchase.time.sleep") as mock_sleep:
        result = purchase_for_account(account, products, db)

    assert result["fail"] == 1
    # 3 次重试，其中 2 次重试间隔 sleep(1)，外加商品间隔 sleep(3~5)
    assert mock_sleep.call_count >= 3


def test_purchase_no_shops_skips_product():
    account = _make_account()
    products = [_make_product()]
    db = MagicMock()

    with patch("core.purchase.pick_shop_id", side_effect=MoutaiError("该省份今日无该商品在售门店")), \
         patch("core.purchase.time.sleep"):
        result = purchase_for_account(account, products, db)

    assert result["fail"] == 1


def test_purchase_auth_error_marks_account_expired():
    account = _make_account()
    products = [_make_product()]
    db = MagicMock()

    with patch("core.purchase.pick_shop_id", return_value="shop001"), \
         patch("core.purchase.reserve_item", side_effect=MoutaiError("token已失效，请重新登录")), \
         patch("core.purchase.send_server_chan") as mock_notify, \
         patch("core.purchase.time.sleep"):
        result = purchase_for_account(account, products, db)

    assert result["fail"] == 1
    assert account.status == "expired"
    mock_notify.assert_called_once()
