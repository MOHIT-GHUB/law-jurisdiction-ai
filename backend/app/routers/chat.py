"""
routers/chat.py — WebSocket endpoint. The CORE of the user interaction.

═══════════════════════════════════════════════════════════════
  WHERE THIS FILE SITS IN THE ARCHITECTURE DIAGRAM
═══════════════════════════════════════════════════════════════

  CLIENT → SERVER → [THIS FILE] → PROMPT GUARD → INTAKE AGENT
                                                       ↓
                                   (LangGraph takes over after this)

  Specifically, this file is responsible for:
    1. Accepting the WebSocket connection from the client
    2. Authenticating the user via JWT token
    3. Loading or creating the Conversation from PostgreSQL
    4. For each incoming message:
         a. Passing it through Prompt Guard (middleware/prompt_guard.py)
         b. Saving the user message to PostgreSQL (models/models.py → Message)
         c. Injecting the message into LangGraph state
         d. Streaming the agent response back token-by-token to the client
         e. Saving the assistant response to PostgreSQL
    5. Updating Conversation.state in DB as pipeline progresses

═══════════════════════════════════════════════════════════════
  WEBSOCKET MESSAGE PROTOCOL (agree with frontend team)
═══════════════════════════════════════════════════════════════

  CLIENT → SERVER (JSON):
    { "type": "message", "content": "I was fired without cause yesterday" }

  SERVER → CLIENT (JSON, streamed token by token):
    { "type": "token",          "content": "I understand..." }
    { "type": "status",         "message": "Searching federal law..." }
    { "type": "intake_complete" }             ← triggers frontend loading state
    { "type": "score",          "value": 74 } ← triggers score card animation
    { "type": "lawyers",        "data": [...] }
    { "type": "done" }                        ← conversation complete
    { "type": "error",          "message": "..." } ← guard blocked / exception

═══════════════════════════════════════════════════════════════
  HOW TO WIRE LANGGRAPH (critical — read carefully)
═══════════════════════════════════════════════════════════════

  Import the compiled graph singleton:
    from app.agents.graph import graph          # agents/graph.py

  Import the state type:
    from app.agents.state import AgentState     # agents/state.py

  Build the initial state dict (first message in a conversation):
    state: AgentState = {
        "conversation_id": conversation_id,
        "user_id": str(current_user.id),
        "messages": [{"role": "user", "content": user_message}],
        "intake_complete": False,
        "intake_summary": {},
        "federal_law_results": [],
        "state_law_results": [],
        "case_law_results": [],
        "opinion": "",
        "case_strength_score": 0,
        "recommended_actions": [],
        "referred_lawyers": [],
    }

  Build LangGraph config (stream_callback goes HERE, not in state):
    async def stream_to_client(token: str):
        await websocket.send_json({"type": "token", "content": token})

    config = {
        "configurable": {
            "thread_id": conversation_id,      # isolates state per conversation
            "stream_callback": stream_to_client,
        }
    }

  Invoke the graph:
    result = await graph.ainvoke(state, config=config)

  After completion, send final data:
    await websocket.send_json({"type": "score", "value": result["case_strength_score"]})
    await websocket.send_json({"type": "lawyers", "data": result["referred_lawyers"]})
    await websocket.send_json({"type": "done"})

═══════════════════════════════════════════════════════════════
  HOW TO AUTHENTICATE THE WEBSOCKET CONNECTION
═══════════════════════════════════════════════════════════════

  WebSockets don't support Authorization headers.
  Pass the JWT token as a query param:
    ws://localhost:8000/ws/CONV_ID?token=eyJhbGci...

  In the endpoint, read and validate it manually:
    from jose import jwt, JWTError
    from app.config import get_settings
    settings = get_settings()

    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4001)
        return
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id = payload.get("sub")
    except JWTError:
        await websocket.close(code=4001)
        return

═══════════════════════════════════════════════════════════════
  HOW TO SAVE MESSAGES TO POSTGRESQL
═══════════════════════════════════════════════════════════════

  Use AsyncSessionLocal directly (not Depends — WebSockets can't use it):
    from app.database import AsyncSessionLocal
    from app.models.models import Message, Conversation, ConversationState

  Save user message:
    async with AsyncSessionLocal() as db:
        msg = Message(
            conversation_id=conversation_id,
            role="user",
            content=user_message,
        )
        db.add(msg)
        await db.commit()

  Save assistant response + update conversation state:
    async with AsyncSessionLocal() as db:
        msg = Message(conversation_id=conversation_id, role="assistant", content=full_response)
        db.add(msg)
        # Update conversation state to "active" or "completed"
        conv = await db.get(Conversation, conversation_id)
        if result.get("intake_complete") and conv.state == ConversationState.INTAKE:
            conv.state = ConversationState.ACTIVE
        if result.get("referred_lawyers"):
            conv.state = ConversationState.COMPLETED
            conv.research_result = {
                "opinion": result["opinion"],
                "case_strength_score": result["case_strength_score"],
                "recommended_actions": result["recommended_actions"],
                "referred_lawyers": result["referred_lawyers"],
            }
            # Auto-generate a short title from intake_summary
            loc = result["intake_summary"].get("location", "")
            inc = result["intake_summary"].get("incident", "")[:30]
            conv.title = f"{inc}... — {loc}"
        await db.commit()

═══════════════════════════════════════════════════════════════
  HOW TO CALL PROMPT GUARD
═══════════════════════════════════════════════════════════════

  from app.middleware.prompt_guard import check_prompt

  guard = check_prompt(user_message)
  if not guard.allowed:
      await websocket.send_json({"type": "error", "message": guard.reason})
      continue  # don't process this message, wait for next one

═══════════════════════════════════════════════════════════════
  FULL ENDPOINT SKELETON (implement this)
═══════════════════════════════════════════════════════════════

  @router.websocket("/ws/{conversation_id}")
  async def chat_websocket(websocket: WebSocket, conversation_id: str):
      # 1. Authenticate
      # 2. Accept WebSocket
      # 3. Load or create Conversation from DB
      # 4. Loop:
      #      data = await websocket.receive_json()
      #      user_message = data["content"]
      #      guard = check_prompt(user_message)
      #      if not guard.allowed: send error, continue
      #      save user message to DB
      #      build state + config
      #      result = await graph.ainvoke(state, config)
      #      save assistant message + update conversation in DB
      #      send score/lawyers/done to client
      # 5. Handle WebSocketDisconnect gracefully

"""

