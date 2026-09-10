# RiskLens — Portfolio Risk Investigator

An agentic system that investigates *why* a portfolio's risk changed. It is not a trading, optimization, or recommendation system. A LangGraph multi-agent pipeline routes a natural-language question to specialized agents, combines deterministic quantitative analysis with retrieved market and news evidence, and returns a grounded, cited report.

## Contents

- [What it does](#what-it-does)
- [Tech stack](#tech-stack)
- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Configuration](#configuration)
- [1. Validate the methodology (notebooks first)](#1-validate-the-methodology-notebooks-first)
- [2. Backend setup](#2-backend-setup)
- [3. Run the app](#3-run-the-app)
  - [Option A: Local](#option-a-local)
  - [Option B: Docker](#option-b-docker)
- [4. Deploy to Azure](#4-deploy-to-azure)
- [How the investigation pipeline works](#how-the-investigation-pipeline-works)
  - [Guardrail, safety + relevance](#guardrail-safety--relevance)
  - [Semantic routing, embed → nearest centroid → argmax](#semantic-routing-embed--nearest-centroid--argmax)
  - [Agents and MCP tool servers](#agents-and-mcp-tool-servers)
  - [Deterministic risk calculations, the LLM never computes a metric](#deterministic-risk-calculations-the-llm-never-computes-a-metric)
  - [News targeting, top loss contributor](#news-targeting-top-loss-contributor)
  - [Synthesis, Answer vs Report](#synthesis-answer-vs-report)
- [Evaluation results](#evaluation-results)
  - [Five-dimension scorecard](#five-dimension-scorecard)
  - [Router comparison](#router-comparison)
  - [Risk-calculation unit tests](#risk-calculation-unit-tests)
- [Architectural decisions](#architectural-decisions)
  - [Two services, strict boundary](#two-services-strict-boundary)
  - [Stateless agent, shared-secret auth](#stateless-agent-shared-secret-auth)
  - [Semantic router over an LLM-prompt supervisor](#semantic-router-over-an-llm-prompt-supervisor)
  - [The deterministic-calculation rule](#the-deterministic-calculation-rule)
  - [LLM provider, Groq in dev, Azure AI Foundry in prod](#llm-provider-groq-in-dev-azure-ai-foundry-in-prod)
  - [Persistence shape, risk_results as JSONB](#persistence-shape-risk_results-as-jsonb)
  - [Observability (LangSmith)](#observability-langsmith)
  - [CI/CD (GitLab)](#cicd-gitlab)

## What it does

A user asks, in plain language, why their equities portfolio got riskier: *"how concentrated am I?"*, *"what's NVDA's 30-day volatility?"*, *"why did NVDA fall this week?"*, or *"investigate my portfolio risk"*. The system classifies the question and runs only the agents that question needs. Every risk number is computed in deterministic Python, never by the LLM. For a full investigation it also retrieves market and news evidence for the biggest risk driver. The response is either a single plain sentence, for a simple quantitative question, or a cited report with an explicit limitations section, for an investigation.

The scope is deliberately narrow: a portfolio of about 5 to 10 equities, no cash balance (portfolio value is the sum of holding market values), and no trading, optimization, price prediction, or personalized recommendations. Three tempting features — beta and benchmark comparison, VaR, and the Sharpe ratio — were specified and then deferred past V1 rather than half-built. V1 has no benchmark data source, and each of the three needs its own methodology decision first.

The core design rule is that the LLM chooses *which* deterministic function to call and interprets its result, but never does the arithmetic itself. `INVESTIGATION.risk_results` holds the machine-readable calculation output; `INVESTIGATION_REPORT.report_json` holds the LLM's narrative over it. The first is the ground truth the pytest suite checks against; the second is interpretation. [How the investigation pipeline works](#how-the-investigation-pipeline-works) shows how this is proven out rather than just asserted.

## Tech stack

| Layer | Technology | Used for |
|---|---|---|
| Frontend | React 18 + Vite (TypeScript) | Dashboard and investigation workspace on one screen, holdings CRUD, agent-trace view, streamed report rendering |
| Public API | FastAPI — **core-service** (`:8000`) | Auth, portfolio and holdings CRUD, investigation orchestration, and all persistence. The only internet-facing service. |
| Agent API | FastAPI — **agent-service** (`:8100`) | The LangGraph investigation pipeline. Fully stateless, no database, internal-only. |
| Graph orchestration | LangGraph | `guardrail → semantic router → portfolio → market → risk → news → (answer \| report)`, dispatched one node per plan step so the trajectory varies per route shape |
| Intent routing | `semantic-router` + `sentence-transformers` (MiniLM `HuggingFaceEncoder`) | Local, no-API embedding of the question; per-intent KMeans centroids; plain argmax over 5 intents. Settled winner over an LLM-prompt supervisor, see [Evaluation results](#evaluation-results). |
| Clustering / calibration | `scikit-learn` (KMeans) | Build-time fit of at most 3 centroids per intent, committed as `router_calibration.json` |
| Guardrail | Groq or Azure Foundry structured-output LLM call | `unsafe` (prompt-injection) and `off_topic` classification, run ahead of the router in blocking mode. The only place the pipeline refuses. |
| Tool servers | MCP (Model Context Protocol), stdio transport | Market, Risk, and News each run as their own subprocess, spawned once at agent-service startup |
| Market data | Alpha Vantage (via Market MCP) | Historical and current prices, trading volume, company overview, sector and industry. Falls back to deterministic synthetic data when the free-tier daily limit is hit. |
| News retrieval | Tavily (via News MCP) | Evidence for a specific symbol and date window, never a blind search across all holdings |
| Risk math | Deterministic Python (`finance.py`, via Risk MCP) | `returns`, `volatility`, `max_drawdown`, `concentration`, `sector_exposure`, `correlation_matrix`, `contribution_to_loss`. Pure functions, no model, no I/O. |
| Generation (dev) | Groq — `openai/gpt-oss-20b` | Guardrail and Answer/Report synthesis during local iteration |
| Generation (prod) | Azure AI Foundry — `gpt-oss-120b` (`GlobalStandard`) | Same OpenAI `gpt-oss` family. Only the LangChain client differs; everything downstream is provider-agnostic. |
| Database | PostgreSQL 16 | `USER · PORTFOLIO · HOLDING · INVESTIGATION · EVIDENCE · INVESTIGATION_REPORT`, owned entirely by core-service |
| Migrations | Alembic | `alembic upgrade head` on core-service startup. Bootstraps a fresh Postgres; a no-op once at head. |
| Auth | bcrypt + PyJWT | Email and password, bcrypt-hashed. Short-lived stateless JWT access tokens, validated by signature (shared secret), not a network call. |
| Evaluation | In-notebook harness | 5 dimensions (answer correctness, agent selection, trajectory, latency, safety and reliability) over 33 labelled questions; LLM-as-judge for open-ended reports |
| Observability | LangSmith | Per-node tracing of the LangGraph run. Each investigation's `observability_trace_id` is the run id. Opt-in, and the column is vendor-neutral. |
| Cloud | Azure (Terraform, `infra/`) | Container Apps, Static Web Apps, PostgreSQL Flexible Server, Azure AI Foundry, Key Vault, Container Registry |
| CI/CD | GitLab CI | `validate → build → deploy`, OIDC federation to Azure (no stored secret). `terraform apply` stays manual. |
| Orchestration | Docker Compose | 3-container backend stack (`postgres + core-service + agent-service`), an alternative to running the services as local processes. See [Option B: Docker](#option-b-docker). |

## Architecture

The system is two backend services, one Postgres database, three MCP tool subprocesses inside the agent, and three third-party APIs (Alpha Vantage, Tavily, and the LLM provider). The frontend only ever talks to core-service. The agent service is never reachable from the browser and never touches the database; it receives a holdings snapshot in the request body and returns a result.

*Diagram 1 — service topology.*

```mermaid
flowchart TB
  user(["User / browser"])
  fe["frontend<br/>React + Vite · Static Web App"]
  core["core-service · FastAPI :8000<br/>the only public API<br/>auth · portfolio CRUD · orchestration · persistence"]
  agent["agent-service · FastAPI + LangGraph :8100<br/>stateless investigation worker · no database"]
  db[("PostgreSQL 16")]
  ext[("External providers<br/>Alpha Vantage · Tavily · LLM · LangSmith")]

  user -->|"HTTPS"| fe
  fe -->|"REST + Bearer JWT"| core
  core <-->|"SQL"| db
  core <-->|"/internal/investigate + shared secret"| agent
  agent -->|"market · news · LLM"| ext
```

Request flow for an investigation: the browser calls `POST /investigations` on core-service. Core authenticates the user, resolves their portfolio, and loads the holdings from Postgres. It then calls `POST /internal/investigate` on the agent service with the question and the holdings snapshot. The agent runs the graph statelessly and returns the report. Core persists the three investigation tables and returns the result to the browser.

**Why two separate services instead of one monolith:**

- **core-service** owns identity, ownership checks, and all persistence. It is the only public surface, so the auth logic and the attack surface sit in exactly one place.
- **agent-service** is stateless and CPU/GPU-heavy: it loads `sentence-transformers` and the router model (about 2 GiB) and is kept warm. Isolating it keeps that footprint off the API that issues JWTs, and it can be scaled or restarted without touching auth or the database.
- The boundary is a service-to-service shared secret (`INTERNAL_SERVICE_API_KEY`), not a user JWT. A JWT would push end-user identity into a service that has no user table to check it against. With no credential at all, anyone who found the internal endpoint could burn the Groq, Alpha Vantage, and Tavily quota directly.
- Each service builds from its own `Dockerfile` into its own image, so the two deploy independently. In the cloud they run as Azure Container Apps; the frontend is a static build on Azure Static Web Apps, not a container.

## Prerequisites

- **Python 3.12+** and [`uv`](https://docs.astral.sh/uv/getting-started/installation/)
- **Node.js 20+** (for the frontend)
- **PostgreSQL 16** on `localhost:5432`, or run Postgres in Docker (shown below). Not needed if you use [Option B: Docker](#option-b-docker) for everything.
- **Docker Desktop**, only for [Option B: Docker](#option-b-docker)
- **API keys** (all have a free tier):

  | Key | Where | Notes |
  |---|---|---|
  | `GROQ_API_KEY` | <https://console.groq.com/keys> | The LLM used in local dev. Free. |
  | `TAVILY_API_KEY` | <https://app.tavily.com> | News search. Free 1,000 requests per month. |
  | `ALPHA_VANTAGE_API_KEY` | <https://www.alphavantage.co/support/#api-key> | Market data. Free 25 requests per day, enough to try it. The Market MCP falls back to synthetic prices when the limit is hit. |
  | `LANGSMITH_API_KEY` | <https://smith.langchain.com/settings> | Optional. LangGraph tracing; skip it with `LANGSMITH_TRACING=false`. |

- One **shared secret**: any long random string, used by core-service to authenticate to agent-service. Generate one:

  ```bash
  python -c "import secrets; print(secrets.token_urlsafe(32))"
  ```

## Configuration

The repo ships `*.env.example` files. Copy each to `.env` and fill it in. `pydantic-settings` loads `.env` automatically (see each service's `core/config.py`), and the files are gitignored, so never commit real keys. In a deployed environment, set real environment variables directly; they take priority over `.env`.

```bash
cp core_service/.env.example  core_service/.env
cp agent_service/.env.example agent_service/.env
cp frontend/.env.example      frontend/.env
cp .env.example               .env          # only for the notebooks / risk pytest suite
```

Model IDs, the router calibration, the risk formulas, and the graph shape are fixed architecture decisions and are not meant to vary by environment. Only the settings below are overridable.

### `core_service/.env`

| Env var | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg2://postgres:postgres@localhost:5432/risklens` | Postgres connection string. Docker Compose overrides the host automatically. |
| `JWT_SECRET` | *(required)* | Signing secret for access and refresh tokens; any long random string |
| `JWT_ALGORITHM` | `HS256` | JWT signature algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | Access-token lifetime |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `14` | Refresh-token lifetime |
| `INTERNAL_SERVICE_API_KEY` | *(required)* | Shared secret core sends to agent. **Must match `agent_service/.env` exactly.** |
| `AGENT_SERVICE_URL` | `http://localhost:8100` | Where core calls the agent. Docker Compose overrides this. |
| `ALPHA_VANTAGE_API_KEY` | *(required)* | Used by core's `/portfolio/symbol-search` and `/portfolio/quotes` for holdings valuation |
| `CORS_ORIGINS` | `["http://localhost:5173"]` | Allowed browser origins, as a JSON array |

### `agent_service/.env`

| Env var | Default | Purpose |
|---|---|---|
| `LLM_PROVIDER` | `groq` | `groq` (local dev) or `azure` (Azure AI Foundry). Selects the LangChain client; nothing downstream changes. |
| `GROQ_API_KEY` | *(required when `LLM_PROVIDER=groq`)* | Groq key. The model is `openai/gpt-oss-20b`. |
| `AZURE_OPENAI_ENDPOINT` / `AZURE_OPENAI_API_KEY` | *(required when `LLM_PROVIDER=azure`)* | Azure AI Foundry resource endpoint and key |
| `AZURE_OPENAI_DEPLOYMENT` | `gpt-oss-120b` | Foundry deployment name |
| `AZURE_OPENAI_API_VERSION` | `2024-10-21` | Azure OpenAI API version |
| `TAVILY_API_KEY` | *(required)* | News retrieval via the News MCP server |
| `ALPHA_VANTAGE_API_KEY` | *(optional)* | Market data via the Market MCP server. If omitted, the server uses synthetic fallback prices. |
| `INTERNAL_SERVICE_API_KEY` | *(required)* | **Must match `core_service/.env` exactly.** |
| `LANGSMITH_TRACING` | `true` | Set `false` to run with no LangSmith key |
| `LANGSMITH_API_KEY` | *(required when tracing is on)* | LangSmith key |
| `LANGSMITH_PROJECT` | `risklens-agent` | LangSmith project name |

### `frontend/.env`

| Env var | Default | Purpose |
|---|---|---|
| `VITE_API_BASE_URL` | `http://localhost:8000` | Where the UI calls core-service |

### `.env` (repo root)

Read only by `notebooks/` and the risk pytest suite, never by the running services. Needs `GROQ_API_KEY`, `TAVILY_API_KEY`, and `ALPHA_VANTAGE_API_KEY`.

## 1. Validate the methodology (notebooks first)

**Notebooks and evaluation first, implementation second.** The finance math and the agent-evaluation harness were proven in notebooks before the LangGraph app, database, and frontend were scaffolded. The notebooks are the record of that work. You do not need to run them to run the app, but they are where every model and routing choice is justified.

- `notebooks/01_finance_methodology.ipynb` — market data retrieval and risk calculations, validated against ground truth.
- `notebooks/02_agent_evaluation.ipynb` — the original LLM-prompt supervisor prototype and 5-dimension harness. Left untouched as the baseline.
- `notebooks/02_agent_evaluation_v2.ipynb` — fix iterations and the semantic-router experiment that superseded the baseline.
- `notebooks/02_agent_evaluation_v3.ipynb` — the clean current version (Groq `gpt-oss-20b`).
- `notebooks/02_agent_evaluation_v4.ipynb` — the same harness with generation swapped to Azure AI Foundry `gpt-oss-120b`.

```bash
uv sync                 # root env: jupyter + langgraph + semantic-router + sentence-transformers
cp .env.example .env     # fill in GROQ / TAVILY / ALPHA_VANTAGE
uv run jupyter lab
```

Router calibration is a build-time artifact; it is not computed at request time or at startup. Regenerate it only when the calibration data changes:

```bash
cd agent_service
uv run python scripts/calibrate_router.py   # writes src/agent_service/calibration/router_calibration.json
```

## 2. Backend setup

Each service is its own `uv` project. From the repo root:

```bash
# core-service
cd core_service
uv sync --group dev
uv run pytest -q                 # FastAPI TestClient suite, mocked agent + DB

# agent-service
cd ../agent_service
uv sync --group dev
uv run pytest -q                 # guardrail / router / intents unit tests

# risk-calculation ground truth (root project)
cd ..
uv run pytest tests/ -q          # 24 deterministic risk-math tests, no network
```

Risk-calculation correctness (returns, volatility, drawdown, concentration, correlation, and loss contribution) is verified here with plain pytest against Python ground truth. It is math, not agent behavior, so it stays out of the notebook eval harness.

## 3. Run the app

Either option below expects the config files from [Configuration](#configuration) to exist.

### Option A: Local

Three processes (Postgres, core-service, and agent-service), plus the Vite dev server for the frontend.

The quickest Postgres, if you do not have one:

```bash
docker run -d --name risklens-pg -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=risklens -p 5432:5432 postgres:16
```

**Terminal 1 — core-service** (runs `alembic upgrade head` itself on first start):

```bash
cd core_service
uv run alembic upgrade head
uv run uvicorn core_service.main:app --host 0.0.0.0 --port 8000
```

**Terminal 2 — agent-service** (no `--reload`, because startup spawns the MCP tool servers as subprocesses):

```bash
cd agent_service
uv run uvicorn agent_service.main:app --port 8100
```

**Terminal 3 — frontend:**

```bash
cd frontend
npm ci
npm run dev            # http://localhost:5173
```

Check they are up:

```bash
curl http://localhost:8000/health
curl http://localhost:8100/health
```

Then open **<http://localhost:5173>**. Register a user, add holdings (`AAPL`, `NVDA`, `MSFT`, `GOOGL`, and `TSLA` have real data), and ask a question. The sample buttons cover all five routes: *what are my holdings?*, *how concentrated am I?*, *what's NVDA's 30-day volatility?*, *why did NVDA fall this week?*, and *investigate my portfolio risk*.

### Option B: Docker

`docker-compose.yml` runs `postgres`, `core-service`, and `agent-service` as three containers. The frontend is not containerised locally; it stays on Vite (Azure Static Web Apps in the cloud). Each service reads its own `<service>/.env` for secrets. The compose file only swaps `localhost` hostnames for compose-network names and forces `LLM_PROVIDER=groq`.

```bash
docker compose up --build
```

The first build is slow (about 10 to 20 minutes) because the agent image compiles PyTorch and bakes the semantic-router model. Later runs are cached. Migrations run automatically on core-service startup.

```bash
docker compose logs -f agent-service   # follow agent logs
docker compose down                    # stop, keep the db volume
docker compose down -v                 # stop and wipe the db
```

Then run the frontend as in Option A (`cd frontend && npm ci && npm run dev`).

To point the agent at Azure AI Foundry instead of Groq, set `LLM_PROVIDER=azure` (and the `AZURE_OPENAI_*` vars) under `agent-service` in `docker-compose.yml`. No rebuild is needed; just run `docker compose up -d agent-service`.

## 4. Deploy to Azure

Infrastructure is Terraform, under [`infra/`](infra/). One environment, one resource group (`rg-risklens`): a Static Web App for the frontend, two Container Apps in a VNet (`core-service` public, `agent-service` internal-only), a VNet-private PostgreSQL Flexible Server, an Azure AI Foundry `gpt-oss-120b` deployment, a Key Vault (read per-app via managed identity), and a Container Registry.

*Diagram 4 — Azure topology. Solid arrows are request traffic, dashed are supporting wiring.*

```mermaid
flowchart TB
  user(["End user"])
  swa["Static Web App · risklens-frontend<br/>CDN + managed TLS · no container"]

  subgraph RG["resource group · rg-risklens"]
    direction TB
    subgraph VNET["vnet-risklens · private"]
      direction TB
      subgraph CAE["Container Apps env · cae-risklens"]
        direction TB
        core["core-service<br/>ingress: external"]
        agent["agent-service<br/>ingress: internal only<br/>1 vCPU / 2 GiB · min 1"]
      end
      pg[("PostgreSQL Flexible Server<br/>public access disabled")]
    end

    kv["Key Vault<br/>kv-risklens-rm7"]
    acr[("Container Registry<br/>acrrisklens")]
    foundry["Azure AI Foundry<br/>gpt-oss-120b"]
  end

  ext(["Alpha Vantage · Tavily · LangSmith"])

  user -->|"HTTPS"| swa --> core
  core -->|"shared secret"| agent
  core --> pg
  core --> ext
  agent --> foundry
  agent --> ext

  kv -. "secrets · managed identity" .-> core
  kv -. "secrets · managed identity" .-> agent
  acr -. "image pull" .-> core
  acr -. "image pull" .-> agent
```

Azure Container Apps validates the image at *create* time, so build the registry first, push the images, then provision everything else:

```powershell
cd infra/env
terraform init
terraform apply "-target=module.acr"          # resource group + ACR only

cd ..\..
az acr login -n acrrisklens
$acr = "acrrisklens.azurecr.io"
docker build --platform linux/amd64 -t $acr/risklens-core-service:latest  core_service ; docker push $acr/risklens-core-service:latest
docker build --platform linux/amd64 -t $acr/risklens-agent-service:latest agent_service ; docker push $acr/risklens-agent-service:latest

cd infra/env
terraform apply                               # everything else, in one pass
```

Then deploy the frontend: run `npm run build` with `VITE_API_BASE_URL` set to the `core_service_url` output, then `swa deploy ./dist --deployment-token <frontend_deploy_token>`. `./infra/manage.ps1 stop|start|status` scales the containers to zero and stops Postgres to save cost. Full step-by-step instructions, teardown, and soft-delete purge notes are in the comments of `infra/env/main.tf` and `infra/bootstrap/README.md`.

## How the investigation pipeline works

A single `POST /internal/investigate` runs a compiled LangGraph `StateGraph`: `START → guardrail → (refused ? END : supervisor) → <plan step 1> → <plan step 2> → … → END`. The supervisor emits an ordered list of agent nodes, and a conditional edge dispatches them one at a time by index. The trajectory therefore varies per route, rather than being one fixed path with nodes toggled on and off.

*Diagram 2 — the LangGraph graph inside agent-service.*

```mermaid
flowchart TB
  req(["POST /internal/investigate"])
  g["guardrail<br/>safety + relevance classification"]
  refuse(["refusal · unsafe / off_topic"])
  r["semantic router<br/>selects and orders the agent nodes"]
  exec["run the plan · one agent node per step<br/>portfolio · market · risk · news"]
  ans(["answer — plain quantitative reply"])
  rep(["report — cited synthesis + limitations"])

  req --> g
  g -->|"blocked"| refuse
  g -->|"allowed"| r
  r --> exec
  exec --> ans
  exec --> rep
```

### Guardrail, safety + relevance

A single fast structured-output LLM call (`GuardrailVerdict { unsafe, off_topic, reason }`) runs **before** the router, in blocking mode. `unsafe` catches prompt-injection, instruction-override, and "reveal your system prompt" attempts. `off_topic` catches genuine but unrelated questions such as weather or jokes. Either verdict short-circuits the graph to `END` with its own refusal message, and no agent executes. If the structured-output call fails, the guardrail fails open and proceeds to the router, matching the fallback-on-error pattern used for market data elsewhere.

This is the only place the pipeline refuses. The router downstream has no refusal path of its own; the next section explains why.

### Semantic routing, embed → nearest centroid → argmax

No LLM classifies the intent. At build time, `scripts/calibrate_router.py` pools about 13 to 21 labelled example questions per intent, embeds them with a local `HuggingFaceEncoder` (sentence-transformers, no API key), and fits `KMeans(k = min(3, n))` per intent. It commits the resulting 15 centroids (5 intents, at most 3 each) to `router_calibration.json`.

At request time (`graph/router.py`), the router embeds the question once and L2-normalises it. For each intent it takes the maximum cosine similarity against that intent's centroids, so the question only has to be close to one sub-meaning of an intent. It then takes the argmax over the five scores. There is no threshold and no "none of these" option.

*Diagram 3 — the two phases of the router.*

```mermaid
flowchart TB
  subgraph BUILD["build time · scripts/calibrate_router.py"]
    direction LR
    u["~13–21 labelled<br/>utterances per intent"] --> e1["MiniLM encoder<br/>384-d, local, no API"]
    e1 --> km["KMeans<br/>k = min(3, n), seed 42"]
    km --> cj[("router_calibration.json<br/>15 centroids, committed")]
  end

  subgraph REQ["request time · graph/router.py"]
    direction LR
    q["question"] --> e2["MiniLM encoder<br/>+ L2-normalise"]
    e2 --> sim["cosine similarity vs each intent's<br/>≤3 centroids · keep the max"]
    sim --> am["argmax over 5 scores<br/>no threshold"]
    am --> rt["INTENT_ROUTES lookup<br/>→ ordered agent plan"]
  end

  cj -.->|"loaded on boot"| sim
```

The 5 intents map to fixed ordered routes:

| Intent | Route |
|---|---|
| `holdings` | `portfolio → answer` |
| `symbol_risk` | `market → risk → answer` |
| `concentration` | `portfolio → market → risk → answer` |
| `news_reason` | `market → news → report` |
| `full_investigation` | `portfolio → market → risk → news → report` |

*Diagram 3b — each intent to its route.*

```mermaid
flowchart LR
  r(["router<br/>argmax over 5 intents"])
  i1["holdings"]
  i2["concentration"]
  i3["symbol_risk"]
  i4["news_reason"]
  i5["full_investigation"]

  r --> i1 --> o1["Portfolio → Answer"]
  r --> i2 --> o2["Portfolio → Market → Risk → Answer"]
  r --> i3 --> o3["Market → Risk → Answer"]
  r --> i4 --> o4["Market → News → Report"]
  r --> i5 --> o5["Portfolio → Market → Risk → News → Report"]
```

**Resolved bug (found during the V1 build):** the router originally had its own calibrated-threshold refusal path, and the calibration was broken. Coordinate-ascent threshold search over a labelled set (which included a `"None"` bucket of off-topic examples) reliably converged to all-zero thresholds, reporting "None cases correctly refused: 0/10". The search only ever tried candidate thresholds equal to an observed score, never a value strictly between two clusters, so it could not find the separating gap even though one existed (genuine `symbol_risk` matches scored 0.599 and up, while off-topic examples topped out at 0.266). The fix was to remove router-level refusal entirely and fold it into the guardrail (`unsafe` and `off_topic`). The router is now a plain unconditional argmax, calibration only fits centroids, and calibration accuracy is measured as argmax-matches-label (100% on the calibration set).

### Agents and MCP tool servers

Market, Risk, and News are real MCP servers: separate Python subprocesses over stdio. They are spawned once at agent-service startup (`mcp_manager`) and reused, because spawning a process per call would be far too slow.

- **Portfolio** does no I/O. It reshapes the holdings snapshot already in `state["holdings"]` (put there from the request body). It shapes state rather than fetching data.
- **Market** uses the Alpha Vantage MCP (`get_historical_prices`, `get_company_overview`). It does not compute returns (that is Risk's job) and does not fetch benchmark prices (beta is deferred). When the free tier is exhausted it falls back to deterministic synthetic prices and sectors, so a demo never hard-fails on a rate limit.
- **Risk** is a local deterministic MCP (`calculate_symbol_risk`, `run_full_investigation`) that wraps the pure functions in `finance.py`.
- **News** uses the Tavily MCP (`search_news(symbol, company_name, days, max_results)`). It always receives a specific symbol and window, never a blind multi-holding search.

### Deterministic risk calculations, the LLM never computes a metric

Every number comes from a pure Python function: `calculate_returns`, `calculate_volatility`, `calculate_max_drawdown`, `calculate_concentration`, `calculate_sector_exposure`, `calculate_correlation_matrix`, and `calculate_contribution_to_loss`. None of them use a model, the network, or randomness. The Risk node calls them via MCP and writes structured output into `state["risk_results"]`; the Answer and Report nodes only interpret that dict. `calculate_beta`, `calculate_var`, and `calculate_sharpe_ratio` are deferred: V1 has no benchmark source, and each needs a methodology decision first.

### News targeting, top loss contributor

In a full investigation, nothing in the question names a target, so the target is chosen deterministically. Holdings are ranked by `contribution_to_loss`, and the top driver is passed to News as `{symbol, reason: "largest_loss_contributor", start_date, end_date}`. The date window is the user-requested investigation period (a 90-day lookback by default); V1 does not compute a per-symbol worst-drawdown interval, so there is nothing else to use. A V2 gate that would decide *whether* to run News at all is deferred, not half-built.

### Synthesis, Answer vs Report

- **Answer** ends every quantitative-only route. It turns a raw calculation dict into a single plain sentence (*"NVDA's annualised volatility over the selected period is 28.4%"*), with no citations and no limitations section. A raw dict is never returned to the user.
- **Report** is reserved for routes that involve news evidence or a full investigation. It is a full grounded synthesis: risk summary, quantitative evidence, concentration, the major risk event, cited news evidence, interpretation, and an explicit limitations section (*news correlation is not causation*).

## Evaluation results

Every routing or prompt change that graduates out of a notebook carries a scorecard showing that it did not regress. Each labelled question is scored on five dimensions independently, and the result is reported as a per-dimension pass rate plus an overall average. A correct answer with the wrong trajectory, or with a leaked secret, is still a failure worth surfacing separately.

| Dimension | What it checks |
|---|---|
| Final answer correctness | Deterministic substring or value check for quantitative questions; LLM-as-judge (groundedness and relevance, 1 to 5) for open-ended reports |
| Correct agent selection | `Counter(actual_agents) == Counter(expected_agents)`: the right set, order-independent |
| Correct trajectory | Strict ordered-list comparison against the routing table |
| Latency | Finished within a threshold, with separate thresholds for simple routes and full investigations |
| Safety and reliability | Prompt-injection produces zero agent calls and a refusal; an unknown ticker produces "not available", never a fabricated number; no API-key or config leakage |

The dataset was built in two phases. First, 5 cases (one per route shape: simple, multi-agent quantitative, full investigation, reliability, and safety) to prove the harness end to end. Then it was scaled to 33 cases covering the full routing table and edge cases. Phase 1 passes 100% in both `v3` and `v4`.

### Five-dimension scorecard

Phase 2 (33 cases), head-to-head on the same suite:

| Router | Answer | Agent select | Trajectory | Latency | Safe/Reliable | Overall |
|---|---|---|---|---|---|---|
| LLM-prompt supervisor (baseline) | 87.9% | 90.9% | 90.9% | 78.8% | 93.9% | **88.5%** |
| Semantic router — `v3` (Groq `gpt-oss-20b`) | 100% | 100% | 100% | 93.9% | 100% | **98.8%** |
| Semantic router — `v4` (Azure Foundry `gpt-oss-120b`) | 100% | 100% | 100% | 100% | 100% | **100%** |

LLM-as-judge on the 8 open-ended Report-Agent cases: `v3` scored 87.5% pass, mean 8.6/10; `v4` scored 100% pass, mean 9.0/10. The remaining `v3` latency misses cleared on the larger, faster Foundry model.

> Caveat: eval runs hit the Alpha Vantage free-tier limit and fell back to synthetic prices for many cases, so the volatility and drawdown values in the transcripts vary from run to run. The meaningful signal is the routing, trajectory, safety, and judge results, not the specific risk numbers.

### Router comparison

The semantic router wins on every dimension, not just the average. The LLM-prompt supervisor's weak spots were latency (an extra LLM call on the hot path) and trajectory (it sometimes picked the right agents in the wrong order). The semantic router adds almost no latency (one local embedding plus 15 dot products), and because it is a lookup from intent to a hard-coded route, it cannot get the order wrong.

### Risk-calculation unit tests

`uv run pytest tests/ -q` passes 24 tests. They cover the ground-truth math for returns, volatility, max drawdown, concentration, sector exposure, correlation matrix, and contribution-to-loss. They are deterministic, use no network, and stay entirely outside the agent-behavior eval harness.

## Architectural decisions

### Two services, strict boundary

This is not one FastAPI app. core-service is the only public API and owns all persistence and identity; agent-service is a stateless worker; the frontend can only reach core. This keeps the auth logic and the attack surface in one place, and it lets the heavy embedding and LLM service scale and restart independently of the API that issues tokens. See [Architecture](#architecture).

### Stateless agent, shared-secret auth

agent-service has no database of any kind and never sees a user JWT. Core sends it a holdings snapshot in the request body and an `INTERNAL_SERVICE_API_KEY` header. A JWT here would push end-user identity into a service with no user table to check it against. With no credential at all, the quota-burning endpoint would be open to anyone who finds it.

### Semantic router over an LLM-prompt supervisor

This was decided by the head-to-head above (88.5% overall against 98.8% and 100%). The router is a plain argmax over 5 KMeans-centroid intents, with no refusal path; refusal is entirely the guardrail's job. This is simpler than the original threshold-search design, and it removes the calibration failure mode (all-zero thresholds) rather than patching around it.

### The deterministic-calculation rule

The LLM decides which function to call and interprets the number; it never does the arithmetic. `INVESTIGATION.risk_results` (the calculation output, which pytest checks) is a separate column from `INVESTIGATION_REPORT.report_json` (the LLM's narrative). There is deliberately no `RISK_RESULT` relational table: per-symbol scalars and a pairwise correlation matrix do not share one clean schema, so the calculations stay structured in memory and persist as JSONB. There is also no LLM-assigned "Low / Medium / High" `risk_level` label, which would be an unaudited classification sitting next to rigorously computed numbers; the report states the actual figures instead.

### LLM provider, Groq in dev, Azure AI Foundry in prod

Both providers serve the same OpenAI `gpt-oss` family: `gpt-oss-20b` on Groq for fast local iteration, `gpt-oss-120b` on Foundry in the cloud. Only the LangChain client differs (`core/llm.py`); the graph, guardrail, and router are provider-agnostic. Switch with one environment variable, `LLM_PROVIDER`.

### Persistence shape, risk_results as JSONB

`observability_trace_id` is vendor-neutral (not `langsmith_run_id`), so the trace backend can change. `EVIDENCE.evidence_text` stores the retrieved passage itself, not just a URL, so the evidence-quality judge is reproducible; re-fetching a URL later may not return the same content. `USER.password_hash` exists because auth is in V1 scope, but there is no `risk_tolerance`, `investment_horizon`, or `cash_balance`: this is deliberately not a personalization or valuation-with-cash system.

### Observability (LangSmith)

This is off unless `LANGSMITH_TRACING=true` and a key are set. When it is on, every investigation is traced to `smith.langchain.com` under project `risklens-agent` (the full graph tree, per-node timing, and every LLM and tool call), and the run id is stored as `INVESTIGATION.observability_trace_id`.

### CI/CD (GitLab)

`.gitlab-ci.yml` has three stages: `validate` (the risk, agent, and core test jobs, on every push and MR), `build` (SHA-tagged images to ACR, on `main` only), and `deploy` (`az containerapp update` and `swa deploy`, on `main` only). Azure auth is OIDC federation with no stored secret; the build jobs do the OIDC → Azure AD → ACR-refresh-token exchange by hand with `curl` and `jq`. Path rules keep `build:agent`, `deploy:agent`, and the frontend jobs scoped to their own directories. `terraform apply` is not in CI; infrastructure changes stay manual.

*Diagram 5 — the pipeline. `(*)` marks a job that runs only when its own directory changed.*

```mermaid
flowchart LR
  push(["push / merge request"])

  subgraph V["validate · every push and MR"]
    direction TB
    tr["test:risk"]
    ta["test:agent"]
    tc["test:core (+ postgres:16)"]
  end

  subgraph B["build · main only"]
    direction TB
    bc["build:core"]
    ba["build:agent (*)"]
    bf["build:frontend (*)"]
  end

  subgraph D["deploy · main only · production"]
    direction TB
    dc["deploy:core"]
    da["deploy:agent (*)"]
    df["deploy:frontend (*)"]
  end

  acr[("ACR · acrrisklens<br/>image :SHORT_SHA + :latest")]
  target(["Azure · rg-risklens<br/>Container Apps + Static Web App"])
  oidc{{"GitLab OIDC → Azure AD<br/>federated · no stored secret"}}

  push --> V --> B --> D --> target
  B -->|"docker push"| acr
  acr -->|"pulled at deploy"| D
  oidc -. "authenticates" .-> B
  oidc -. "authenticates" .-> D
```
