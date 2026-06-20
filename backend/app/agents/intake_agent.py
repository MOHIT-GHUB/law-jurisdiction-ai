r"""
agents/intake_agent.py — First agent in the pipeline. Gathers case information.

RESPONSIBILITY:
  Conduct a natural, empathetic conversation with the user to collect:
    1. Incident description
    2. Location (city + state, must be in the US)
    3. Perpetrator identity (required)
    4. Written proof / documentation
    5. Date of incident

  Once all fields are collected, it signals [INTAKE_COMPLETE] + a JSON summary,
  which triggers the graph's conditional edge to the classification agent.

EARLY EXIT (new):
  The pipeline only handles US civil matters that have an identifiable
  defendant. The agent emits [EARLY_EXIT] + a JSON {"reason": ...} when:
    - The user cannot identify ANY perpetrator (individual, company,
      government entity, or broad organization) — there is no one to sue.
    - The incident occurred outside the United States.
  graph.py routes early_exit straight to END.

STREAMING (fixed):
  stream_callback is read from LangGraph's config — NOT from state — because
  MemorySaver serializes state and a callback isn't serializable (see state.py).
  Every node now accepts (state, config) and reads:
    config["configurable"]["stream_callback"]

CONTEXT COMPRESSION (replaces the old sliding window):
  Instead of dropping old messages (which loses facts), once the running
  history exceeds COMPRESSION_TOKEN_THRESHOLD we summarize the older turns
  into a single message and keep the most recent ones verbatim. The
  structured intake_summary dict lives in state and is never altered, so no
  collected field is ever lost to compression.

ROBUST JSON PARSING (fixed):
  All extraction uses agents/parsing.extract_json (json.JSONDecoder().raw_decode)
  instead of a regex, so nested braces / messy output are handled.
"""

import json

# Import from state.py, NOT graph.py — avoids circular import
from app.agents.parsing import extract_json
from app.agents.state import AgentState
from app.config import get_settings
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

settings = get_settings()

# Once the estimated token size of the message history exceeds this, older
# turns are compressed into a single summary message.
COMPRESSION_TOKEN_THRESHOLD = 3000
# Number of most-recent turns always kept verbatim (never compressed).
RECENT_MESSAGES_TO_KEEP = 4

INTAKE_SYSTEM_PROMPT = """You are LexAI's Intake Agent — a compassionate, professional legal intake specialist for US CIVIL matters.

Your ONLY job is to gather the following information from the user. Ask for ONE missing piece of information at a time, naturally:
1. A clear description of the incident
2. Location (city AND state in the US)
3. Who is the perpetrator (an individual, company, government entity, or organization?)
4. Any written proof or documentation (yes/no and what type)
5. Date of the incident

Rules:
- Be empathetic — users may be in distress.
- Never give legal advice yourself — you are only collecting information.
- If the user volunteers multiple fields at once, acknowledge them all.
- Ask for only what is still MISSING. If the conversation already contains all 5
  fields, do NOT ask further questions — go straight to completion below.
- Per turn, output EITHER a single follow-up question OR a completion/early-exit
  block. Never write both, and never role-play the user's answers.

EARLY EXIT — these cases are out of scope. When you determine one applies, do NOT
keep asking questions. Briefly and kindly explain why, then end your response with
the exact tag [EARLY_EXIT] followed by a JSON object {"reason": "<short reason>"}:
- PERPETRATOR is required. If the user genuinely cannot identify anyone to hold
  responsible (no individual, company, government entity, or organization), explain
  that this tool helps build CIVIL suits, which require an identifiable defendant,
  and that without one we cannot proceed.
- LOCATION must be in the United States. If the incident occurred outside the US,
  explain that this tool only covers US jurisdictions.

COMPLETION — When you have ALL 5 fields, end your response with the exact tag
[INTAKE_COMPLETE] followed by a JSON object with keys:
incident, location, state, perpetrator, written_proof, date_of_incident

Example completion:
"Thank you for sharing all the details. Let me now research your case.
[INTAKE_COMPLETE]
{"incident": "...", "location": "Austin, Texas", "state": "Texas", "perpetrator": "...", "written_proof": "yes - email records", "date_of_incident": "2024-03-15"}"
"""

COMPRESSION_SYSTEM_PROMPT = """You compress legal-intake conversations.
Summarize the conversation below into a concise paragraph that preserves EVERY fact
the user provided (incident details, names, dates, locations, evidence). Do not add
information, do not give legal advice, and do not include disclaimers."""


