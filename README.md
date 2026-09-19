# Quantpulse

Post-Market Intelligence & Forecasting Platform.

Quantpulse ingests Indian equities data after each market session, computes
features, analyzes news, and produces probabilistic 7/15/30-day forecasts,
risk assessments, and plain-English explanations — one analysis per ticker,
served to many users.

**Status:** Stage 0 — foundation only. No data, no ML, no real UI yet.

## Layout

    quantpulse/
    ├── backend/         FastAPI service + pipeline + ML + NLP
    ├── frontend/        React (Vite + Tailwind)
    ├── data/            SQLite DB + raw cache (gitignored)
    └── docs/            Stage handoff docs

## First run

    cp .env.example .env
    make setup-backend
    make setup-frontend

    # terminal 1
    make run-backend

    # terminal 2
    make run-frontend

Open http://localhost:5173 — you should see "Quantpulse" and
"backend: ok".

## Stages

See `docs/` for per-stage handoff documents.
