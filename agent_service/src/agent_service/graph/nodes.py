"""Agent nodes: portfolio (state-shaping only), market/risk/news (MCP-backed,
async), answer/report (LLM synthesis), and the Supervisor itself. Ported from
notebook cells 6-12 and the semantic_supervisor_node half of cell 38.
"""



from agent_service.core.llm import invoke_with_retry
from agent_service.core.mcp_manager import mcp_manager
from agent_service.graph.intents import INTENT_ROUTES
from agent_service.graph.router import extract_target_symbol, predict_intent, score_all_routes
from agent_service.graph.state import InvestigationState

AGENT_LABELS = {
    "portfolio": "Portfolio",
    "market": "Market",
    "risk": "Risk",
    "news": "News",
    "answer": "Answer",
    "report": "Report",
}


def semantic_supervisor_node(state: InvestigationState) -> dict:
    question = state["question"]
    scores = score_all_routes(question)
    predicted_intent = predict_intent(scores)

    plan = list(INTENT_ROUTES[predicted_intent])
    needs_target = predicted_intent in ("symbol_risk", "news_reason")
    known_symbols = [h["symbol"] for h in state["holdings"]]
    target_symbol = extract_target_symbol(question, known_symbols) if needs_target else None

    return {
        "intent": predicted_intent,
        "plan": plan,
        "step": 0,
        "target_symbol": target_symbol,
        "refused": False,
    }


def portfolio_node(state: InvestigationState) -> dict:
    """State-shaping only -- holdings already arrived in the request payload
    (see CLAUDE.md's Backend architecture: the Agent service has no database
    access), so there's nothing to fetch here."""
    return {
        "agents_used": state["agents_used"] + [AGENT_LABELS["portfolio"]],
        "step": state["step"] + 1,
    }


async def market_node(state: InvestigationState) -> dict:
    target = state.get("target_symbol")
    known_symbols = [h["symbol"] for h in state["holdings"]]

    if target and target not in known_symbols:
        return {
            "not_found": True,
            "agents_used": state["agents_used"] + [AGENT_LABELS["market"]],
            "step": state["step"] + 1,
        }

    scope_symbols = [target] if target else known_symbols
    prices = {}
    for symbol in scope_symbols:
        prices[symbol] = await mcp_manager.call_tool("market", "get_historical_prices", {"symbol": symbol})

    sectors = {}
    if not target:
        for symbol in scope_symbols:
            overview = await mcp_manager.call_tool("market", "get_company_overview", {"symbol": symbol})
            sectors[symbol] = overview["sector"]

    return {
        "scope_symbols": scope_symbols,
        "prices": prices,
        "sectors": sectors,
        "not_found": False,
        "agents_used": state["agents_used"] + [AGENT_LABELS["market"]],
        "step": state["step"] + 1,
    }


async def risk_node(state: InvestigationState) -> dict:
    if state.get("not_found"):
        return {
            "agents_used": state["agents_used"] + [AGENT_LABELS["risk"]],
            "step": state["step"] + 1,
        }

    target = state.get("target_symbol")
    prices = state.get("prices")

    if not prices:
        raise RuntimeError(
            "Risk node has no price data in state. Market must run before Risk "
            "for any route that needs current prices."
        )

    if target:
        result = await mcp_manager.call_tool(
            "risk", "calculate_symbol_risk", {"symbol": target, "price_data": prices[target]}
        )
        risk_results = {
            "volatility": {target: result["volatility"]},
            "max_drawdown": {target: result["max_drawdown"]},
        }
        news_target = target
    else:
        risk_results = await mcp_manager.call_tool(
            "risk",
            "run_full_investigation",
            {"portfolio": state["holdings"], "price_data": prices, "sectors": state.get("sectors", {})},
        )
        news_target = max(risk_results["loss_contribution"], key=risk_results["loss_contribution"].get)

    return {
        "risk_results": risk_results,
        "news_target": news_target,
        "agents_used": state["agents_used"] + [AGENT_LABELS["risk"]],
        "step": state["step"] + 1,
    }


async def news_node(state: InvestigationState) -> dict:
    target = state.get("target_symbol") or state.get("news_target")
    overview = await mcp_manager.call_tool("market", "get_company_overview", {"symbol": target})
    company = overview["name"]

    days = max(7, min((state["end_date"] - state["start_date"]).days, 30))

    result = await mcp_manager.call_tool(
        "news", "search_news", {"symbol": target, "company_name": company, "days": days, "max_results": 5}
    )

    return {
        "news_evidence": result["evidence"],
        "agents_used": state["agents_used"] + [AGENT_LABELS["news"]],
        "step": state["step"] + 1,
    }


ANSWER_SYSTEM_PROMPT = \
"""You are the Answer Agent in a portfolio risk investigator.

Turn the given data into ONE plain-English sentence. No citations, no
limitations section, no hedging: just state the number(s) plainly.

If the question asks which holding is largest, most concentrated, most volatile,
or similar (an identify-the-extreme question), state both its identity AND its
associated number from the data (e.g. "AAPL is your largest position at 32% of
your portfolio."), not the identity alone.

If `not_found` is true, or the data has no value for what was asked, reply
exactly: "That data is not available." Never invent a number."""


def answer_node(state: InvestigationState) -> dict:
    payload = {
        "question": state["question"],
        "not_found": state.get("not_found", False),
        "holdings": state.get("holdings"),
        "risk_results": state.get("risk_results"),
    }
    messages = [
        {"role": "system", "content": ANSWER_SYSTEM_PROMPT},
        {"role": "user", "content": f"Question: {state['question']}\nData: {payload}"},
    ]
    answer = invoke_with_retry(messages, fallback="Answer generation failed, please try again.")
    return {
        "answer": answer,
        "agents_used": state["agents_used"] + [AGENT_LABELS["answer"]],
        "step": state["step"] + 1,
    }


REPORT_SYSTEM_PROMPT = \
"""You are the Report Agent in a portfolio risk investigator.

Write a short grounded report with, in order:
1. A quantitative risk summary based ONLY on the given risk_results.
2. A brief narrative of what the news evidence indicates happened, referencing article titles
   by name (not raw URLs -- the UI already lists full citations with links in a separate
   Evidence section shown below this report, so do not repeat URLs here).
3. A brief interpretation connecting the numbers to the news. news_evidence only ever covers
   the single symbol Risk selected as the top loss driver: for every other holding mentioned
   in risk_results, state plainly that its cause was not examined rather than inferring one.
4. A section with the exact heading "Limitations" (use that literal word) noting that news
   correlation is not causation and that the retrieved evidence may be incomplete.

Never state a fact that isn't backed by the given risk_results or news_evidence.
If `not_found` is true, say the requested data is not available instead of
writing a report."""


def report_node(state: InvestigationState) -> dict:
    payload = {
        "question": state["question"],
        "not_found": state.get("not_found", False),
        "risk_results": state.get("risk_results"),
        "news_evidence": state.get("news_evidence", []),
    }
    messages = [
        {"role": "system", "content": REPORT_SYSTEM_PROMPT},
        {"role": "user", "content": f"Question: {state['question']}\nData: {payload}"},
    ]
    answer = invoke_with_retry(messages, fallback="Report generation failed, please try again.")
    return {
        "answer": answer,
        "agents_used": state["agents_used"] + [AGENT_LABELS["report"]],
        "step": state["step"] + 1,
    }
