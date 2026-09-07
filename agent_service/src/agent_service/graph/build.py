"""Compiles the full graph: guardrail -> supervisor -> dynamically-dispatched
agent nodes -> END. Ported from the graph-building half of notebook cell 38.
Exposes run_investigation() as the entrypoint main.py calls per request.
"""

from datetime import date
from typing import Literal, Optional

from langchain_core.tracers.context import collect_runs
from langgraph.graph import END, START, StateGraph

from agent_service.core.config import settings

from agent_service.graph.guardrail import guardrail_node, route_after_guardrail
from agent_service.graph.nodes import (
    answer_node,
    market_node,
    news_node,
    portfolio_node,
    report_node,
    risk_node,
    semantic_supervisor_node,
)
from agent_service.graph.state import InvestigationState

AgentName = Literal["portfolio", "market", "risk", "news", "answer", "report"]

AGENT_NODE_FUNCS = {
    "portfolio": portfolio_node,
    "market": market_node,
    "risk": risk_node,
    "news": news_node,
    "answer": answer_node,
    "report": report_node,
}


def route_next(state: InvestigationState) -> str:
    """Dispatches to the Supervisor's planned agent one at a time, by index.
    This dynamic-plan dispatch is what makes the trajectory vary per route
    shape, rather than a graph with only one possible path."""
    if state["step"] >= len(state["plan"]):
        return END
    return state["plan"][state["step"]]


route_map = {name: name for name in AGENT_NODE_FUNCS}
route_map[END] = END

_graph_builder = StateGraph(InvestigationState)
_graph_builder.add_node("guardrail", guardrail_node)
_graph_builder.add_node("supervisor", semantic_supervisor_node)
for _name, _fn in AGENT_NODE_FUNCS.items():
    _graph_builder.add_node(_name, _fn)

_graph_builder.add_edge(START, "guardrail")
_graph_builder.add_conditional_edges(
    "guardrail", route_after_guardrail, {"supervisor": "supervisor", END: END}
)
_graph_builder.add_conditional_edges("supervisor", route_next, route_map)
for _name in AGENT_NODE_FUNCS:
    _graph_builder.add_conditional_edges(_name, route_next, route_map)

app = _graph_builder.compile()


def _initial_state(question: str, holdings: list[dict], start_date: date, end_date: date) -> InvestigationState:
    return InvestigationState(
        question=question,
        start_date=start_date,
        end_date=end_date,
        intent=None,
        plan=[],
        step=0,
        agents_used=[],
        target_symbol=None,
        refused=False,
        not_found=False,
        holdings=holdings,
        scope_symbols=[],
        prices={},
        sectors={},
        risk_results={},
        news_target=None,
        news_evidence=[],
        answer="",
    )


async def run_investigation(
    question: str, holdings: list[dict], start_date: date, end_date: date
) -> tuple[InvestigationState, Optional[str]]:
    """The entrypoint main.py's POST /internal/investigate handler calls.
    Async (ainvoke, not invoke) since market_node/risk_node/news_node are
    async MCP-calling nodes.

    Returns (final_state, trace_id). trace_id is the LangSmith root-run id for
    this investigation -- Core persists it as INVESTIGATION.observability_trace_id
    so a run can be pulled up in the LangSmith UI later. It's None when tracing
    is disabled (no LangSmith key), so the column stays null rather than holding
    an id that points at nothing.
    """
    with collect_runs() as runs_cb:
        final_state = await app.ainvoke(_initial_state(question, holdings, start_date, end_date))

    trace_id: Optional[str] = None
    if settings.langsmith_tracing and runs_cb.traced_runs:
        trace_id = str(runs_cb.traced_runs[0].id)

    return final_state, trace_id
