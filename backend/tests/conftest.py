import os

os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.db import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture()
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    engine.dispose()


@pytest.fixture()
def make_user(client):
    def _make(email: str = "anirudh@example.com", name: str = "Anirudh K"):
        r = client.post("/api/auth/register", json={"email": email, "name": name, "password": "s3cure-pass"})
        assert r.status_code == 201, r.text
        token = r.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        me = client.get("/api/auth/me", headers=headers).json()
        return {"headers": headers, "workspace_id": me["workspaces"][0]["id"], "user": me["user"]}

    return _make


@pytest.fixture()
def demo(client, make_user):
    u = make_user()
    r = client.post(f"/api/workspaces/{u['workspace_id']}/demo-project", headers=u["headers"])
    assert r.status_code == 201, r.text
    return {**u, "project_id": r.json()["id"]}
