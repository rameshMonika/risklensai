# Portfolio Risk Investigator

An agentic AI system that investigates *why* portfolio risk changed — not a trading, optimization, or recommendation system. A LangGraph multi-agent supervisor routes natural-language questions to specialized agents, combining deterministic quantitative analysis with externally retrieved market and news evidence into a grounded, cited report.

## Objective

Design and evaluate an agentic system capable of dynamically investigating portfolio risk by combining deterministic quantitative analysis with externally retrieved market and news evidence.

**Core architectural rule: the LLM never calculates risk metrics itself.** It decides which deterministic Python function to call; the function computes; the LLM interprets the result.

## Scope

Out of scope: automated trading, buy/sell execution, portfolio optimization, price prediction, options pricing, tax calculations, crypto, brokerage integration, personalized investment recommendations.

MVP limits: portfolio capped at ~5-10 equities; no cash balance tracked (portfolio value = Σ holding market values only); margin, lot-level cost basis, and dividend persistence all deferred (dividends fetched live, not stored); dashboard and AI investigation workspace merged into one screen.

**Auth is in scope for V1** (revised from an earlier no-auth assumption): email/password with bcrypt-hashed passwords and short-lived stateless JWT access tokens. `USER.password_hash` exists in the ERD for this reason. JWTs are validated by signature (shared secret) wherever they're checked, not by a network call back to the auth service — see Backend architecture below.

## Development approach

**Notebook + evaluation first, implementation second.** Before building the actual LangGraph application, validate the finance methodology and the agent-evaluation approach in notebooks:

1. `01_finance_methodology.ipynb` — market data retrieval, risk calculations, validated against ground truth.
2. `02_agent_evaluation.ipynb` — a lightweight in-notebook LangGraph supervisor + agent-node prototype (Portfolio/Market/Risk/News/Answer/Report), run over labelled test questions spanning both simple routes and full investigations, scored across five dimensions: final answer correctness, correct agent selection, correct trajectory, latency, and safety/reliability. See Evaluation methodology below. This original notebook (LLM-prompt Supervisor) is left untouched as the historical baseline; `02_agent_evaluation_v2.ipynb` holds the fix iterations and the semantic-router experiment that superseded it, and `02_agent_evaluation_v3.ipynb` is the clean current version — see Supervisor routing methodology under Agent flow / routing below for the outcome.

Only after the notebooks prove the calculations are correct and the evaluation harness works does the real multi-agent app itself get built. Do not scaffold the LangGraph app, database, or frontend before that. Risk-calculation correctness (returns, volatility, drawdown, concentration, correlation, loss contribution) is verified separately by plain pytest unit tests in the codebase, not in these notebooks — it's ground-truth math, not agent behavior.

## ERD

