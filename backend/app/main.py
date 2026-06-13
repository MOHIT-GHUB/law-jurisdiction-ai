"""
main.py — FastAPI application entry point.

═══════════════════════════════════════════════════════════════
  FULL SYSTEM FLOW (matches architecture diagram exactly)
═══════════════════════════════════════════════════════════════

  ┌──────────────────────────────────────────────────────────┐
  │  CLIENT  (React frontend — frontend/src/)                │
  │  Chat UI, sidebar, score card                            │
  └───────────────────┬──────────────────────────────────────┘
                      │  HTTP REST  +  WebSocket
  ┌───────────────────▼──────────────────────────────────────┐
  │  SERVER  (this file — main.py)                           │
  │  FastAPI app. Registers all routes. Starts DB on boot.   │
  │                                                          │
  │  REST routes:                                            │
  │    POST /auth/signup      → routers/auth.py              │
  │    POST /auth/login       → routers/auth.py              │
  │    GET  /conversations/   → routers/conversations.py     │
  │    GET  /conversations/{id}                              │
  │    GET  /conversations/{id}/export-pdf                   │
  │    DELETE /conversations/{id}                            │
  │                                                          │
  │  WebSocket:                                              │
  │    WS /ws/{conversation_id}?token=JWT                    │
  │                       → routers/chat.py  ◄── MAIN FLOW  │
  │                                                          │
  │  Infrastructure (started here):                          │
  │    PostgreSQL  → database.py   (user auth + history)     │
  │    Redis       → redis_client.py (API response cache)    │
  └──────────────────────────────────────────────────────────┘

DIAGRAM NOTE — "Server" box in the image maps to:
  - This file (app setup, lifespan, CORS)
  - routers/auth.py (HTTP endpoints)
  - routers/conversations.py (HTTP endpoints)
  - routers/chat.py (WebSocket — the main user interaction path)

DIAGRAM NOTE — "PostgreSQL" box in the image:
  - Configured in: config.py (DATABASE_URL)
  - Engine/session: database.py
  - Table definitions: models/models.py
  - init_db() called in lifespan() below

TEAM — WHAT TO IMPLEMENT HERE:
  1. Create the FastAPI app instance
  2. Add CORS middleware (allow frontend on localhost:3000)
  3. Write a lifespan() async context manager:
       - on startup: call await init_db()
       - on shutdown: close DB engine if needed
  4. Register all routers:
       app.include_router(auth_router)          # from routers/auth.py
       app.include_router(conversations_router) # from routers/conversations.py
       app.include_router(chat_router)          # from routers/chat.py
  5. Add a GET /health endpoint (judges like seeing this — shows professionalism)

IMPORTS YOU WILL NEED:
  from fastapi import FastAPI
  from fastapi.middleware.cors import CORSMiddleware
  from contextlib import asynccontextmanager
  from app.database import init_db
  from app.routers.auth import router as auth_router
  from app.routers.conversations import router as conversations_router
  from app.routers.chat import router as chat_router

HOW TO RUN (after implementing):
  uvicorn app.main:app --reload --port 8000
  Then open: http://localhost:8000/docs  (auto-generated API explorer)
"""

# ── TODO: implement this file ─────────────────────────────────────────────────
# Effort: ~30 minutes. Ask ChatGPT: "Write a FastAPI main.py that:
#   - Has a lifespan context that calls init_db() on startup
#   - Registers 3 routers: auth, conversations, chat
#   - Adds CORS for http://localhost:3000
#   - Has a /health endpoint returning {status: ok}
# Then show it this file's docstring for context."
raise NotImplementedError("main.py not yet implemented — see docstring above")
