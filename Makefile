.PHONY: help setup-backend setup-frontend run-backend run-frontend clean

PY=python3

help:
	@echo "Quantpulse — common commands"
	@echo "  make setup-backend    install Python deps into backend/.venv"
	@echo "  make setup-frontend   install Node deps into frontend/node_modules"
	@echo "  make run-backend      run FastAPI on :8000"
	@echo "  make run-frontend     run Vite on :5173"
	@echo "  make clean            remove venv, node_modules, caches"

setup-backend:
	cd backend && $(PY) -m venv .venv && . .venv/bin/activate && \
		pip install --upgrade pip && pip install -r requirements.txt

setup-frontend:
	cd frontend && npm install

run-backend:
	cd backend && . .venv/bin/activate && \
		uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

run-frontend:
	cd frontend && npm run dev

clean:
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf backend/.venv frontend/node_modules frontend/dist
