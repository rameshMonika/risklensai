# Portfolio Risk Investigator

An agentic AI system that investigates *why* portfolio risk changed — not a trading, optimization, or recommendation system. A LangGraph multi-agent supervisor routes natural-language questions to specialized agents, combining deterministic quantitative analysis with externally retrieved market and news evidence into a grounded, cited report.

## Objective

Design and evaluate an agentic system capable of dynamically investigating portfolio risk by combining deterministic quantitative analysis with externally retrieved market and news evidence.

**Core architectural rule: the LLM never calculates risk metrics itself.** It decides which deterministic Python function to call; the function computes; the LLM interprets the result.

## Scope

Out of scope: automated trading, buy/sell execution, portfolio optimization, price prediction, options pricing, tax calculations, crypto, brokerage integration, personalized investment recommendations.

MVP limits: portfolio capped at ~5-10 equities; no auth in V1 (single hardcoded user); no cash balance tracked (portfolio value = Σ holding market values only); margin, lot-level cost basis, and dividend persistence all deferred (dividends fetched live, not stored); dashboard and AI investigation workspace merged into one screen.

## Development approach

**Notebook + evaluation first, implementation second.** Before building the actual LangGraph application, validate the finance methodology and evaluation approach in notebooks:

1. `01_finance_methodology.ipynb` — market data retrieval, risk calculations, validated against ground truth.
2. `02_agent_evaluation.ipynb` — supervisor routing accuracy (labelled test questions), evidence quality (LLM-as-judge).
3. `03_end_to_end_evaluation.ipynb` — full investigations, report quality (LLM-as-judge).

Only after the notebooks prove the calculations are correct and the evaluation rubric works does the multi-agent app itself get built. Do not scaffold the LangGraph app, database, or frontend before that.

## ERD

```
USER
  id PK
  name
  email
  created_at

PORTFOLIO
  id PK
  user_id FK -> USER
  name
  created_at

HOLDING
  id PK
  portfolio_id FK -> PORTFOLIO
  symbol
  quantity
  avg_cost
  created_at

INVESTIGATION
  id PK
  portfolio_id FK -> PORTFOLIO
  query
  intent
  status
  start_date
  end_date
  risk_results JSONB
  observability_trace_id
  created_at

EVIDENCE
  id PK
  investigation_id FK -> INVESTIGATION
  symbol
  title
  source_url
  published_at
  evidence_text
  retrieved_at

INVESTIGATION_REPORT
  id PK
  investigation_id FK -> INVESTIGATION
  summary
  report_json
  created_at
```

Design notes:
- No `risk_tolerance` / `investment_horizon` / `preferred_currency` / `password_hash` on `USER` — deliberately dropped to keep this a non-personalization, non-recommendation system.
- No `cash_balance` on `PORTFOLIO` — valuation is Σ holding market values only.
- No sector/industry/asset-class columns on `HOLDING` and no separate `SECURITIES` master table. Sector/company metadata source of truth is the Market Agent (live market-data lookup); cache in Postgres later only if repeated calls become wasteful.
- No `RISK_RESULT` relational table. Forcing scalar per-symbol metrics (volatility, drawdown) and pairwise metrics (correlation matrix) into one relational schema wasn't worth it — risk calculations stay structured in-memory during the agent workflow and persist as `INVESTIGATION.risk_results` JSONB instead.
- `INVESTIGATION.risk_results` (machine-readable calc output, e.g. `{"volatility": {"NVDA": 0.28}, "max_drawdown": {"NVDA": -0.17}, "sector_exposure": {"Technology": 0.61}, "loss_contribution": {"NVDA": 0.47}}`) is kept distinct from `INVESTIGATION_REPORT.report_json` (final user-facing narrative synthesized by Report Agent from `risk_results`). One is deterministic ground truth (what pytest/eval checks against); the other is the LLM's interpretation of it.
- `observability_trace_id` is vendor-neutral (not `langsmith_run_id`) so it works whether the trace backend ends up being LangSmith, Langfuse, or something else.
- `beta` and its benchmark dependency are deferred past V1 entirely (see Risk tools below), so no benchmark ticker field is needed anywhere in this schema for V1.
- `EVIDENCE.evidence_text` (the actual retrieved passage/snippet, not just title + URL) is required so the evidence-quality LLM judge can evaluate claim-support reproducibly — a URL alone isn't reproducible since re-fetching later may not return the same content. `retrieved_at` supports the same audit purpose.
- No `relevance` column on `EVIDENCE` in V1 — there's no defined runtime step where the News Agent ranks/filters candidate articles, so a persisted relevance score would conflate an eval-time judge score (computed separately, not application data) with an application ranking that doesn't exist yet. If real-time News ranking gets added later, define it explicitly first.
- No `risk_level` on `INVESTIGATION_REPORT` — an LLM-assigned "Low/Medium/High" label has no defined methodology behind it and would be an unaudited classification sitting next to rigorously-computed metrics. The report states the actual computed numbers (e.g. "volatility rose from X to Y, tech exposure is Z%") instead of inventing a categorical label.

