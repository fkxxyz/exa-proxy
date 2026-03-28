import pytest

from exa_proxy.main import create_app
from exa_proxy.config import Settings, UpstreamConfig


def test_create_app_requires_upstreams():
    with pytest.raises(ValueError, match="No upstreams configured"):
        create_app(Settings(upstreams=[]))


def test_create_app_accepts_enabled_upstreams():
    settings = Settings(
        upstreams=[
            UpstreamConfig(
                name="exa-a", url="https://mcp.exa.ai/mcp", authorization="Bearer a"
            )
        ]
    )

    app = create_app(settings)

    assert app is not None
