# RiskLens — Portfolio Risk Investigator

An agentic system that investigates *why* portfolio risk changed. A LangGraph
pipeline routes a natural-language question to specialised agents, combines
deterministic risk calculations with retrieved market and news evidence, and
returns a grounded, cited report.

## Two ways to run it

1. **[Run locally](#run-locally)** — on your machine, with Docker or with `uv` + Node. Start here.
2. **[Deploy to Azure](#deploy-to-azure)** — Terraform-provisioned: Container Apps, Static Web Apps, PostgreSQL Flexible Server, Azure AI Foundry.

## Services

| Service | Stack | Port | Role |
|---|---|---|---|
| `frontend` | React + Vite | 5173 | The UI. Talks only to `core-service`. |
| `core-service` | FastAPI | 8000 | Auth, portfolio CRUD, all persistence, calls the agent. The only public API. |
| `agent-service` | FastAPI + LangGraph | 8100 | The investigation pipeline. Stateless, no DB. Internal-only in the cloud. |
| PostgreSQL | — | 5432 | All persistence. |

---

# Run locally

Written for a fresh clone: no API keys, no `.env` files yet.

## 1. Install the tools

Pick one path:

- **Docker path (simplest):** [Docker Desktop](https://www.docker.com/products/docker-desktop/). That's all you need for the backend; Node is still handy for the frontend.
- **Manual path:** [`uv`](https://docs.astral.sh/uv/getting-started/installation/) (Python), [Node 20+](https://nodejs.org/), and a local **PostgreSQL 16** (or run just Postgres in Docker — shown below).

## 2. Get the API keys (all have a free tier)

| Key | Where | Notes |
|---|---|---|
| `GROQ_API_KEY` | https://console.groq.com/keys | The LLM used in local dev. Free. |
| `TAVILY_API_KEY` | https://app.tavily.com | News search. Free 1,000 requests/month. |
| `ALPHA_VANTAGE_API_KEY` | https://www.alphavantage.co/support/#api-key | Market data. Free 25 requests/day (enough to try it). |
| `LANGSMITH_API_KEY` | https://smith.langchain.com/settings | **Optional** — LangGraph tracing. Skip it by setting `LANGSMITH_TRACING=false`. |

You also need one **shared secret** — any long random string, used by `core-service` to authenticate to `agent-service`. Generate one:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

## 3. Create your local config files

The repo ships `*.env.example` files. Copy each to `.env` and fill in your values.

```bash
cp core_service/.env.example  core_service/.env
cp agent_service/.env.example agent_service/.env
cp frontend/.env.example      frontend/.env
```

Then edit:

**`agent_service/.env`**
- `GROQ_API_KEY` — your Groq key
- `TAVILY_API_KEY` — your Tavily key
- `ALPHA_VANTAGE_API_KEY` — your Alpha Vantage key
- `INTERNAL_SERVICE_API_KEY` — the shared secret from step 2
- `LANGSMITH_API_KEY` — your LangSmith key, **or** set `LANGSMITH_TRACING=false` and leave it as-is
- keep `LLM_PROVIDER=groq`

**`core_service/.env`**
- `JWT_SECRET` — any long random string (a second `token_urlsafe(32)` is fine)
- `INTERNAL_SERVICE_API_KEY` — **the exact same value** as in `agent_service/.env`
- `ALPHA_VANTAGE_API_KEY` — your Alpha Vantage key
- leave `DATABASE_URL`, `AGENT_SERVICE_URL`, `CORS_ORIGINS` as they are (Docker overrides the first two automatically)

**`frontend/.env`** — leave it: `VITE_API_BASE_URL=http://localhost:8000`

### The four `.env` files

| File | Used by | Needed to run the app? |
|---|---|---|
| `agent_service/.env` | `agent-service` | **yes** |
| `core_service/.env` | `core-service` | **yes** |
| `frontend/.env` | Vite build | **yes** |
| `.env` (repo root) | the Jupyter notebooks in `notebooks/` and the risk pytest suite (`src/risklensaidev/`) | **no** — only if you run those |

The root `.env` is the config for the notebook-first evaluation workflow (see
`CLAUDE.md` → "Development approach"), not the running services. If you want to
run `notebooks/01_finance_methodology.ipynb` or the agent-eval notebooks:

```bash
cp .env.example .env
```

and fill in `GROQ_API_KEY`, `TAVILY_API_KEY`, `ALPHA_VANTAGE_API_KEY` — the same
three keys from step 2. It has no shared secret and no LangSmith entry; it's a
smaller subset. Running the app never reads it.

> Your `.env` files, `infra/env/secrets.auto.tfvars`, and Terraform state are
> already in `.gitignore` — don't `git add` them if `git status` surfaces one.
> Only the `*.env.example` files and `infra/env/terraform.tfvars` (region only,
> no secrets) belong in the repo.

## 4. Run it

### 4a. Docker for the backend, Vite for the frontend

`docker-compose.yml` runs the three container tiers — Postgres, `core-service`,
`agent-service` (the frontend isn't containerised; it's Vite here, Static Web
Apps in the cloud).

```bash
docker compose up --build
```

First build is slow (~10–20 min) — the agent image compiles PyTorch and bakes
the semantic-router model; later runs are cached. Database migrations run
automatically on `core-service` startup.

Then, in another terminal:

```bash
cd frontend
npm ci
npm run dev          # http://localhost:5173
```

Handy:

```bash
docker compose logs -f agent-service   # follow agent logs
docker compose down                    # stop, keep the DB
docker compose down -v                 # stop and wipe the DB
```

### 4b. Manual — `uv` + Node, no Docker for the app

You need PostgreSQL 16 on `localhost:5432`, database `risklens`, user `postgres`,
password `postgres` (to match `core_service/.env.example`). Quickest is Docker
for just that:

```bash
docker run -d --name risklens-pg -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=risklens -p 5432:5432 postgres:16
```

**Terminal 1 — core-service**
```bash
cd core_service
uv run alembic upgrade head          # first run only, creates the schema
uv run uvicorn core_service.main:app --host 0.0.0.0 --port 8000
```

**Terminal 2 — agent-service**
```bash
cd agent_service
uv run uvicorn agent_service.main:app --port 8100
```
No `--reload` — startup spawns the MCP tool servers as subprocesses.

**Terminal 3 — frontend**
```bash
cd frontend
npm ci
npm run dev
```

## 5. Use it

Open **http://localhost:5173**:

1. Register a user.
2. Add holdings — use `AAPL`, `NVDA`, `MSFT`, `GOOGL`, `TSLA` (the symbols with real data).
3. Ask a question. The sample buttons cover all five routes:
   - *What are my holdings?*
   - *How concentrated am I?*
   - *What's NVDA's 30-day volatility?*
   - *Why did NVDA fall this week?*
   - *Investigate my portfolio risk*

Health checks: `curl http://localhost:8000/health` and `curl http://localhost:8100/health`.

## Observability (optional)

With `LANGSMITH_TRACING=true` and a real `LANGSMITH_API_KEY` in
`agent_service/.env`, every investigation is traced to
[smith.langchain.com](https://smith.langchain.com) under project `risklens-agent`
— the full graph tree, per-node timing, every LLM and tool call. Each stored
investigation's `observability_trace_id` is the run id.

---

# Deploy to Azure

Infrastructure is in [`infra/`](infra/), provisioned with Terraform. One
environment, one resource group (`rg-risklens`).

| Piece | Azure resource |
|---|---|
| `frontend` | **Static Web App** `risklens-frontend` — a CDN, no container |
| `core-service` / `agent-service` | **Container Apps** in `cae-risklens` (agent has internal-only ingress) |
| Database | **PostgreSQL Flexible Server** `psql-risklens`, VNet-private |
| LLM | **Azure AI Foundry** `risklens-ai-foundry` (eastus2), `gpt-oss-120b` deployment |
| Secrets | **Key Vault** `kv-risklens-rm7`, read via per-app managed identity |
| Images | **Container Registry** `acrrisklens` |

Prereqs: `az` CLI (logged in), `terraform` ≥ 1.9, Docker, Node.

> All `terraform` commands below run from **`infra/env/`**. `docker` / `az acr`
> commands run from the **repo root**.

## 1. One-time setup

- **State backend** — create the storage account that holds Terraform state and
  register the resource providers. Follow
  [`infra/bootstrap/README.md`](infra/bootstrap/README.md) (steps 1–2). Run once
  per subscription.

- **Secrets** — create `infra/env/secrets.auto.tfvars` (**gitignored — never
  commit it**) with:

  ```hcl
  postgres_administrator_password = "..."
  jwt_secret                      = "..."
  internal_service_api_key        = "..."   # any long random string
  alpha_vantage_api_key           = "..."
  tavily_api_key                  = "..."
  langsmith_api_key               = "..."   # lsv2_...
  ```

  The Azure AI Foundry key is **not** here — Terraform reads it off the Foundry
  resource it creates and writes it into Key Vault itself.

## 2. Provision the infrastructure

```powershell
az login
cd infra/env
terraform init
terraform apply
```

This creates everything **except** the two container apps, which fail on the
first apply with `MANIFEST_UNKNOWN` — Azure validates the image at create time
and it doesn't exist yet. That's expected. Build and push the images, then apply
again.

## 3. Build and push the service images

ACR Tasks is disabled on this subscription, so images build locally.

```powershell
az acr login -n acrrisklens
$acr = "acrrisklens.azurecr.io"

docker build --platform linux/amd64 -t $acr/risklens-core-service:latest  core_service
docker push  $acr/risklens-core-service:latest

docker build --platform linux/amd64 -t $acr/risklens-agent-service:latest agent_service
docker push  $acr/risklens-agent-service:latest
```

## 4. Apply again — creates the container apps

```powershell
cd infra/env
terraform apply
terraform output          # frontend_url, core_service_url, acr_login_server, ...
```

`core-service`'s entrypoint runs `alembic upgrade head` on boot, so the schema
self-applies on the new Postgres.

## 5. Deploy the front end

The Static Web App is created empty; the React build is pushed separately.

```powershell
cd frontend
npm ci
$env:VITE_API_BASE_URL = (terraform "-chdir=..\infra\env" output -raw core_service_url)
npm run build
npx --yes @azure/static-web-apps-cli deploy ./dist `
  --deployment-token (terraform "-chdir=..\infra\env" output -raw frontend_deploy_token) `
  --env production
```

Then open the frontend URL — `terraform "-chdir=infra\env" output -raw frontend_url`
from the repo root, or `terraform output -raw frontend_url` from `infra/env/`.

## Redeploying after a code change

- **A service** — rebuild + push its image (step 3), then roll the revision:
  ```powershell
  az containerapp update -g rg-risklens -n core-service  --image $acr/risklens-core-service:latest
  az containerapp update -g rg-risklens -n agent-service --image $acr/risklens-agent-service:latest
  ```
  (`terraform apply` won't roll a revision — the `:latest` tag doesn't change.)
- **The front end** — rerun step 5 (rebuild with the cloud `core_service_url`, then `swa deploy`). Hard-refresh the browser afterward.
- **Infra** — `terraform apply` from `infra/env/`.

## Pausing to save cost

```powershell
./infra/manage.ps1 stop      # stops Postgres, scales the two containers to 0
./infra/manage.ps1 start     # reverses it, restores a warm agent replica
./infra/manage.ps1 status    # Postgres state, replica counts, URLs
```

The Static Web App, Foundry (pay-per-token), ACR, and Key Vault have no idle
cost worth managing and are left running. **Start Postgres (`manage.ps1 start`)
before running `terraform apply` from `infra/env/`** — Terraform can't refresh a
stopped server.