import logging

from app.agents.graph import graph
from app.agents.state import AgentState
from app.config import get_settings
from app.database import AsyncSessionLocal
from app.middleware.prompt_guard import check_prompt
from app.models.models import Conversation, ConversationState, Message
from app.utils.pii import redact_pii
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from jose import JWTError, jwt
from langchain_core.runnables import RunnableConfig
from sqlalchemy import select

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(tags=["chat"])


def _make_stream_callback(websocket: WebSocket, parts: list[str]):
    """Build the per-message token stream callback.

    Defined as a factory (rather than a closure inside the receive loop) so the
    accumulator list and socket are bound as arguments — avoids the late-binding
    loop-variable trap (ruff B023).
    """

    async def stream_to_client(token: str) -> None:
        parts.append(token)
        await websocket.send_json({"type": "token", "content": token})

    return stream_to_client


# ── Helper: authenticate WebSocket via JWT query param ───────────────────────


async def _authenticate(websocket: WebSocket) -> str | None:
    """
    WebSockets cannot carry Authorization headers, so the JWT is passed
    as a query param: ws://host/ws/CONV_ID?token=eyJ...

    Returns the user_id (UUID string) from the token payload,
    or None if the token is missing / invalid / expired.
    Closes the socket with code 4001 on failure.
    """
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4001, reason="Missing token")
        return None
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: str | None = payload.get("sub")
        if not user_id:
            raise JWTError("No sub claim")
        return user_id
    except JWTError:
        await websocket.close(code=4001, reason="Invalid or expired token")
        return None


# ── Helper: load or create a Conversation row ─────────────────────────────────


