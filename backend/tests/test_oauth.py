"""Sign in with Google / GitHub, with the provider replaced by a fake."""

from urllib.parse import parse_qs, urlparse

import pytest

from app.config import get_settings
from app.services import oauth


@pytest.fixture()
def providers(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "g-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "g-secret")
    monkeypatch.setenv("PUBLIC_WEB_URL", "https://web.test")
    monkeypatch.delenv("GITHUB_CLIENT_ID", raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture()
def fake_provider(monkeypatch):
    """Whoever `who` says is signing in at the provider."""
    who = {"value": oauth.Identity("g-123", "new@example.com", True, "Nina New")}
    seen = {}

    def fake(provider, settings, code, verifier, redirect_uri):
        seen.update(provider=provider, code=code, verifier=verifier, redirect_uri=redirect_uri)
        return who["value"]

    monkeypatch.setattr(oauth, "fetch_identity", fake)
    return who, seen


def _start(client, provider="google", headers=None):
    r = client.get(
        f"/api/auth/{provider}/start", params={"next": "/invite/abc"}, headers=headers or {}, follow_redirects=False
    )
    assert r.status_code == 302, r.text
    return parse_qs(urlparse(r.headers["location"]).query)


def _finish(client, state, provider="google", code="the-code"):
    r = client.get(f"/api/auth/{provider}/callback", params={"code": code, "state": state}, follow_redirects=False)
    assert r.status_code == 302
    url = urlparse(r.headers["location"])
    return url, parse_qs(url.fragment), parse_qs(url.query)


def test_only_configured_providers_are_offered(client, providers):
    assert client.get("/api/auth/providers").json() == {"google": True, "github": False}
    assert client.get("/api/auth/github/start", follow_redirects=False).status_code == 404
    assert client.get("/api/auth/facebook/start", follow_redirects=False).status_code == 404


def test_start_sends_state_and_pkce_to_the_provider(client, providers):
    r = client.get("/api/auth/google/start", headers={"x-forwarded-proto": "https"}, follow_redirects=False)
    q = parse_qs(urlparse(r.headers["location"]).query)
    assert r.headers["location"].startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert q["client_id"] == ["g-id"] and q["code_challenge_method"] == ["S256"]
    assert q["redirect_uri"] == ["https://testserver/api/auth/google/callback"]  # proxy-aware
    assert len(q["state"][0]) > 20 and len(q["code_challenge"][0]) == 43
    cookie = r.headers["set-cookie"]
    assert "slipcast_oauth=" in cookie and "HttpOnly" in cookie and "Path=/api/auth" in cookie
    assert "g-secret" not in r.headers["location"]


def test_new_person_gets_an_account_and_a_workspace(client, providers, fake_provider):
    who, seen = fake_provider
    q = _start(client)
    url, frag, _ = _finish(client, q["state"][0])
    assert url.geturl().startswith("https://web.test/auth/callback#")
    assert frag["next"] == ["/invite/abc"]
    assert seen["code"] == "the-code" and len(seen["verifier"]) > 40  # PKCE verifier goes to the exchange

    h = {"Authorization": f"Bearer {frag['token'][0]}"}
    me = client.get("/api/auth/me", headers=h).json()
    assert me["user"]["email"] == "new@example.com" and me["user"]["name"] == "Nina New"
    assert me["workspaces"][0] == {**me["workspaces"][0], "name": "Nina's workspace", "role": "admin"}
    assert me["has_password"] is False and me["sign_in_methods"] == ["google"]
    # no password yet, so password login can't work, but a password can be set without the old one
    assert client.post("/api/auth/login", json={"email": "new@example.com", "password": "anything"}).status_code == 401
    assert client.post("/api/auth/password", json={"new_password": "now-i-have-one"}, headers=h).status_code == 200


def test_verified_email_links_to_the_existing_account(client, providers, fake_provider, make_user):
    who, _ = fake_provider
    u = make_user("anirudh@example.com", "Anirudh K")
    who["value"] = oauth.Identity("g-777", "Anirudh@Example.com".lower(), True, "Anirudh")
    _, frag, _ = _finish(client, _start(client)["state"][0])
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {frag['token'][0]}"}).json()
    assert me["user"]["id"] == u["user"]["id"]  # same account, same workspace
    assert me["sign_in_methods"] == ["google", "password"] or me["sign_in_methods"] == ["password", "google"]

    # later sign-ins find the link by provider id, even if the email at Google changed
    who["value"] = oauth.Identity("g-777", "renamed@example.com", True, "Anirudh")
    _, frag2, _ = _finish(client, _start(client)["state"][0])
    me2 = client.get("/api/auth/me", headers={"Authorization": f"Bearer {frag2['token'][0]}"}).json()
    assert me2["user"]["id"] == u["user"]["id"]


def test_unverified_email_never_takes_over_an_account(client, providers, fake_provider, make_user):
    who, _ = fake_provider
    make_user("victim@example.com", "Victim")
    who["value"] = oauth.Identity("g-evil", "victim@example.com", False, "Mallory")
    url, frag, query = _finish(client, _start(client)["state"][0])
    assert url.path == "/login" and query["error"] == ["unverified_email"] and "token" not in frag


def test_bad_state_or_cancel_is_rejected(client, providers, fake_provider):
    _start(client)
    url, frag, query = _finish(client, "forged-state")
    assert url.path == "/login" and query["error"] == ["expired"] and not frag

    client.cookies.clear()  # no cookie at all, e.g. the link was opened in another browser
    url, _, query = _finish(client, "whatever")
    assert query["error"] == ["expired"]

    _start(client)
    r = client.get("/api/auth/google/callback", params={"error": "access_denied"}, follow_redirects=False)
    assert parse_qs(urlparse(r.headers["location"]).query)["error"] == ["cancelled"]


def test_provider_failure_is_reported_not_crashed(client, providers, monkeypatch):
    def broken(*a, **k):
        raise oauth.OAuthError("provider_unreachable")

    monkeypatch.setattr(oauth, "fetch_identity", broken)
    _, _, query = _finish(client, _start(client)["state"][0])
    assert query["error"] == ["provider_unreachable"]


def test_next_cannot_point_off_site(client, providers, fake_provider):
    r = client.get("/api/auth/google/start", params={"next": "//evil.example/x"}, follow_redirects=False)
    state = parse_qs(urlparse(r.headers["location"]).query)["state"][0]
    _, frag, _ = _finish(client, state)
    assert frag["next"] == ["/dashboard"]


def test_oauth_state_token_is_not_a_login(client, providers):
    r = client.get("/api/auth/google/start", follow_redirects=False)
    state_cookie = r.cookies.get("slipcast_oauth") or client.cookies.get("slipcast_oauth")
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {state_cookie}"}).status_code == 401
