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

TEAM — EFFORT ESTIMATE: 2-4 hours. This is the hardest file.
  Start by implementing authentication + a basic echo response,
  then add LangGraph invocation, then add DB saving.
  Use ChatGPT: paste this entire docstring and say "implement this".
"""

# ── TODO: implement this file ─────────────────────────────────────────────────
from fastapi import APIRouter

router = APIRouter(tags=["chat"])

# IMPLEMENT: @router.websocket("/ws/{conversation_id}")
# See the full skeleton in the docstring above.
