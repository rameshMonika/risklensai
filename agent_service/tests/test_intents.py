"""The routing table (graph/intents.py) against CLAUDE.md's confirmed routes.

intents.py has no heavy imports, so this file needs no stubs -- it's a plain
integrity check on two dicts.
"""

from agent_service.graph.intents import INTENT_ROUTES, ROUTE_UTTERANCES

FIVE_INTENTS = {"holdings", "concentration", "symbol_risk", "news_reason", "full_investigation"}
VALID_AGENTS = {"portfolio", "market", "risk", "news", "answer", "report"}


def test_both_dicts_cover_exactly_the_five_intents():
    assert set(INTENT_ROUTES) == FIVE_INTENTS
    assert set(ROUTE_UTTERANCES) == FIVE_INTENTS


def test_every_route_is_a_nonempty_list_of_valid_agent_names():
    for intent, route in INTENT_ROUTES.items():
        assert isinstance(route, list) and route, intent
        assert set(route) <= VALID_AGENTS, (intent, route)


def test_routes_match_the_claude_md_table():
    assert INTENT_ROUTES["holdings"] == ["portfolio", "answer"]
    assert INTENT_ROUTES["concentration"] == ["portfolio", "market", "risk", "answer"]
    assert INTENT_ROUTES["symbol_risk"] == ["market", "risk", "answer"]
    assert INTENT_ROUTES["news_reason"] == ["market", "news", "report"]
    assert INTENT_ROUTES["full_investigation"] == ["portfolio", "market", "risk", "news", "report"]


def test_quantitative_routes_end_at_answer_news_routes_end_at_report():
    # CLAUDE.md rule of thumb: Answer = quant-only synthesis, Report = anything
    # involving News / a full investigation.
    for intent in ("holdings", "concentration", "symbol_risk"):
        assert INTENT_ROUTES[intent][-1] == "answer"
        assert "news" not in INTENT_ROUTES[intent]
    for intent in ("news_reason", "full_investigation"):
        assert INTENT_ROUTES[intent][-1] == "report"
        assert "news" in INTENT_ROUTES[intent]


def test_market_precedes_risk_wherever_both_run():
    # Risk needs prices that only Market fetches.
    for route in INTENT_ROUTES.values():
        if "market" in route and "risk" in route:
            assert route.index("market") < route.index("risk")


def test_every_intent_has_several_example_utterances():
    for intent, utterances in ROUTE_UTTERANCES.items():
        assert len(utterances) >= 3, intent
        assert all(isinstance(u, str) and u.strip() for u in utterances)