async def _get_or_create_conversation(conversation_id: str, user_id: str) -> Conversation:
    """
    Load the conversation from Postgres by ID.
    If it doesn't exist yet (new conversation), create it now.

    The conversation_id comes from the WebSocket URL path — the frontend
    generates a fresh UUID for every new chat session before connecting.
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Conversation).where(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id,
            )
        )
        conv = result.scalar_one_or_none()
        if conv is None:
            conv = Conversation(
                id=conversation_id,
                user_id=user_id,
                state=ConversationState.INTAKE,
            )
            db.add(conv)
            await db.commit()
    return conv


# ── Helper: load full message history for a conversation ─────────────────────


async def _load_messages(conversation_id: str) -> list[dict]:
    """
    Fetch all messages for this conversation from Postgres, ordered oldest-first.
    Returned as a list of {"role": ..., "content": ...} dicts for LangGraph state.
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at)
        )
        rows = result.scalars().all()
    return [{"role": m.role, "content": m.content} for m in rows]


# ── Helper: persist a message to Postgres ────────────────────────────────────


async def _save_message(conversation_id: str, role: str, content: str) -> None:
    """Save a single user or assistant message to the messages table."""
    async with AsyncSessionLocal() as db:
        db.add(Message(conversation_id=conversation_id, role=role, content=content))
        await db.commit()


# ── Helper: update Conversation state + research_result after research done ───


async def _finalize_conversation(conversation_id: str, result: dict) -> None:
    """
    Called after LangGraph completes the full pipeline (referral agent done).
    - Saves the full research output to conversation.research_result (JSONB)
    - Marks state as COMPLETED
    - Auto-generates a short title shown in the sidebar
    """
    async with AsyncSessionLocal() as db:
        conv = await db.get(Conversation, conversation_id)
        if conv is None:
            return

        intake = result.get("intake_summary", {})

        # Transition state
        if result.get("referred_lawyers"):
            conv.state = ConversationState.COMPLETED
            conv.research_result = {
                "opinion": result.get("opinion", ""),
                "case_strength_score": result.get("case_strength_score", 0),
                "recommended_actions": result.get("recommended_actions", []),
                "referred_lawyers": result.get("referred_lawyers", []),
                "legal_classification": result.get("legal_classification", {}),
                "federal_law_results": result.get("federal_law_results", []),
                "state_law_results": result.get("state_law_results", []),
                "case_law_results": result.get("case_law_results", []),
            }
            # Build a short sidebar title: first 30 chars of incident + location
            incident = intake.get("incident", "New case")[:30]
            location = intake.get("location", "")
            conv.title = f"{incident}{'...' if len(intake.get('incident', '')) > 30 else ''} — {location}".strip(
                " —"
            )
        elif result.get("intake_complete") and conv.state == ConversationState.INTAKE:
            # Intake just completed, research starting
            conv.state = ConversationState.ACTIVE
            conv.intake_summary = intake

        await db.commit()


# ── Main WebSocket endpoint ────────────────────────────────────────────────────


