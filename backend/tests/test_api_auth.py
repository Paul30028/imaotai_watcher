def test_login_success(client, admin_user):
    resp = client.post("/api/auth/login", json={"username": "testadmin", "password": "testpass"})
    assert resp.status_code == 200
    assert "access_token" in resp.json()


def test_login_wrong_password(client, admin_user):
    resp = client.post("/api/auth/login", json={"username": "testadmin", "password": "wrong"})
    assert resp.status_code == 401


def test_me_requires_token(client):
    resp = client.get("/api/auth/me")
    assert resp.status_code in (401, 403)  # HTTPBearer returns 403 pre-0.111 or 401 in newer FastAPI


def test_me_returns_user(client, admin_token):
    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    assert resp.json()["username"] == "testadmin"


def test_refresh_returns_new_token(client, admin_token):
    resp = client.post("/api/auth/refresh", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200
    assert "access_token" in resp.json()
