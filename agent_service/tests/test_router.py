"""Pure helpers in graph/router.py: extract_target_symbol, predict_intent.

score_all_routes (the embedding path) is NOT tested here -- it needs the real
encoder and is exercised end-to-end by the eval notebooks. conftest.py stubs
the encoder so the module imports without a model download.
"""

from agent_service.graph.router import extract_target_symbol, predict_intent

KNOWN = ["AAPL", "NVDA", "MSFT", "GOOGL", "TSLA"]


# --------------------------------------------------------------------------- #
# extract_target_symbol
# --------------------------------------------------------------------------- #

def test_matches_a_known_portfolio_symbol_case_insensitively():
    assert extract_target_symbol("What's NVDA's 30-day volatility?", KNOWN) == "NVDA"
    assert extract_target_symbol("how volatile is nvda right now", KNOWN) == "NVDA"


def test_known_symbol_wins_over_a_stray_caps_token():
    # "ZZZZ" is a distinctive caps token, but a known symbol is also present
    # and should be returned first.
    assert extract_target_symbol("Compare NVDA against ZZZZ", KNOWN) == "NVDA"


def test_falls_back_to_a_distinctive_all_caps_token_when_no_known_symbol():
    assert extract_target_symbol("What is ZZZZ's volatility?", KNOWN) == "ZZZZ"
    assert extract_target_symbol("Why did FAKECO drop this week?", KNOWN) == "FAKECO"


def test_returns_none_when_nothing_looks_like_a_ticker():
    assert extract_target_symbol("How concentrated is my portfolio?", KNOWN) is None
    assert extract_target_symbol("Investigate my portfolio risk", KNOWN) is None


def test_lowercase_text_with_no_known_symbol_yields_none():
    # the caps fallback only fires on ALL-CAPS tokens.
    assert extract_target_symbol("why did the stock fall this week", KNOWN) is None


def test_common_all_caps_words_are_not_treated_as_tickers():
    # every >=3-letter caps token here is in _COMMON_WORDS
    assert extract_target_symbol("WHAT DID THE WEEK", KNOWN) is None
    assert extract_target_symbol("HOW RECENTLY DID THIS", KNOWN) is None


def test_caps_fallback_needs_at_least_three_letters():
    assert extract_target_symbol("What about GM stock", KNOWN) is None       # 2 letters
    assert extract_target_symbol("What about IBM stock", KNOWN) == "IBM"     # 3 letters


def test_empty_known_list_still_allows_the_caps_fallback():
    assert extract_target_symbol("How risky is XCORP", []) == "XCORP"


# --------------------------------------------------------------------------- #
# predict_intent
# --------------------------------------------------------------------------- #

def test_returns_the_single_highest_scoring_intent():
    scores = {
        "holdings": 0.11,
        "concentration": 0.20,
        "symbol_risk": 0.72,
        "news_reason": 0.30,
        "full_investigation": 0.15,
    }
    assert predict_intent(scores) == "symbol_risk"


def test_picks_the_max_even_when_all_scores_are_low():
    # the router has no refusal path -- it always returns one of the five.
    scores = {"holdings": 0.01, "concentration": 0.02, "symbol_risk": 0.015}
    assert predict_intent(scores) == "concentration"


def test_tie_returns_a_valid_key():
    scores = {"holdings": 0.5, "concentration": 0.5}
    assert predict_intent(scores) in scores
