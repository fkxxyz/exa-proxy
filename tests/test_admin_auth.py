from fastapi.testclient import TestClient

from exa_proxy.main import create_app
from exa_proxy.executor import ProxyExecutor


async def _fake_execute(self, method, path, headers=None, body=None):
    return 200, {"content-type": "application/json"}, b'{"ok":true}'


def test_admin_requires_basic_auth(monkeypatch, tmp_path):
    monkeypatch.setenv("EXA_PROXY_STORAGE", str(tmp_path / "keys.json"))
    monkeypatch.setenv("EXA_PROXY_ADMIN_USERNAME", "fkxxyz")
    monkeypatch.setenv("EXA_PROXY_ADMIN_PASSWORD", "secret-pass")
    monkeypatch.setattr(ProxyExecutor, "execute", _fake_execute)

    app = create_app()
    client = TestClient(app)

    response = client.get("/admin")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Basic"


def test_admin_allows_basic_auth(monkeypatch, tmp_path):
    monkeypatch.setenv("EXA_PROXY_STORAGE", str(tmp_path / "keys.json"))
    monkeypatch.setenv("EXA_PROXY_ADMIN_USERNAME", "fkxxyz")
    monkeypatch.setenv("EXA_PROXY_ADMIN_PASSWORD", "secret-pass")
    monkeypatch.setattr(ProxyExecutor, "execute", _fake_execute)

    app = create_app()
    client = TestClient(app)

    response = client.get("/admin", auth=("fkxxyz", "secret-pass"))

    assert response.status_code == 200
    assert "Exa Proxy" in response.text


def test_key_api_requires_basic_auth(monkeypatch, tmp_path):
    monkeypatch.setenv("EXA_PROXY_STORAGE", str(tmp_path / "keys.json"))
    monkeypatch.setenv("EXA_PROXY_ADMIN_USERNAME", "fkxxyz")
    monkeypatch.setenv("EXA_PROXY_ADMIN_PASSWORD", "secret-pass")
    monkeypatch.setattr(ProxyExecutor, "execute", _fake_execute)

    app = create_app()
    client = TestClient(app)

    response = client.get("/api/keys")

    assert response.status_code == 401


def test_mcp_does_not_require_auth(monkeypatch, tmp_path):
    monkeypatch.setenv("EXA_PROXY_STORAGE", str(tmp_path / "keys.json"))
    monkeypatch.setenv("EXA_PROXY_ADMIN_USERNAME", "fkxxyz")
    monkeypatch.setenv("EXA_PROXY_ADMIN_PASSWORD", "secret-pass")
    monkeypatch.setattr(ProxyExecutor, "execute", _fake_execute)

    app = create_app()
    client = TestClient(app)

    response = client.post("/mcp", json={"jsonrpc": "2.0", "method": "ping", "id": 1})

    assert response.status_code == 200
    assert response.json() == {"ok": True}
