"""
agents/case_law_agent.py — Finds winning past court cases via CourtListener.

RESPONSIBILITY:
  Find real precedent cases where plaintiffs WON on similar facts.
  This is the most compelling output for users — "someone just like you won."

WHY THIS IS A WIN FACTOR FOR THE HACKATHON:
  Judges will ask "how is this different from ChatGPT asking for legal advice?"
  Answer: We search REAL court databases for REAL cases that ACTUALLY WON.
  This is grounded, verifiable, and specific — not generic LLM output.

HOW IT WORKS:
  CourtListener is a free, open API with 4M+ court opinions.
  No API key needed for basic usage (rate-limited but sufficient for demo).
  Results include case name, court, date, and full opinion text snippet.

TEAM — WHERE HUMAN EFFORT IS NEEDED:
  1. Test CourtListener search quality with sample queries.
     Try: "employment discrimination Texas 2020" and see if results are relevant.
  2. CourtListener returns opinion snippets, not full decisions.
     The LLM has to infer win/loss from the snippet — this can be wrong.
     IMPROVEMENT: Filter for opinions where the API indicates plaintiff won.
     CourtListener API has 'type' and 'precedential_status' fields — use them.
  3. The SYSTEM_PROMPT asks for relevance score (1-10). This feeds into
     the case_strength_score in opinion_agent. Calibrate the scoring.

AI USAGE NOTE:
  The most impactful improvement here is better CourtListener query building.
  Ask an AI: "write a function that builds an optimal CourtListener boolean
  search query from a legal incident description and US state".
"""
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from app.config import get_settings
# Import from state.py, NOT graph.py — avoids circular import
from app.agents.state import AgentState
from app.tools.courtlistener_tool import search_courtlistener
import json

settings = get_settings()

SYSTEM_PROMPT = """You are a case law research specialist.
Given a legal incident, find past US court cases with similar facts where the plaintiff WON.
For each case:
- Case name and citation
- Court and year
- Key facts that match our case
- Why the plaintiff won
- Relevance score to current case (1-10)

Focus on cases from the same state if possible. Federal circuit cases also valuable."""


async def run_case_law_agent(state: AgentState) -> dict:
    intake = state.get("intake_summary", {})

    raw_results = await search_courtlistener(
        query=intake.get("incident", ""),
        state=intake.get("state", ""),
    )

    llm = ChatOpenAI(model=settings.OPENAI_MODEL, api_key=settings.OPENAI_API_KEY)
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(
            content=f"Case: {json.dumps(intake)}\nCourtListener results: {json.dumps(raw_results[:5])}"
        ),
    ]
    response = await llm.ainvoke(messages)

    stream_cb = state.get("stream_callback")
    if stream_cb:
        await stream_cb(f"\n🔍 **Case Law Research complete**\n")

    return {
        "case_law_results": [
            {"source": "CourtListener", "raw": raw_results, "analysis": response.content}
        ]
    }