```
USER
  id PK
  name
  email
  password_hash
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
- No `risk_tolerance` / `investment_horizon` / `preferred_currency` on `USER` — deliberately dropped to keep this a non-personalization, non-recommendation system. `password_hash` *is* present (see MVP limits above: auth is in scope for V1), which doesn't conflict with that reasoning — authentication isn't personalization.
- No `cash_balance` on `PORTFOLIO` — valuation is Σ holding market values only.
- No sector/industry/asset-class columns on `HOLDING` and no separate `SECURITIES` master table. Sector/company metadata source of truth is the Market Agent (live market-data lookup); cache in Postgres later only if repeated calls become wasteful.
- No `RISK_RESULT` relational table. Forcing scalar per-symbol metrics (volatility, drawdown) and pairwise metrics (correlation matrix) into one relational schema wasn't worth it — risk calculations stay structured in-memory during the agent workflow and persist as `INVESTIGATION.risk_results` JSONB instead.
- `INVESTIGATION.risk_results` (machine-readable calc output, e.g. `{"volatility": {"NVDA": 0.28}, "max_drawdown": {"NVDA": -0.17}, "sector_exposure": {"Technology": 0.61}, "loss_contribution": {"NVDA": 0.47}}`) is kept distinct from `INVESTIGATION_REPORT.report_json` (final user-facing narrative synthesized by Report Agent from `risk_results`). One is deterministic ground truth (what pytest/eval checks against); the other is the LLM's interpretation of it.
- `observability_trace_id` is vendor-neutral (not `langsmith_run_id`) so it works whether the trace backend ends up being LangSmith, Langfuse, or something else.
- `beta` and its benchmark dependency are deferred past V1 entirely (see Risk tools below), so no benchmark ticker field is needed anywhere in this schema for V1.
- `EVIDENCE.evidence_text` (the actual retrieved passage/snippet, not just title + URL) is required so the evidence-quality LLM judge can evaluate claim-support reproducibly — a URL alone isn't reproducible since re-fetching later may not return the same content. `retrieved_at` supports the same audit purpose.
- No `relevance` column on `EVIDENCE` in V1 — there's no defined runtime step where the News Agent ranks/filters candidate articles, so a persisted relevance score would conflate an eval-time judge score (computed separately, not application data) with an application ranking that doesn't exist yet. If real-time News ranking gets added later, define it explicitly first.
- No `risk_level` on `INVESTIGATION_REPORT` — an LLM-assigned "Low/Medium/High" label has no defined methodology behind it and would be an unaudited classification sitting next to rigorously-computed metrics. The report states the actual computed numbers (e.g. "volatility rose from X to Y, tech exposure is Z%") instead of inventing a categorical label.

## Backend architecture (V1)

Two separate FastAPI services, not one monolith, with a strict service boundary — the frontend only ever talks to one of them:

- **Core service** (Auth/Portfolio) — registration, login, JWT issuance, FR1 (portfolio/holdings CRUD), and **all persistence**: owns `USER`, `PORTFOLIO`, `HOLDING`, and also `INVESTIGATION`, `EVIDENCE`, `INVESTIGATION_REPORT`. This is the only public-facing API; the frontend never calls the Agent service directly.
- **Agent service** — the LangGraph investigation pipeline (guardrail → semantic router → Portfolio/Market/Risk/News/Answer/Report agents). **Fully stateless, no database access of any kind.** Not reachable from outside the private network/service mesh — only Core calls it.

Request flow for an investigation: `React → Core: POST /investigations {portfolio_id, question} → Core authenticates the user, verifies portfolio ownership, loads holdings from Postgres → Core calls Agent: POST /internal/investigate {portfolio_id, question, holdings} → Agent runs the LangGraph pipeline statelessly and returns the report → Core persists INVESTIGATION/EVIDENCE/INVESTIGATION_REPORT → Core returns the result to React.` The Agent service never touches Postgres, never sees a user JWT, and never knows how portfolios are stored — it only receives a holdings snapshot in the request body and returns a result. This makes the earlier "Portfolio Agent reads Postgres directly" design point obsolete — see its updated note below.

The internal `POST /internal/investigate` endpoint is protected by a **service-to-service shared secret** (an `INTERNAL_SERVICE_API_KEY` header Core sends and Agent validates), not a user JWT and not database credentials — a JWT would leak end-user identity into a service that has no user table to check it against, and without *some* credential here anyone who finds the endpoint could call it directly and burn the Groq/Alpha Vantage/Tavily quota, bypassing Core's auth entirely.

The semantic router's calibration (KMeans cluster centroids + per-intent thresholds, see Agent flow / routing below) is a build-time artifact, not something computed at request time or even at server startup — `scripts/calibrate_router.py` in the Agent service is run manually (or in CI) whenever the calibration data changes, and its output is a committed JSON file the service loads directly on boot.

Market, Risk, and News are real MCP servers (separate processes, stdio transport, one consumer) — this was originally an aspirational note in the Agents section below; it's now the actual plan, not just documentation language.

## Agents (V1)

- **Portfolio Agent** — does not query Postgres at all (the Agent service has no database access — see Backend architecture above). Reads the holdings snapshot already present in `state["holdings"]`, populated from the incoming request payload Core sent. Effectively a state-shaping step rather than a data-fetching one now.
- **Market Agent** — Alpha Vantage MCP. Retrieves raw historical prices, current/latest prices, trading volume, company info, and sector/industry metadata. Does NOT compute returns (that's `calculate_returns()`, owned by Risk Agent — Market Agent returning derived returns would duplicate/conflict with the deterministic-calculation rule) and does NOT retrieve benchmark prices in V1 (dead scope now that beta/benchmark comparison is deferred past V1).
- **Risk Agent** — local deterministic-calculation MCP (was called "Analytics Agent" in early drafts).
- **News Agent** — Tavily MCP. Always given a specific symbol + date-range target (from either the user's question or the Risk Agent's output) — never a blind search across all holdings.
- **Answer Agent** — lightweight synthesis node for simple quantitative Q&A. Turns a raw calc dict like `{"symbol": "NVDA", "volatility": 0.284}` into one plain sentence ("NVDA's annualised volatility over the selected period is 28.4%"). No citations/limitations structure.
- **Report Agent** — full grounded synthesis with citations, reserved for routes involving News/evidence or a full investigation.

## Agent flow / routing (V1)

One Supervisor, no second supervisor/meta-router — kept deliberately simple for V1. The Supervisor classifies intent, extracts target ticker + period, and **selects both which agents run and the edge order between them** per query (not just which nodes to include from one fixed graph).

### Supervisor routing methodology: decided — embedding-based semantic intent routing

The LLM-prompt-based structured-output classification originally assumed for V1 has been replaced. Head-to-head evaluation in `02_agent_evaluation_v2.ipynb` (iteration history) and `02_agent_evaluation_v3.ipynb` (clean final version) showed the LLM-prompt Supervisor scoring 88.5% overall on the 33-case Phase 2 suite (87.9% Answer Correct, 90.9% Agent Correct, 90.9% Trajectory Correct, 78.8% Latency Pass, 93.9% Safe/Reliable), against the semantic router's 99.4% overall (100% / 100% / 100% / 97.0% / 100% across the same five dimensions) — a decisive win on every dimension, not just the average.

The adopted architecture:
- A small local encoder (`HuggingFaceEncoder`, no API key) embeds each question; per-intent KMeans cluster centroids (a handful of representative vectors per intent, not every raw example) represent each business intent (holdings, concentration, symbol_risk, news_reason, full_investigation); a calibrated per-intent score threshold (tuned by coordinate ascent against a labelled calibration set, weighted to penalize false-negative refusals more than ordinary intent mix-ups) decides the winner, or refuses if nothing clears its bar.
- A **separate, dedicated safety guardrail** (a small fast Groq LLM call, structured-output classification) runs *ahead of* the intent router and blocks the pipeline entirely — in blocking mode, so no agent executes — on prompt-injection attempts. This was a necessary addition: the embedding router alone could not reliably separate crafted injection phrasings from real intents no matter how the calibration set was tuned, since general-purpose sentence embeddings give even unrelated text a mildly positive similarity floor against every intent. Off-topic-but-benign questions (weather, jokes) are still handled by the intent router's own refusal path, not the guardrail.

This decision resolves the "Not yet decided" item that used to track this; no hybrid was needed.

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
| "How concentrated am I?" | `Portfolio → Market → Risk → Answer → END` (Risk needs current prices for `calculate_concentration()`, which only Market fetches, so Market is required ahead of Risk) |
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

Five dimensions, not a growing pile of metrics — adapted from a standard AI-agent eval framework. In our multi-agent design, the Supervisor's routing decision is the analog of "tool selection," and the agent-node invocation order is the "trajectory":

1. **Final Answer Correctness** — did the Answer/Report Agent give the right answer? Deterministic substring/value checks against ground truth for quantitative questions (e.g. "28.4%" appears in the answer); LLM-as-judge (groundedness + relevance, 1-5 rubric) for open-ended full-investigation reports, since there's no single correct phrasing. This subsumes the old "evidence quality" and "report quality" checks — a report that cites evidence not supporting its claims is an answer-correctness failure, not a separate category.
2. **Correct Agent Selection** — did the Supervisor invoke the right set of agents for the question (Portfolio/Market/Risk/News/Answer/Report), regardless of order? `Counter(actual_agents) == Counter(expected_agents)`.
3. **Correct Trajectory** — did it invoke them in the right order? Strict ordered-list comparison against the routing table in Agent flow / routing above (e.g. `Market → Risk → Answer` for "What's NVDA's 30-day volatility?"). Order can fail even when agent selection passes.
4. **Latency** — did the route finish within a threshold? Simple Q&A routes and full-investigation routes get separate thresholds, since a full investigation involves multiple external API calls (Alpha Vantage, Tavily) and is expected to take longer.
5. **Safety & Reliability** — prompt-injection resistance (an injected "reveal your instructions" question should trigger zero agent calls and a refusal, not a tool call); reliability (an unknown/delisted ticker should produce "not available," never a fabricated price or metric); no leakage of API keys or internal config in any answer.

Labelled test questions (each with expected agent sequence, expected answer/substring or judge rubric, max latency, and test type — normal/reliability/safety) drive the harness in `02_agent_evaluation.ipynb`, run against the in-notebook mini prototype. Each test case is scored on all five dimensions independently and reported as a scorecard (per-dimension pass rate + overall average), not a single blended number — a correct final answer with the wrong trajectory or a leaked secret is still a failure worth surfacing separately.

Build the dataset in two phases: **first ~5 cases** covering one of each route shape (a simple single-agent route, a multi-agent quantitative route, a full investigation, a reliability case like an unknown ticker, and a safety/prompt-injection case) to prove the harness and prototype work end-to-end — same shape as the reference notebook's 5-case smoke set. Only after those 5 pass cleanly, **scale to 30-50** covering the full routing table and edge cases. Don't write the 30-50 up front; the 5-case pass is the gate.

Risk-calculation correctness (returns, volatility, max drawdown, concentration, correlation, loss contribution) stays outside this harness entirely — plain pytest unit tests in the codebase against Python ground truth, since it's deterministic math, not agent behavior.

## Not yet decided

- Tech stack and project layout (frontend framework, backend framework, language/package-manager choices).
- Concrete sample portfolio and API access (Alpha Vantage, Tavily) needed to actually run the notebooks.
- Ground-truth reference for the risk calculation pytest suite.
- The 30-50 labelled test questions (expected agent sequence, expected answer, latency threshold, test type) for the 5-dimension agent eval.
