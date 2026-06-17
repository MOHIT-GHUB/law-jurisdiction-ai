"""
agents/referral_agent.py — Finds and recommends nearby attorneys.

RESPONSIBILITY:
  The final step of the pipeline. After the user understands their case,
  connect them with a real lawyer who can actually help.

  This closes the loop: LexAI doesn't just inform — it takes action.
  'Find me a lawyer' is what users actually want at the end.

HOW _infer_specialty() WORKS:
  Scans the incident description and opinion text for keywords to
  determine the most relevant type of attorney to search for.
  This is a simple keyword match — not ML. Fast and reliable enough.
  TEAM: Add more keyword mappings for common case types:
    housing/landlord → "tenant rights attorney"
    immigration → "immigration attorney"
    family/divorce → "family law attorney"

HOW LAWYER SEARCH WORKS:
  Uses Google Maps Places API with query:
  "[specialty] near [city, state]"
  Results cached in Redis for 24 hours (lawyers don't move often).
  Without Google Maps API key, returns DEMO_DATA (3 example lawyers).

TEAM — WHERE HUMAN EFFORT IS NEEDED:
  1. Get a Google Maps API key (free tier: 200$/month credit).
     Without it, referral always shows demo data.
  2. Google Maps Places returns general "lawyer" listings, not filtered
     by bar admission or specialty. The LLM reranks them by specialty match.
     IMPROVEMENT: Use Avvo API or State Bar APIs for licensed attorney data.
  3. Test _infer_specialty() with at least 10 different case descriptions
     and verify it returns the right specialty.
  4. The LLM recommendation script (what to say when calling the lawyer)
     is a nice UX touch — test that it generates sensible scripts.

AI USAGE NOTE:
  _infer_specialty() is the most improvable function here. Ask an AI:
  "expand this keyword-based specialty mapper to cover 20 common US
  legal case types" and show it the current function.
"""

import json

# Import from state.py, NOT graph.py — avoids circular import
from app.agents.state import AgentState
from app.config import get_settings
from app.tools.lawyer_finder_tool import find_lawyers_near
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

settings = get_settings()

SYSTEM_PROMPT = """You are a legal referral specialist.
Given a case summary and a list of nearby attorneys, recommend the TOP 3 most suitable lawyers.
For each recommendation explain:
- Why this lawyer's specialty matches the case
- What to say when calling them (brief intro script)
- What documents to bring to the first consultation

Keep recommendations practical and actionable."""


async def run_referral_agent(state: AgentState) -> dict:
    intake = state.get("intake_summary", {})
    opinion = state.get("opinion", "")
    score = state.get("case_strength_score", 50)
    location = intake.get("location", "")
    state_name = intake.get("state", "")

    # Determine specialty needed based on case type
    specialty = _infer_specialty(intake.get("incident", ""), opinion)

    lawyers = await find_lawyers_near(location=location, specialty=specialty, state=state_name)

    llm = ChatOpenAI(model=settings.OPENAI_MODEL, api_key=settings.OPENAI_API_KEY)
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(
            content=f"Case: {json.dumps(intake)}\nCase strength: {score}/100\nNearby lawyers: {json.dumps(lawyers[:10])}"
        ),
    ]
    response = await llm.ainvoke(messages)

    stream_cb = state.get("stream_callback")
    if stream_cb:
        await stream_cb(f"\n\n---\n## 👨‍⚖️ Recommended Attorneys\n\n{response.content}")

    return {
        "referred_lawyers": lawyers,
    }


def _infer_specialty(incident: str, opinion: str) -> str:
    text = (incident + " " + opinion).lower()
    if any(w in text for w in ["employment", "fired", "workplace", "discrimination", "harassment"]):
        return "employment lawyer"
    if any(w in text for w in ["assault", "battery", "injury", "accident"]):
        return "personal injury lawyer"
    if any(w in text for w in ["contract", "business", "fraud"]):
        return "business litigation lawyer"
    if any(w in text for w in ["civil rights", "police", "constitutional"]):
        return "civil rights attorney"
    return "general practice attorney"
