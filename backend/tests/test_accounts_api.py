from models.models import Account, Product


def _make_account(db, **overrides):
    defaults = dict(
        phone="13800138000",
        token="tok-123",
        user_id="u1",
        device_id="dev-1",
        province_name="广东省",
        city_name="深圳市",
        lat="22.54",
        lng="114.05",
        shop_type=1,
        status="active",
    )
    defaults.update(overrides)
    account = Account(**defaults)
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


def test_requires_auth(client):
    resp = client.get("/api/accounts/gh-action-config")
    assert resp.status_code in (401, 403)


def test_empty_when_no_logged_in_accounts(client, admin_token):
    resp = client.get("/api/accounts/gh-action-config", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    assert resp.json() == []


def test_excludes_expired_and_tokenless_accounts(client, admin_token, db):
    _make_account(db, phone="13800138001", status="expired")
    _make_account(db, phone="13800138002", token=None)
    resp = client.get("/api/accounts/gh-action-config", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.json() == []


def test_includes_token_and_shop_fields_for_active_logged_in_account(client, admin_token, db):
    _make_account(db)
    resp = client.get("/api/accounts/gh-action-config", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    [entry] = resp.json()
    assert entry["phone"] == "13800138000"
    assert entry["token"] == "tok-123"
    assert entry["device_id"] == "dev-1"
    assert entry["user_id"] == "u1"
    assert entry["shop_id"] == "AUTO"
    assert entry["shop_type"] == 1
    assert entry["province"] == "广东省"
    assert entry["city"] == "深圳市"
    assert entry["item_ids"] == []


def test_uses_account_products_over_global_defaults(client, admin_token, db):
    account = _make_account(db)
    db.add(Product(account_id=None, item_code="global1", item_name="全局商品", enabled=True))
    db.add(Product(account_id=account.id, item_code="own1", item_name="账号专属商品", enabled=True))
    db.commit()
    resp = client.get("/api/accounts/gh-action-config", headers={"Authorization": f"Bearer {admin_token}"})
    [entry] = resp.json()
    assert entry["item_ids"] == ["own1"]


def test_falls_back_to_global_products_when_account_has_none(client, admin_token, db):
    _make_account(db)
    db.add(Product(account_id=None, item_code="global1", item_name="全局商品", enabled=True))
    db.commit()
    resp = client.get("/api/accounts/gh-action-config", headers={"Authorization": f"Bearer {admin_token}"})
    [entry] = resp.json()
    assert entry["item_ids"] == ["global1"]
