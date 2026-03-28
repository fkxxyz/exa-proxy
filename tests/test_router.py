from exa_proxy.config import UpstreamConfig
from exa_proxy.router import AttemptContext, UpstreamRouter


def make_router():
    upstreams = [
        UpstreamConfig(
            name="exa-a",
            url="https://mcp.exa.ai/mcp",
            authorization="Bearer a",
            cooldown_seconds=30,
        ),
        UpstreamConfig(
            name="exa-b",
            url="https://mcp.exa.ai/mcp",
            authorization="Bearer b",
            cooldown_seconds=30,
        ),
    ]
    return UpstreamRouter(upstreams)


def test_choose_uses_round_robin_between_healthy_upstreams():
    router = make_router()
    context = AttemptContext(tool_name="exa_search", arguments={"query": "mcp"})

    first = router.choose(context)
    second = router.choose(context)

    assert first.name == "exa-a"
    assert second.name == "exa-b"


def test_mark_failure_puts_upstream_into_cooldown_and_skips_it():
    router = make_router()
    context = AttemptContext(tool_name="exa_search", arguments={"query": "mcp"})

    first = router.choose(context)
    router.mark_failure(first)
    second = router.choose(context)

    assert first.name == "exa-a"
    assert second.name == "exa-b"


def test_rewrite_arguments_injects_selected_upstream_name_for_observability():
    router = make_router()
    upstream = router.choose(
        AttemptContext(tool_name="exa_search", arguments={"query": "mcp"})
    )

    rewritten = router.rewrite_arguments(upstream, {"query": "mcp"})

    assert rewritten["query"] == "mcp"
    assert rewritten["_proxy"]["upstream"] == "exa-a"
