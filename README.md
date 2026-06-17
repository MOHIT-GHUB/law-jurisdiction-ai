# LexAI — US Jurisdiction Assistant

LexAI is a multi-agent legal assistant that helps a user describe a legal situation in plain language and get back a structured, jurisdiction-aware analysis: which **federal** and **state** laws apply, relevant **case law**, a **case-strength score**, recommended next steps, and nearby **attorney referrals**.

The user chats with the system; behind the scenes a [LangGraph](https://langchain-ai.github.io/langgraph/) pipeline of specialized agents gathers and synthesizes the answer, streaming tokens back over a WebSocket.

> ⚠️ **Status: work in progress.** The backend boots and serves today, but several pieces are still being built (see [Project status](#project-status)). This README covers the current, uv-based local setup.

---

## How it works

```
        user message
             │
             ▼
      ┌─────────────┐   not enough info yet
      │   intake    │───────────────► (wait for next message)
      │   agent     │
      └──────┬──────┘  intake complete
             ▼
   ┌───────────────────┐   runs the 3 research agents in parallel
   │  fan_out_research │
   └───┬─────┬─────┬───┘
       ▼     ▼     ▼
   federal  state  case-law      (Congress.gov · Cornell LII · CourtListener)
       └─────┼─────┘
             ▼
       ┌──────────┐   writes opinion + case_strength_score + recommended_actions
       │ opinion  │
       └────┬─────┘
            ▼
      ┌───────────┐   finds nearby attorneys (Google Maps)
      │ referral  │
      └────┬──────┘
           ▼
          done
```

**The agents** (in `backend/app/agents/`):

| Agent | Role | Data source |
|-------|------|-------------|
| `intake_agent` | Asks clarifying questions until it has enough facts (incident, location, state, etc.) | LLM |
| `federal_law_agent` | Finds applicable federal statutes | Congress.gov |
| `state_law_agent` | Finds applicable state statutes | Cornell LII |
| `case_law_agent` | Finds relevant precedent | CourtListener |
| `opinion_agent` | Synthesizes a legal opinion + a 0–100 case-strength score | LLM |
| `referral_agent` | Recommends nearby attorneys | Google Maps |

All agents share a single `AgentState` (the "whiteboard") defined in `backend/app/agents/state.py`.

---

## Tech stack

- **API:** FastAPI (async) + Uvicorn, with a WebSocket chat endpoint
- **Agents:** LangGraph + LangChain (OpenAI models)
- **Database:** PostgreSQL via async SQLAlchemy (users, conversations, messages)
- **Cache:** Redis (caches external legal-API responses to stay fast and within rate limits)
- **Auth:** JWT (python-jose) + bcrypt password hashing (passlib)
- **PDF export:** ReportLab (generates a downloadable case report)
- **Packaging:** [uv](https://docs.astral.sh/uv/) (`pyproject.toml` + `uv.lock`)
- **Frontend:** React (planned — not built yet)

---

## Prerequisites

- [**Docker**](https://docs.docker.com/get-docker/) + Docker Compose (for Postgres, Redis, and optionally the server)
- [**uv**](https://docs.astral.sh/uv/getting-started/installation/) (only needed if you run the server on your host instead of in Docker)
  - uv manages the Python version automatically — you do **not** need Python 3.12 pre-installed.
- An **OpenAI API key** (the agents call OpenAI). Other API keys are optional in demo mode.

---

## Setup

### 1. Configure environment

```bash
cp backend/.env.example backend/.env
```

Then edit `backend/.env` and set at minimum:

- `OPENAI_API_KEY` — required for the agents to run
- `SECRET_KEY` — generate one with:
  ```bash
  python3 -c "import secrets; print(secrets.token_hex(32))"
  ```

Leave `DEMO_MODE=True` to bypass the external legal APIs and return realistic mock data — handy when you don't have the other API keys or want a reliable demo.

> The `DATABASE_URL` / `REDIS_URL` in `.env` use `localhost` (correct for running the server on your host). When the server runs **inside** Docker Compose, those hosts are automatically overridden to the `postgres` / `redis` service names — no edit needed.

### 2. Run

You have two options.

#### Option A — everything in Docker (simplest)

Starts Postgres, Redis, **and** the backend server. Source is bind-mounted, so code edits hot-reload.

```bash
docker compose up -d --build
```

- API: http://localhost:8000
- Interactive docs (Swagger): http://localhost:8000/docs

Stop with `docker compose down` (add `-v` to also wipe the database/cache volumes).

#### Option B — infra in Docker, server on your host (best for active dev)

```bash
# 1. Start just Postgres + Redis
docker compose up -d postgres redis

# 2. Install deps + run the server (uv creates the venv and fetches Python 3.12)
cd backend
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

Either way, open http://localhost:8000/docs to explore the API.

---

## IDE setup (VSCode)

After `uv sync`, point VSCode at the project interpreter so imports resolve:

1. `Cmd+Shift+P` → **Python: Select Interpreter**
2. **Enter interpreter path…** → `./backend/.venv/bin/python`

(The auto-discovery list may not show it since the venv lives in the `backend/` subfolder.)

---

## Project structure

```
.
├── Makefile                  # dev command shortcuts (make help)
├── docker-compose.yml        # postgres + redis + server
├── .pre-commit-config.yaml   # ruff lint/format + hygiene hooks
├── backend/
│   ├── Dockerfile            # uv-based image for the server
│   ├── pyproject.toml        # dependencies + ruff config (managed by uv)
│   ├── uv.lock               # pinned, reproducible versions — commit this
│   ├── .env.example          # copy to .env
│   └── app/
│       ├── main.py           # FastAPI entry point (app + lifespan)
│       ├── config.py         # settings loaded from .env
│       ├── database.py       # async SQLAlchemy engine/session + init_db()
│       ├── redis_client.py   # Redis connection + cache helpers
│       ├── agents/           # LangGraph agents + graph wiring
│       ├── routers/          # auth, conversations, chat (WebSocket)
│       ├── tools/            # external legal-API clients
│       ├── models/           # SQLAlchemy ORM models
│       ├── schemas/          # Pydantic request/response schemas
│       ├── middleware/       # prompt-injection guard
│       └── utils/            # auth helpers, PDF export
└── frontend/                 # React app (planned)
```


## Developer commands

Common tasks are wrapped in the `Makefile` — run `make help` to see them all:

```bash
make install     # install deps (incl. dev tools) + git pre-commit hook
make env         # create backend/.env from the example
make up          # full stack in Docker (postgres + redis + server)
make up-infra    # just Postgres + Redis
make run         # run the server on the host with auto-reload
make logs        # tail the server container logs
make reset       # wipe DB/cache volumes and rebuild
make lint        # ruff lint
make fix         # ruff autofix + format
make pre-commit  # run all hooks against every file
```

The equivalent raw commands still work (`cd backend && uv lock && uv sync`, `docker compose ...`, etc.) if you prefer.

## Code quality (ruff + pre-commit)

Linting and formatting use [ruff](https://docs.astral.sh/ruff/), configured in `backend/pyproject.toml`. A [pre-commit](https://pre-commit.com/) hook runs ruff (with autofix) and a few hygiene checks on every commit, scoped to `backend/`.

```bash
make install     # one-time: installs the git hook (or: make hooks)
```

After that, `git commit` automatically lints/formats staged files. To run everything on demand: `make pre-commit`.
