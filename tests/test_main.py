from fastapi.testclient import TestClient

from exa_proxy.main import create_app
from exa_proxy.executor import ProxyExecutor


async def _fake_execute(self, method, path, headers=None, body=None, should_abort=None):
    return 200, {"content-type": "application/json"}, b'{"ok":true}'


def test_create_app_returns_fastapi_app(monkeypatch, tmp_path):
    monkeypatch.setenv("EXA_PROXY_STORAGE", str(tmp_path / "keys.json"))
    monkeypatch.setattr(ProxyExecutor, "execute", _fake_execute)

    app = create_app()

    assert app is not None
    assert app.title == "Exa Proxy"


def test_health_endpoint_reports_zero_keys(monkeypatch, tmp_path):
    monkeypatch.setenv("EXA_PROXY_STORAGE", str(tmp_path / "keys.json"))
    monkeypatch.setattr(ProxyExecutor, "execute", _fake_execute)

    app = create_app()
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "available_keys": 0,
        "total_keys": 0,
    }
