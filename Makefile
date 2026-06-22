# LexAI — developer command shortcuts.
# Run `make` or `make help` to see all targets.

BACKEND := backend
FRONTEND := frontend
COMPOSE := docker compose
UV      := uv --project $(BACKEND)
PORT    ?= 8000
SCENARIO ?= complete

.DEFAULT_GOAL := help

##@ Setup

.PHONY: install
install: ## Install everything: backend deps + git hook + frontend deps
	cd $(BACKEND) && uv sync
	$(UV) run pre-commit install
	cd $(FRONTEND) && npm install

.PHONY: env
env: ## Create backend/.env and frontend/.env from examples if missing
	@test -f $(BACKEND)/.env && echo "$(BACKEND)/.env already exists" || (cp $(BACKEND)/.env.example $(BACKEND)/.env && echo "Created $(BACKEND)/.env — fill in OPENAI_API_KEY and SECRET_KEY")
	@test -f $(FRONTEND)/.env && echo "$(FRONTEND)/.env already exists" || (cp $(FRONTEND)/.env.example $(FRONTEND)/.env && echo "Created $(FRONTEND)/.env")

.PHONY: lock
lock: ## Re-resolve and update uv.lock after editing pyproject.toml
	cd $(BACKEND) && uv lock

.PHONY: sync
sync: ## Install exactly what's in uv.lock
	cd $(BACKEND) && uv sync

##@ Run

.PHONY: run
run: ## Run the server on the host with auto-reload (needs infra: make up-infra)
	cd $(BACKEND) && DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib:/usr/local/lib \
		uv run uvicorn app.main:app --reload --port $(PORT)

.PHONY: dev
dev: ## Run EVERYTHING: full stack in Docker (db+redis+server) + frontend dev server
	$(COMPOSE) up -d --build
	@echo ""
	@echo "  Backend  → http://localhost:8000/docs   (Docker, detached)"
	@echo "  Frontend → Vite dev server starting below (Ctrl-C stops it)"
	@echo "  Stop the backend stack afterwards with:  make down"
	@echo ""
	cd $(FRONTEND) && npm run dev

.PHONY: up
up: ## Start the full stack in Docker (postgres + redis + server)
	$(COMPOSE) up -d --build

.PHONY: up-infra
up-infra: ## Start only Postgres + Redis (run the server yourself with `make run`)
	$(COMPOSE) up -d postgres redis

.PHONY: down
down: ## Stop all containers
	$(COMPOSE) down

.PHONY: reset
reset: ## Wipe DB/cache volumes and rebuild the full stack
	$(COMPOSE) down -v && $(COMPOSE) up -d --build

.PHONY: logs
logs: ## Tail the server container logs
	$(COMPOSE) logs -f server

##@ Quality

.PHONY: lint
lint: ## Lint the backend with ruff (no changes)
	cd $(BACKEND) && uv run ruff check .

.PHONY: format
format: ## Format the backend with ruff
	cd $(BACKEND) && uv run ruff format .

.PHONY: fix
fix: ## Autofix lint issues + format the backend
	cd $(BACKEND) && uv run ruff check --fix . && uv run ruff format .

.PHONY: hooks
hooks: ## Install the git pre-commit hook
	$(UV) run pre-commit install

.PHONY: pre-commit
pre-commit: ## Run all pre-commit hooks against every file
	$(UV) run pre-commit run --all-files

##@ Smoke tests

.PHONY: smoke-mock
smoke-mock: ## Drive the agent graph offline with a stubbed LLM (all scenarios)
	cd $(BACKEND) && for s in complete partial no-perp outside-us criminal; do \
		echo "=== $$s ==="; uv run python scripts/run_workflow.py $$s --mock; echo; done

.PHONY: smoke
smoke: ## Drive the agent graph with the REAL LLM (needs OPENAI_API_KEY); SCENARIO?=complete
	cd $(BACKEND) && uv run python scripts/run_workflow.py $(SCENARIO)

.PHONY: smoke-ws
smoke-ws: ## End-to-end smoke over the running HTTP+WS API (needs the stack up)
	cd $(BACKEND) && uv run python scripts/ws_smoke.py

##@ Frontend

.PHONY: fe-install
fe-install: ## Install frontend npm dependencies
	cd $(FRONTEND) && npm install

.PHONY: fe-dev
fe-dev: ## Run the Vite dev server (hot reload)
	cd $(FRONTEND) && npm run dev

.PHONY: fe-build
fe-build: ## Production build of the frontend (tsc + vite build)
	cd $(FRONTEND) && npm run build

.PHONY: fe-lint
fe-lint: ## Lint the frontend with ESLint
	cd $(FRONTEND) && npm run lint

.PHONY: fe-preview
fe-preview: ## Serve the production build locally
	cd $(FRONTEND) && npm run preview

##@ Housekeeping

.PHONY: clean
clean: ## Remove Python caches, ruff cache, and frontend build output
	find $(BACKEND) -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
	rm -rf $(BACKEND)/.ruff_cache $(FRONTEND)/dist

.PHONY: help
help: ## Show this help
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage: make \033[36m<target>\033[0m\n"} \
		/^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2 } \
		/^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) }' $(MAKEFILE_LIST)
	@echo ""
