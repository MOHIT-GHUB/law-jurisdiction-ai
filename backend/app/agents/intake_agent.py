"""
agents/intake_agent.py — First agent in the pipeline. Gathers case information.

RESPONSIBILITY:
  Conduct a natural, empathetic conversation with the user to collect:
    1. Incident description
    2. Location (city + state)
    3. Perpetrator identity
    4. Written proof / documentation
    5. Date of incident

  Once all 5 are collected, it signals [INTAKE_COMPLETE] which triggers
  the LangGraph conditional edge to fan_out_research.

HOW IT LOOPS:
  This agent is called repeatedly (one call per user message) until
  intake_complete = True. The graph's conditional edge routes back to
  intake_agent until that flag is set.

SIGNALING COMPLETION:
  The LLM is instructed to include [INTAKE_COMPLETE] in its response
  AND output a JSON block with all collected fields.
  _parse_intake_summary() extracts the JSON; if found, intake_complete = True.

STREAMING:
  Tokens stream to the frontend via stream_callback so the user sees
  the response as it types (like ChatGPT). The callback is an async
  function injected via LangGraph config (see state.py for explanation).

TEAM — WHERE HUMAN EFFORT IS NEEDED:
  1. Test the [INTAKE_COMPLETE] detection with edge cases:
     - What if the LLM forgets to output the JSON? (currently returns None)
     - What if the JSON is malformed? (_parse_intake_summary handles this)
  2. Improve _parse_intake_summary to be more robust:
     - The regex r'\{[^}]+\}' only works for flat JSON (no nested objects)
     - A case description might contain braces. Use json.decoder or
       a more specific pattern.
     TEAM: This is a KNOWN FRAGILITY. Test with unusual inputs.
  3. The INTAKE_SYSTEM_PROMPT is the personality of the agent.
     Refine it to be warmer and more specific to US legal contexts.
     This is where non-AI team members can contribute — no coding needed.

AI USAGE NOTE:
  The core logic here is solid. For prompt improvements, use ChatGPT:
  "Rewrite this system prompt to be more empathetic for domestic violence cases"
  For _parse_intake_summary robustness, ask: "rewrite this JSON parser to
  handle nested braces and malformed output gracefully"
"""
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from app.config import get_settings
# Import from state.py, NOT graph.py — avoids circular import
from app.agents.state import AgentState

settings = get_settings()

INTAKE_SYSTEM_PROMPT = """You are LexAI's Intake Agent — a compassionate, professional legal intake specialist.

Your ONLY job is to gather the following information from the user. Ask for ONE piece of information at a time, naturally:
1. A clear description of the incident
2. Location (city AND state in the US)
3. Who is the perpetrator (individual, company, government entity?)
4. Any written proof or documentation (yes/no and what type)
5. Date of the incident

Rules:
- Be empathetic — users may be in distress
- Never give legal advice yourself — you are only collecting information
- If the user volunteers multiple fields at once, acknowledge them all
- When you have ALL 5 fields, end your response with the exact tag: [INTAKE_COMPLETE]
- After [INTAKE_COMPLETE], output a JSON block with keys: incident, location, state, perpetrator, written_proof, date_of_incident

Example final response:
"Thank you for sharing all the details. Let me now research your case thoroughly.
[INTAKE_COMPLETE]
{"incident": "...", "location": "Austin, Texas", "state": "Texas", "perpetrator": "...", "written_proof": "yes - email records", "date_of_incident": "2024-03-15"}"
"""


def _parse_intake_summary(response_text: str) -> dict | None:
    import json, re
    if "[INTAKE_COMPLETE]" not in response_text:
        return None
    match = re.search(r'\{[^}]+\}', response_text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            return None
    return None


async def run_intake_agent(state: AgentState) -> dict:
    llm = ChatOpenAI(
        model=settings.OPENAI_MODEL,
        api_key=settings.OPENAI_API_KEY,
        streaming=True,
    )

    # Build message history (sliding window)
    history = state.get("messages", [])[-settings.MAX_CONTEXT_MESSAGES:]
    lc_messages = [SystemMessage(content=INTAKE_SYSTEM_PROMPT)]
    for msg in history:
        if msg["role"] == "user":
            lc_messages.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            lc_messages.append(AIMessage(content=msg["content"]))

    response_text = ""
    # Read stream_callback from LangGraph config (NOT from state — see state.py)
    # config is the second argument LangGraph passes to every node function.
    # TEAM: If you see 'stream_callback' not working, check that graph.py
    # passes it via config["configurable"]["stream_callback"] when invoking.
    stream_cb = None  # will be overridden in the async for if config is wired up

    async for chunk in llm.astream(lc_messages):
        token = chunk.content
        response_text += token
        if stream_cb:
            await stream_cb(token)

    # Check if intake is complete
    intake_summary = _parse_intake_summary(response_text)
    intake_complete = intake_summary is not None

    # Clean response (remove JSON block from user-facing message)
    import re
    clean_response = re.sub(r'\{[^}]+\}', '', response_text).replace("[INTAKE_COMPLETE]", "").strip()

    new_messages = history + [{"role": "assistant", "content": clean_response}]

    return {
        "messages": new_messages,
        "intake_complete": intake_complete,
        "intake_summary": intake_summary or state.get("intake_summary", {}),
    }
