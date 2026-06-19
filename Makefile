# LexAI — developer command shortcuts.
# Run `make` or `make help` to see all targets.

BACKEND := backend
COMPOSE := docker compose
UV      := uv --project $(BACKEND)
PORT    ?= 8000
SCENARIO ?= complete

.DEFAULT_GOAL := help

##@ Setup

.PHONY: install
install: ## Install backend deps (incl. dev tools) and the git pre-commit hook
	cd $(BACKEND) && uv sync
	$(UV) run pre-commit install

.PHONY: env
env: ## Create backend/.env from the example if it doesn't exist
	@test -f $(BACKEND)/.env && echo "$(BACKEND)/.env already exists" || (cp $(BACKEND)/.env.example $(BACKEND)/.env && echo "Created $(BACKEND)/.env — fill in OPENAI_API_KEY and SECRET_KEY")

.PHONY: lock
lock: ## Re-resolve and update uv.lock after editing pyproject.toml
	cd $(BACKEND) && uv lock

.PHONY: sync
sync: ## Install exactly what's in uv.lock
	cd $(BACKEND) && uv sync

##@ Run

.PHONY: run
run: ## Run the server on the host with auto-reload (needs infra: make up-infra)
	cd $(BACKEND) && uv run uvicorn app.main:app --reload --port $(PORT)

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

##@ Housekeeping

.PHONY: clean
clean: ## Remove Python caches and ruff cache
	find $(BACKEND) -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
	rm -rf $(BACKEND)/.ruff_cache

.PHONY: help
help: ## Show this help
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage: make \033[36m<target>\033[0m\n"} \
		/^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2 } \
		/^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) }' $(MAKEFILE_LIST)
	@echo ""
