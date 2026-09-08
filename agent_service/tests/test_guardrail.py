"""graph/guardrail.py pure helpers: _blocked_by_content_filter, route_after_guardrail.

guardrail_node itself makes an LLM call, so it isn't unit-tested here (it's
covered by scripts/check_guardrail.py and the eval notebooks). conftest.py
supplies dummy env vars so core/config.py and core/llm.py import.
"""

from agent_service.graph.guardrail import _blocked_by_content_filter, route_after_guardrail


# --------------------------------------------------------------------------- #
# _blocked_by_content_filter
# --------------------------------------------------------------------------- #

def test_true_for_a_prompt_shield_label_block():
    exc = Exception("Error code: 400 - Response content blocked by label 'Jailbreak'.")
    assert _blocked_by_content_filter(exc) is True


def test_true_for_the_jailbreak_keyword():
    exc = Exception("... content_filter_results: {jailbreak: {filtered: true}} ...")
    assert _blocked_by_content_filter(exc) is True


def test_true_for_the_nested_content_filter_code():
    exc = Exception("... 'error': {'code': 'content_filter', 'message': '...'} ...")
    assert _blocked_by_content_filter(exc) is True


def test_case_insensitive():
    exc = Exception("Response Content BLOCKED BY LABEL 'JAILBREAK'")
    assert _blocked_by_content_filter(exc) is True


def test_false_for_an_ordinary_400_that_merely_mentions_content_filter_results():
    # every Azure 400 body carries a `content_filter_results` key -- that alone
    # must NOT count as a block (this is the bug the helper was written to avoid).
    exc = Exception(
        "Error code: 400 - {'error': {'message': \"'tool_choice' is not supported\", "
        "'type': 'invalid_request_error'}, 'content_filter_results': {}}"
    )
    assert _blocked_by_content_filter(exc) is False


def test_false_for_an_unrelated_error():
    assert _blocked_by_content_filter(Exception("Connection error.")) is False
    assert _blocked_by_content_filter(TimeoutError("read timed out")) is False


# --------------------------------------------------------------------------- #
# route_after_guardrail
# --------------------------------------------------------------------------- #

def test_refused_state_goes_to_end():
    from langgraph.graph import END

    assert route_after_guardrail({"refused": True}) == END


def test_clean_state_goes_to_supervisor():
    assert route_after_guardrail({"refused": False}) == "supervisor"


def test_missing_refused_key_defaults_to_supervisor():
    assert route_after_guardrail({}) == "supervisor"