## Agents (V1)

- **Portfolio Agent** — reads Postgres directly (no MCP wrapper; internal/simple, not worth the infra overhead).
- **Market Agent** — Alpha Vantage MCP. Retrieves raw historical prices, current/latest prices, trading volume, company info, and sector/industry metadata. Does NOT compute returns (that's `calculate_returns()`, owned by Risk Agent — Market Agent returning derived returns would duplicate/conflict with the deterministic-calculation rule) and does NOT retrieve benchmark prices in V1 (dead scope now that beta/benchmark comparison is deferred past V1).
- **Risk Agent** — local deterministic-calculation MCP (was called "Analytics Agent" in early drafts).
- **News Agent** — Tavily MCP. Always given a specific symbol + date-range target (from either the user's question or the Risk Agent's output) — never a blind search across all holdings.
- **Answer Agent** — lightweight synthesis node for simple quantitative Q&A. Turns a raw calc dict like `{"symbol": "NVDA", "volatility": 0.284}` into one plain sentence ("NVDA's annualised volatility over the selected period is 28.4%"). No citations/limitations structure.
- **Report Agent** — full grounded synthesis with citations, reserved for routes involving News/evidence or a full investigation.

## Agent flow / routing (V1)

One Supervisor, no second supervisor/meta-router — kept deliberately simple for V1. The Supervisor classifies intent, extracts target ticker + period, and **selects both which agents run and the edge order between them** per query (not just which nodes to include from one fixed graph).

```
                         USER
                           │
                           ▼
                      SUPERVISOR
              (classify intent, extract target/period,
               select agents AND their order)
                           │
              ┌────────────┴────────────┐
              ▼                         ▼
     Specific/simple question    Full portfolio investigation
              │                         │
   only the agents that            always the complete route:
   question needs, then          Portfolio → Market → Risk →
   → ANSWER → END                     News → REPORT → END
```

Confirmed example routes:

| Question | Route |
|---|---|
| "What are my holdings?" | `Portfolio → Answer → END` |
| "How concentrated am I?" | `Portfolio → Risk → Answer → END` |
| "What's NVDA's 30-day volatility?" | `Market → Risk → Answer → END` |
| "Why did NVDA fall this week?" | `Market → News → Report → END` (target ticker+period already given by the user, so Risk isn't needed to discover it — still goes through Report since it involves News/evidence) |
| "Investigate my portfolio risk" | `Portfolio → Market → Risk → News → Report → END` (full investigation, always the complete route) |

Rule of thumb: **Answer Agent = simple Q&A synthesis, every quantitative-only route ends here (never raw dicts returned to the user). Report Agent = full investigation/News-involving synthesis with citations + limitations.**

### How News targets get chosen in a full investigation

This was an initial gap: "News is always given a specific symbol + date range" doesn't say *who picks it* when the target isn't already named in the user's question (i.e. the full-investigation route, where the portfolio has multiple holdings and nothing has narrowed it down yet).

**V1 rule: full investigations always run News, but the target is chosen deterministically — rank holdings by `contribution_to_loss` and take the top-1 driver.** Risk Agent's output feeds directly into a `news_targets` structure:

```json
{
  "news_targets": [
    {
      "symbol": "NVDA",
      "reason": "largest_loss_contributor",
      "start_date": "<INVESTIGATION.start_date>",
      "end_date": "<INVESTIGATION.end_date>"
    }
  ]
}
```

This is a distinct decision from the deferred V2 gate: **V1 decides *who* to research (always runs News); V2 decides *whether* to research at all.** They don't overlap.

**Date window rule (V1): use the user-requested investigation period (`start_date`/`end_date` on `INVESTIGATION`) as the News search window, not a separately-calculated drawdown-specific interval.** V1 doesn't compute a per-symbol worst-drawdown window distinct from the overall investigation period, so there's nothing else to use — this can be revisited if a specific drawdown-window calculation gets added later.

```
Full investigation
        │
        ▼
  Risk calculates metrics
        │
        ▼
  Rank risk drivers by contribution_to_loss
        │
        ▼
  Select top-1 driver → symbol + date window
        │
        ▼
     News Agent
```

**Deferred to V2 (explicitly KIV'd, not V1 scope):** a deterministic "important event?" gate after Risk in the full-investigation route, which would decide whether News is even needed (skip News → Report directly if nothing significant happened), based on a risk-threshold rule — not an LLM judgment call. Staged-complexity plan: V1 = intent-based conditional routing (which agents run at all); V2 = event-driven conditional routing (whether to bother with News) layered on top.

```
V2 addition inside the full-investigation route:

  Risk
   │
   ▼
  deterministic event-detection (risk-threshold rule)
   │
   ├── not significant ──────────────► Report
   └── significant ────► News ───────► Report
```

## Functional requirements (V1)

- **FR1 Portfolio management** — create portfolio, add/remove holdings, specify quantity + purchase price, view current holdings.
- **FR2 Natural-language investigation** — Supervisor converts a question into a structured plan: `intent`, `time_range`, `required_agents`, `required_calculations`, `news_targets`.
- **FR3 Market investigation** — daily/historical prices, current prices, trading volume, company info, sector/industry metadata, via Market Agent → Alpha Vantage MCP. (No returns — that's `calculate_returns()`; no benchmark prices in V1.)
- **FR4 Quantitative risk analysis** — deterministic Python tools, never LLM-calculated:
  - V1: `calculate_returns`, `calculate_volatility`, `calculate_max_drawdown`, `calculate_concentration`, `calculate_sector_exposure`, `calculate_correlation_matrix`, `calculate_contribution_to_loss`.
  - Deferred past V1: `calculate_beta` (no benchmark source needed in V1 as a result; if added later, benchmark will be application-configured and fetched via Market MCP), `calculate_var`, `calculate_sharpe_ratio`.
- **FR5 News investigation** — News Agent receives specific targets (symbol + date range) rather than blindly searching every holding. Pipeline: rank quantitative risk drivers → select top driver → search relevant evidence → assess evidence → generate grounded explanation. (Not "detect quantitative anomaly" — V1 has no true anomaly detector, it deterministically ranks and picks the top `contribution_to_loss` driver, per the News-targeting rule above.)
- **FR6 Grounded risk report** — risk summary, quantitative evidence, concentration, major risk event, cited news evidence, interpretation, and an explicit limitations section (news correlation ≠ causation).

## Evaluation methodology

Kept deliberately small — four claims, not twenty metrics:

1. **Supervisor routing accuracy** — 30-50 labelled test questions with an expected agent sequence (e.g. "What's NVDA volatility?" → `Market → Risk`), compare actual vs. expected route, pass/fail. Metric: Routing Accuracy. (Intent accuracy, target-source accuracy, unnecessary-agent-rate are debugging info only, not core metrics.)
2. **Risk calculation correctness** — plain pytest unit tests against Python ground truth for returns, volatility, max drawdown, concentration, correlation, loss contribution. No LLM judge. Metric: Financial Calculation Accuracy.
3. **Evidence quality** — LLM-as-judge, 1-5 rubric: relevance (is retrieved evidence relevant to the identified risk event?) and claim_support (does it actually support the report's claim?).
4. **Final report quality** — second LLM-as-judge pass, given question + verified metrics + evidence + generated report: groundedness (conclusions supported by supplied data?) and relevance (does it answer the question?). Clarity is explicitly deferred, not a core metric.

Notebook layout mirrors this: `01_finance_methodology.ipynb` (market data, risk calcs, validation), `02_agent_evaluation.ipynb` (supervisor routing, evidence judge), `03_end_to_end_evaluation.ipynb` (full investigations, report judge). Unit tests for the deterministic risk functions live in the actual codebase, not notebooks.

## Not yet decided

- Tech stack and project layout (frontend framework, backend framework, language/package-manager choices).
- Concrete sample portfolio and API access (Alpha Vantage, Tavily) needed to actually run the notebooks.
- Ground-truth reference for the risk calculation pytest suite.
- The 30-50 labelled routing questions for the supervisor eval.
