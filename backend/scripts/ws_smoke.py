#!/usr/bin/env python
"""
scripts/ws_smoke.py — End-to-end smoke test over the real HTTP + WebSocket API.

Exercises the actual path the frontend will use: signup/login for a JWT, then a
WebSocket chat turn. Unlike run_workflow.py this needs the full stack running and
a real OPENAI_API_KEY configured ON THE SERVER (the graph calls OpenAI).

Runbook:
  cp backend/.env.example backend/.env       # set OPENAI_API_KEY, SECRET_KEY, DEMO_MODE=True
  docker compose up -d --build               # postgres + redis + server
  uv run python scripts/ws_smoke.py          # from backend/

Config via env:
  LEXAI_BASE_URL   default http://localhost:8000
  LEXAI_MESSAGE    the chat message to send (defaults to a full intake)
"""

import asyncio
import json
import os
import uuid

import httpx
import websockets

BASE_URL = os.environ.get("LEXAI_BASE_URL", "http://localhost:8000").rstrip("/")
WS_URL = "ws" + BASE_URL[len("http") :]  # http->ws, https->wss

DEFAULT_MESSAGE = (
    "I was fired from my job at Acme Corp in Austin, Texas on 2024-03-15 by my manager "
    "Jane Doe right after I reported safety violations. I have the termination email and "
    "my complaint emails saved."
)


async def _get_token() -> str:
    """Sign up a throwaway user (or log in if it already exists) and return a JWT."""
    creds = {"username": f"smoke_{uuid.uuid4().hex[:8]}", "password": "smoketest123"}
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=15) as client:
        resp = await client.post("/auth/signup", json=creds)
        if resp.status_code == 409:
            resp = await client.post("/auth/login", json=creds)
        resp.raise_for_status()
        return resp.json()["access_token"]


async def _run() -> None:
    token = await _get_token()
    conversation_id = str(uuid.uuid4())
    url = f"{WS_URL}/ws/{conversation_id}?token={token}"
    message = os.environ.get("LEXAI_MESSAGE", DEFAULT_MESSAGE)

    print(f">>> connecting {url}\n>>> sending: {message}\n")
    async with websockets.connect(url) as ws:
        await ws.send(json.dumps({"content": message}))

        final: dict = {}
        while True:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=120)
            except TimeoutError:
                print("\n!!! timed out waiting for a frame")
                break

            frame = json.loads(raw)
            ftype = frame.get("type")
            if ftype == "token":
                print(frame.get("content", ""), end="", flush=True)
            elif ftype == "status":
                print(f"\n[status] {frame.get('message')}")
            elif ftype == "error":
                print(f"\n[error] {frame.get('message')}")
                break
            elif ftype in ("score", "lawyers", "actions"):
                final[ftype] = frame.get("value", frame.get("data"))
            elif ftype == "done":
                break
            else:
                print(f"\n[{ftype}]")

    print("\n\n" + "=" * 60)
    print("DONE")
    print("=" * 60)
    print(f"  score   : {final.get('score')}")
    print(f"  lawyers : {len(final.get('lawyers') or [])}")
    print(f"  actions : {len(final.get('actions') or [])}")


if __name__ == "__main__":
    asyncio.run(_run())
