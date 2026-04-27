from fastapi.testclient import TestClient

from exa_proxy.main import create_app
from exa_proxy.executor import ProxyExecutor


async def _fake_execute(self, method, path, headers=None, body=None, should_abort=None):
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


def test_admin_dashboard_renders_management_ui(monkeypatch, tmp_path):
    monkeypatch.setenv("EXA_PROXY_STORAGE", str(tmp_path / "keys.json"))
    monkeypatch.setenv("EXA_PROXY_ADMIN_USERNAME", "fkxxyz")
    monkeypatch.setenv("EXA_PROXY_ADMIN_PASSWORD", "secret-pass")
    monkeypatch.setattr(ProxyExecutor, "execute", _fake_execute)

    app = create_app()
    client = TestClient(app)

    response = client.get("/admin", auth=("fkxxyz", "secret-pass"))

    assert response.status_code == 200
    assert "Exa Proxy Admin" in response.text
    assert "Total Keys" in response.text
    assert "Success Rate" in response.text
    assert "Add Key" in response.text
    assert "Search keys" in response.text
    assert "No API keys added yet" in response.text
    assert "Create Key" in response.text


def test_admin_dashboard_displays_key_rows_and_actions(monkeypatch, tmp_path):
    monkeypatch.setenv("EXA_PROXY_STORAGE", str(tmp_path / "keys.json"))
    monkeypatch.setenv("EXA_PROXY_ADMIN_USERNAME", "fkxxyz")
    monkeypatch.setenv("EXA_PROXY_ADMIN_PASSWORD", "secret-pass")
    monkeypatch.setattr(ProxyExecutor, "execute", _fake_execute)

    app = create_app()
    client = TestClient(app)

    create_response = client.post(
        "/api/keys",
        auth=("fkxxyz", "secret-pass"),
        json={"name": "primary", "key": "exa_api_key_1234567890abcdef"},
    )
    assert create_response.status_code == 201

    response = client.get("/admin", auth=("fkxxyz", "secret-pass"))

    assert response.status_code == 200
    assert "primary" in response.text
    assert "exa_api_...cdef" in response.text
    assert "Available" in response.text
    assert "Edit" in response.text
    assert "Disable" in response.text
    assert "Reset" in response.text
    assert "Delete" in response.text


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