@router.websocket("/ws/{conversation_id}")
async def chat_websocket(websocket: WebSocket, conversation_id: str):
    """
    The primary entry point for all user interaction.

    FLOW PER MESSAGE:
      receive JSON → prompt guard → save to DB → build LangGraph state
      → ainvoke graph (streams tokens back) → save result → send done

    URL format: ws://localhost:8000/ws/{uuid}?token=JWT
    The frontend generates a new UUID per session for new conversations,
    or passes an existing conversation_id to resume a past one.

    COORDINATION WITH AI TEAM:
      This calls app.agents.graph.graph — that must be implemented for
      full functionality. Until then, DEMO_MODE in config returns mock
      data so the WebSocket still works end-to-end.
    """
    # ── Step 1: Accept first — can't close/send before accepting ─────────
    await websocket.accept()

    # ── Step 2: Authenticate (closes with code 4001 if invalid) ──────────
    user_id = await _authenticate(websocket)
    if user_id is None:
        return  # socket already closed by _authenticate

    # ── Step 3: Load or create the Conversation from DB ───────────────────
    try:
        await _get_or_create_conversation(conversation_id, user_id)
    except Exception as exc:
        logger.error("Failed to load/create conversation %s: %s", conversation_id, exc)
        await websocket.send_json({"type": "error", "message": "Failed to load conversation"})
        await websocket.close()
        return

    # ── Step 4: Main message loop ─────────────────────────────────────────
    try:
        while True:
            # Receive message from frontend
            try:
                data = await websocket.receive_json()
            except Exception:
                # Client sent non-JSON — skip silently
                continue

            user_message: str = (data.get("content") or "").strip()
            if not user_message:
                continue

            # ── Redact PII before it touches storage, the LLM, or moderation ─
            user_message = redact_pii(user_message)

            # ── Prompt Guard: rate limit + injection + moderation ─────────
            guard = await check_prompt(user_message, user_id)
            if not guard.allowed:
                await websocket.send_json({"type": "error", "message": guard.reason})
                continue  # wait for a valid message, don't disconnect

            # ── Persist user message to Postgres ──────────────────────────
            await _save_message(conversation_id, "user", user_message)

            # ── Build LangGraph state ─────────────────────────────────────
            # Load full history so the intake agent has context across turns
            history = await _load_messages(conversation_id)

            state: AgentState = {
                "conversation_id": conversation_id,
                "user_id": user_id,
                # history already includes the message we just saved
                "messages": history,
                "intake_complete": False,
                "intake_summary": {},
                "federal_law_results": [],
                "state_law_results": [],
                "case_law_results": [],
                "opinion": "",
                "case_strength_score": 0,
                "recommended_actions": [],
                "referred_lawyers": [],
                "legal_classification": {},
                "early_exit": False,
                "early_exit_reason": "",
            }

            # ── stream_callback: sends each token to client in real-time ──
            # This is what makes responses feel like ChatGPT (token-by-token).
            # Passed via LangGraph config — NOT stored in state (not serializable).
            full_response_parts: list[str] = []
            stream_to_client = _make_stream_callback(websocket, full_response_parts)

            config: RunnableConfig = {
                "configurable": {
                    "thread_id": conversation_id,
                    "user_id": str(user_id),
                    "stream_callback": stream_to_client,
                }
            }

            # ── Notify frontend we are thinking ───────────────────────────
            await websocket.send_json({"type": "status", "message": "Thinking..."})

            # ── Invoke LangGraph graph ────────────────────────────────────
            # This runs: intake_agent → classification → fan_out_research → opinion → referral
            # Tokens stream back via stream_to_client callback above
            try:
                result = await graph.ainvoke(state, config=config)
            except Exception as exc:
                logger.error("Graph invocation error for conv %s: %s", conversation_id, exc)
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": "An error occurred while processing your case. Please try again.",
                    }
                )
                continue

            # ── Save the assembled assistant response to Postgres ─────────
            full_response = "".join(full_response_parts)
            if full_response:
                await _save_message(conversation_id, "assistant", full_response)

            # ── Notify frontend when intake just completed ────────────────
            if result.get("intake_complete"):
                await websocket.send_json({"type": "intake_complete"})
                await websocket.send_json(
                    {
                        "type": "status",
                        "message": "Searching federal law, state law, and past cases simultaneously...",
                    }
                )

            # ── Send final structured results to frontend ─────────────────
            score = result.get("case_strength_score", 0)
            lawyers = result.get("referred_lawyers", [])
            actions = result.get("recommended_actions", [])

            if score:
                # Frontend renders the animated score gauge on this message
                await websocket.send_json({"type": "score", "value": score})

            if lawyers:
                await websocket.send_json({"type": "lawyers", "data": lawyers})

            if actions:
                await websocket.send_json({"type": "actions", "data": actions})

            # ── Persist final state to Postgres ───────────────────────────
            await _finalize_conversation(conversation_id, result)

            # ── Signal frontend the turn is complete ──────────────────────
            await websocket.send_json({"type": "done"})

    except WebSocketDisconnect:
        # Normal — user closed the browser tab or navigated away
        logger.info("WebSocket disconnected: conversation=%s user=%s", conversation_id, user_id)
    except Exception as exc:
        logger.error("Unexpected WebSocket error: %s", exc)
        try:
            await websocket.send_json(
                {"type": "error", "message": "Server error. Please reconnect."}
            )
        except Exception:
            pass  # socket may already be closed
