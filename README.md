# RiskLens — Portfolio Risk Investigator

An agentic system that investigates *why* portfolio risk changed. A LangGraph
pipeline routes a natural-language question to specialised agents, combines
deterministic risk calculations with retrieved market and news evidence, and
returns a grounded, cited report.

See [`CLAUDE.md`](CLAUDE.md) for the full architecture and design rationale.

## Services

| Service | Stack | Port | Role |
|---|---|---|---|
| `frontend` | React + Vite | 5173 | The UI. Talks only to `core-service`. |
| `core-service` | FastAPI | 8000 | Auth, portfolio CRUD, all persistence, calls the agent. The only public API. |
| `agent-service` | FastAPI + LangGraph | 8100 | The investigation pipeline. Stateless, no DB. Internal-only in the cloud. |
| PostgreSQL | — | 5432 | All persistence. |

---

## Running locally

### Prerequisites

- **Docker Desktop** (for the one-command path), or
- **[uv](https://docs.astral.sh/uv/)** + **Node 20+** + a local **PostgreSQL 16** (for the manual path)
- API keys:
  - **Groq** — https://console.groq.com (the LLM in local dev)
  - **Tavily** — https://tavily.com (news search)
  - **Alpha Vantage** — https://www.alphavantage.co/support/#api-key (market data)
  - **LangSmith** *(optional)* — https://smith.langchain.com/settings (LangGraph tracing; set `LANGSMITH_TRACING=false` to skip)

### 1. Environment files

Copy each example and fill in the values:

```bash
cp core_service/.env.example  core_service/.env
cp agent_service/.env.example agent_service/.env
cp frontend/.env.example      frontend/.env
```

Key points:

- **`INTERNAL_SERVICE_API_KEY` must be identical** in `core_service/.env` and
  `agent_service/.env` — it's the shared secret Core uses to call the Agent.
- `frontend/.env` → `VITE_API_BASE_URL=http://localhost:8000`
- `agent_service/.env` → keep `LLM_PROVIDER=groq` for local dev.
- For Docker, `core_service/.env`'s `DATABASE_URL` / `AGENT_SERVICE_URL` are
  overridden by `docker-compose.yml` to use the compose network — you don't
  need to change them.

### 2a. Run with Docker Compose (recommended)

```bash
docker compose up --build
```

Brings up Postgres, `core-service`, `agent-service`, and `frontend`. The first
build is slow (~10–20 min) — the agent image compiles PyTorch and bakes the
semantic-router model. Subsequent runs are cached.

Migrations run automatically (`alembic upgrade head` in the core entrypoint).

Just the backend, and run the frontend separately with Vite:

```bash
docker compose up --build postgres core-service agent-service
# in another terminal:
cd frontend && npm ci && npm run dev
```

Useful:

```bash
docker compose logs -f agent-service   # follow agent logs
docker compose down                    # stop, keep the DB volume
docker compose down -v                 # stop and wipe the DB
```

### 2b. Run manually (no Docker for the app)

You need a PostgreSQL 16 on `localhost:5432` with a database named `risklens`.
(Or run just that in Docker: `docker run -d --name risklens-pg -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=risklens -p 5432:5432 postgres:16`, and set `core_service/.env`'s `DATABASE_URL` to match.)

**Terminal 1 — core-service**

```bash
cd core_service
uv run alembic upgrade head          # first run only
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

### 3. Use it

Open **http://localhost:5173** →

1. Register a user.
2. Add a few holdings — use `AAPL`, `NVDA`, `MSFT`, `GOOGL`, `TSLA` (the known
   symbols with real data).
3. Ask a question. The sample buttons cover all five routes:
   - *What are my holdings?*
   - *How concentrated am I?*
   - *What's NVDA's 30-day volatility?*
   - *Why did NVDA fall this week?*
   - *Investigate my portfolio risk*

Health checks: `curl http://localhost:8000/health` and
`curl http://localhost:8100/health`.

### Observability (optional)

With `LANGSMITH_TRACING=true` and a real `LANGSMITH_API_KEY` in
`agent_service/.env`, every investigation is traced to
[smith.langchain.com](https://smith.langchain.com) under project
`risklens-agent` — the full graph tree, per-node timing, and every LLM/tool
call. Each stored investigation's `observability_trace_id` is the run id.

---

## Deploying to Azure

Infrastructure is in [`infra/`](infra/), provisioned with Terraform. One
environment, one resource group (`rg-risklens`). The cloud topology:

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

### 1. One-time setup

- **State backend** — create the storage account that holds Terraform state,
  and register the resource providers. Follow
  [`infra/bootstrap/README.md`](infra/bootstrap/README.md) (steps 1–2). Run once
  per subscription.

- **Secrets** — create `infra/env/secrets.auto.tfvars` (gitignored) with:

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

### 2. Provision the infrastructure

```powershell
az login
cd infra/env
terraform init
terraform apply
```

This creates everything **except** the two container apps, which fail on the
first apply with `MANIFEST_UNKNOWN` — Azure validates the image at create time
and it doesn't exist yet. That's expected. Build and push the images, then
apply again.

### 3. Build and push the service images

ACR Tasks is disabled on this subscription, so images build locally.

```powershell
az acr login -n acrrisklens
$acr = "acrrisklens.azurecr.io"

docker build --platform linux/amd64 -t $acr/risklens-core-service:latest  core_service
docker push  $acr/risklens-core-service:latest

docker build --platform linux/amd64 -t $acr/risklens-agent-service:latest agent_service
docker push  $acr/risklens-agent-service:latest
```

### 4. Apply again — creates the container apps

```powershell
cd infra/env
terraform apply
terraform output          # frontend_url, core_service_url, acr_login_server, ...
```

`core-service`'s entrypoint runs `alembic upgrade head` on boot, so the schema
self-applies on the new Postgres.

### 5. Deploy the front end

The Static Web App is created empty; the React build is pushed separately.

```powershell
cd frontend
npm ci
$env:VITE_API_BASE_URL = (terraform -chdir=../infra/env output -raw core_service_url)
npm run build
npx --yes @azure/static-web-apps-cli deploy ./dist `
  --deployment-token (terraform -chdir=../infra/env output -raw frontend_deploy_token) `
  --env production
```

Open the frontend URL (`terraform -chdir=infra/env output -raw frontend_url`
from the repo root, or `terraform output -raw frontend_url` from `infra/env/`),
register, add holdings, run an investigation.

### Redeploying after a code change

- **A service** — rebuild + push its image (step 3), then roll the revision:
  ```powershell
  az containerapp update -g rg-risklens -n core-service  --image $acr/risklens-core-service:latest
  az containerapp update -g rg-risklens -n agent-service --image $acr/risklens-agent-service:latest
  ```
  (`terraform apply` won't roll a revision — the `:latest` tag doesn't change.)
- **The front end** — rerun step 5.
- **Infra** — `terraform apply` from `infra/env/`.

### Pausing to save cost

```powershell
./infra/manage.ps1 stop      # stops Postgres, scales the two containers to 0
./infra/manage.ps1 start     # reverses it, restores a warm agent replica
./infra/manage.ps1 status    # Postgres state, replica counts, URLs
```

The Static Web App, Foundry (pay-per-token), ACR, and Key Vault have no idle
cost worth managing and are left running. **Start Postgres (`manage.ps1 start`)
before running `terraform apply` from `infra/env/`** — Terraform can't refresh a
stopped server.

### Observability

The agent container runs with `LANGSMITH_TRACING=true`; every investigation is
traced to [smith.langchain.com](https://smith.langchain.com) under project
`risklens-agent`, and each investigation row's `observability_trace_id` is the
run id.
