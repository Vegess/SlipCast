def test_register_creates_personal_workspace(client, make_user):
    u = make_user()
    me = client.get("/api/auth/me", headers=u["headers"]).json()
    assert me["user"]["email"] == "anirudh@example.com"
    assert me["workspaces"][0]["name"] == "Anirudh's workspace"
    assert me["workspaces"][0]["role"] == "admin"


def test_duplicate_email_rejected(client, make_user):
    make_user()
    r = client.post(
        "/api/auth/register",
        json={"email": "ANIRUDH@example.com", "name": "Copy", "password": "another-pass"},
    )
    assert r.status_code == 409


def test_login_and_bad_password(client, make_user):
    make_user()
    ok = client.post("/api/auth/login", json={"email": "anirudh@example.com", "password": "s3cure-pass"})
    assert ok.status_code == 200 and ok.json()["access_token"]
    bad = client.post("/api/auth/login", json={"email": "anirudh@example.com", "password": "wrong-pass"})
    assert bad.status_code == 401


def test_protected_routes_need_token(client):
    assert client.get("/api/auth/me").status_code == 401
    r = client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert r.status_code == 401


def test_short_password_rejected(client):
    r = client.post("/api/auth/register", json={"email": "a@example.com", "name": "A", "password": "short"})
    assert r.status_code == 422
