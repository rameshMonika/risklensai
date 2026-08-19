-- Portfolio Risk Investigator: Core service schema
-- Owns all persistence for the app (see CLAUDE.md "Backend architecture (V1)").
-- The Agent service has no database access at all.

CREATE DATABASE risklens;

\connect risklens

CREATE TABLE "user" (
    id            BIGSERIAL PRIMARY KEY,
    name          TEXT NOT NULL,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE portfolio (
    id         BIGSERIAL PRIMARY KEY,
    user_id    BIGINT NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
    name       TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE holding (
    id           BIGSERIAL PRIMARY KEY,
    portfolio_id BIGINT NOT NULL REFERENCES portfolio(id) ON DELETE CASCADE,
    symbol       TEXT NOT NULL,
    quantity     NUMERIC NOT NULL,
    avg_cost     NUMERIC NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE investigation (
    id                      BIGSERIAL PRIMARY KEY,
    portfolio_id            BIGINT NOT NULL REFERENCES portfolio(id) ON DELETE CASCADE,
    query                   TEXT NOT NULL,
    intent                  TEXT,
    status                  TEXT NOT NULL,
    start_date              DATE,
    end_date                DATE,
    risk_results            JSONB,
    observability_trace_id  TEXT,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE evidence (
    id                BIGSERIAL PRIMARY KEY,
    investigation_id  BIGINT NOT NULL REFERENCES investigation(id) ON DELETE CASCADE,
    symbol            TEXT NOT NULL,
    title             TEXT,
    source_url        TEXT,
    published_at      TIMESTAMPTZ,
    evidence_text     TEXT,
    retrieved_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One report per investigation.
CREATE TABLE investigation_report (
    id               BIGSERIAL PRIMARY KEY,
    investigation_id BIGINT NOT NULL UNIQUE REFERENCES investigation(id) ON DELETE CASCADE,
    summary          TEXT NOT NULL,
    report_json      JSONB NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_portfolio_user_id ON portfolio(user_id);
CREATE INDEX idx_holding_portfolio_id ON holding(portfolio_id);
CREATE INDEX idx_investigation_portfolio_id ON investigation(portfolio_id);
CREATE INDEX idx_evidence_investigation_id ON evidence(investigation_id);
