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

import json

# Import from state.py, NOT graph.py — avoids circular import
from app.agents.state import AgentState
from app.config import get_settings
from app.tools.courtlistener_tool import search_courtlistener
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI

settings = get_settings()

SYSTEM_PROMPT = """You are a case law research specialist.

You are given the user's incident and a list of REAL court cases retrieved from CourtListener
(each has case_name, court, citation, date, summary, and url).

STRICT RULES:
- Discuss ONLY the cases provided below. NEVER invent a case name, citation, court, or URL.
- Whenever you reference a case, link it as a markdown link using its url: [Case name](url).
- If none of the retrieved cases are genuinely on point, say so plainly — do not fabricate precedent.

Order cases most-relevant first. For each relevant case, write a short paragraph:
- **[Case name, citation](url)** — court and year
- Holding & key facts (what the court decided and why)
- Why it is analogous to (or distinguishable from) the user's situation
- Relevance score (1-10)

Prefer cases from the user's state; federal circuit cases also count."""

# CourtListener is a full-text engine — a narrative sentence retrieves poorly.
# We first distill the incident into legal search terms (causes of action / terms
# of art), which dramatically improves relevance.
QUERY_BUILD_PROMPT = """You write search queries for CourtListener, a full-text search engine over US court opinions.

Given a legal incident, output a SHORT query (3-8 words) of the key legal concepts, causes of
action, and claim types a lawyer would search for — using legal terms of art, NOT a narrative.

Examples:
- "fired after reporting safety violations" -> whistleblower retaliation wrongful termination
- "landlord entered my apartment without notice" -> tenant privacy unlawful entry landlord
- "a coworker's prank physically injured me at work" -> assault battery negligence workplace injury

Output ONLY the query text — no quotes, no labels, no explanation."""


async def _build_search_query(intake: dict, bucket: str, llm) -> str:
    """Distill the incident into focused legal search terms for CourtListener."""
    incident = intake.get("incident", "")
    if not incident:
        return ""
    resp = await llm.ainvoke(
        [
            SystemMessage(content=QUERY_BUILD_PROMPT),
            HumanMessage(content=f"Incident: {incident}\nCase type: {bucket or 'unknown'}"),
        ]
    )
    query = (resp.content or "").strip().strip('"').replace("\n", " ")
    return query or incident


async def run_case_law_agent(state: AgentState, config: RunnableConfig) -> dict:
    intake = state.get("intake_summary", {})
    bucket = (state.get("legal_classification") or {}).get("bucket") or ""

    llm = ChatOpenAI(model=settings.OPENAI_MODEL, api_key=settings.OPENAI_API_KEY)

    # Build a focused query first, then search with it.
    query = await _build_search_query(intake, bucket, llm)
    raw_results = await search_courtlistener(query=query, state=intake.get("state", ""))
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(
            content=(
                f"User's case:\n{json.dumps(intake)}\n\n"
                "Retrieved cases (cite ONLY these; include each one's url as a link):\n"
                f"{json.dumps(raw_results[:8], indent=2)}"
            )
        ),
    ]
    response = await llm.ainvoke(messages)

    stream_cb = (config or {}).get("configurable", {}).get("stream_callback")
    if stream_cb:
        await stream_cb("\n🔍 **Case Law Research complete**\n")

    return {
        "case_law_results": [
            {"source": "CourtListener", "raw": raw_results, "analysis": response.content}
        ]
    }
