# Quantpulse — developer commands
# Requires: uv (https://docs.astral.sh/uv/), node 20+
#
# Python deps live in the repo-root .venv (Python 3.12, managed by uv).
# Activate manually:   source .venv/bin/activate
# Run a script:        .venv/bin/python backend/scripts/foo.py

.PHONY: help setup setup-backend setup-frontend run-backend run-frontend clean

help:
	@echo "Quantpulse — common commands"
	@echo "  make setup            install backend + frontend deps"
	@echo "  make setup-backend    install Python deps into .venv"
	@echo "  make setup-frontend   install Node deps into frontend/node_modules"
	@echo "  make run-backend      run FastAPI on 127.0.0.1:8000"
	@echo "  make run-frontend     run Vite on localhost:5173"
	@echo "  make clean            remove .venv, node_modules, __pycache__"

setup: setup-backend setup-frontend

setup-backend:
	uv pip install -r backend/requirements.txt

setup-frontend:
	cd frontend && npm install

run-backend:
	cd backend && ../.venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

run-frontend:
	cd frontend && npm run dev

clean:
	find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
	rm -rf .venv frontend/node_modules frontend/dist