_CONTROL_TAGS = ("[INTAKE_COMPLETE]", "[EARLY_EXIT]")
# While streaming, hold back this many trailing chars so a partial tag
# ("[INTAKE_COMPL…") can never leak before we recognize and strip it.
_MAX_TAG_LEN = max(len(t) for t in _CONTROL_TAGS)


def _clean_response(text: str) -> str:
    """Strip control tags (and the JSON that follows them) from user-facing text."""
    for tag in _CONTROL_TAGS:
        idx = text.find(tag)
        if idx != -1:
            text = text[:idx]
    return text.strip()


def _estimate_tokens(messages: list[dict]) -> int:
    """Rough token estimate (~4 chars/token) — avoids a tokenizer dependency."""
    return sum(len(m.get("content", "")) for m in messages) // 4


async def _compress_history(history: list[dict], intake_summary: dict) -> list[dict]:
    """Summarize older turns when history grows too large; keep recent turns verbatim.

    intake_summary is passed to the summarizer as authoritative ground truth and is
    never modified here — it is preserved verbatim in state by the caller.
    """
    if _estimate_tokens(history) <= COMPRESSION_TOKEN_THRESHOLD:
        return history
    if len(history) <= RECENT_MESSAGES_TO_KEEP:
        return history

    older = history[:-RECENT_MESSAGES_TO_KEEP]
    recent = history[-RECENT_MESSAGES_TO_KEEP:]

    transcript = "\n".join(f"{m['role']}: {m['content']}" for m in older)
    llm = ChatOpenAI(model=settings.OPENAI_MODEL, api_key=settings.OPENAI_API_KEY)
    resp = await llm.ainvoke(
        [
            SystemMessage(content=COMPRESSION_SYSTEM_PROMPT),
            HumanMessage(
                content=(
                    "Structured data already collected (authoritative — do not contradict):\n"
                    f"{json.dumps(intake_summary)}\n\n"
                    f"Conversation to summarize:\n{transcript}"
                )
            ),
        ]
    )
    summary_message = {
        "role": "assistant",
        "content": f"[Earlier conversation summary]\n{resp.content}",
    }
    return [summary_message] + recent


async def run_intake_agent(state: AgentState, config: dict) -> dict:
    stream_cb = (config or {}).get("configurable", {}).get("stream_callback")

    intake_summary = state.get("intake_summary", {})
    # Compress (not truncate) — never lose facts. intake_summary stays verbatim.
    history = await _compress_history(state.get("messages", []), intake_summary)

    llm = ChatOpenAI(
        model=settings.OPENAI_MODEL,
        api_key=settings.OPENAI_API_KEY,
        streaming=True,
    )

    lc_messages = [SystemMessage(content=INTAKE_SYSTEM_PROMPT)]
    if intake_summary:
        lc_messages.append(
            SystemMessage(content=f"Information collected so far: {json.dumps(intake_summary)}")
        )
    for msg in history:
        if msg["role"] == "user":
            lc_messages.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            lc_messages.append(AIMessage(content=msg["content"]))

    # Stream only the user-facing prose. We forward the growing _clean_response()
    # delta but hold back the last _MAX_TAG_LEN chars, so neither a complete tag +
    # its JSON nor a partial tag ("[INTAKE_COMPL…") split across chunks ever leaks.
    response_text = ""
    sent = 0
    async for chunk in llm.astream(lc_messages):
        response_text += chunk.content
        if stream_cb:
            safe_end = len(_clean_response(response_text)) - _MAX_TAG_LEN
            if safe_end > sent:
                await stream_cb(_clean_response(response_text)[sent:safe_end])
                sent = safe_end

    clean_response = _clean_response(response_text)
    if stream_cb and len(clean_response) > sent:
        # Flush the held-back tail (it's now confirmed tag-free).
        await stream_cb(clean_response[sent:])
    new_messages = history + [{"role": "assistant", "content": clean_response}]

    # Out-of-scope: no identifiable perpetrator, or outside the US.
    if "[EARLY_EXIT]" in response_text:
        early = extract_json(response_text) or {}
        return {
            "messages": new_messages,
            "intake_complete": False,
            "early_exit": True,
            "early_exit_reason": early.get(
                "reason", "This case is outside the scope of this tool."
            ),
        }

    # Intake finished: parse the structured summary block.
    summary = extract_json(response_text) if "[INTAKE_COMPLETE]" in response_text else None
    return {
        "messages": new_messages,
        "intake_complete": summary is not None,
        "intake_summary": summary or intake_summary,
    }
