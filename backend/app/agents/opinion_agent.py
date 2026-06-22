"""
agents/opinion_agent.py — Synthesizes all research into a final legal opinion.

RESPONSIBILITY:
  This is the most important agent output — what the user actually reads.
  It receives all 3 research results and produces:
  1. Plain-English case overview
  2. Strongest legal arguments
  3. Case Strength Score (0-100) — the visual centerpiece of the UI
  4. Direct answer: does the user have a viable case?
  5. Risks and weaknesses (honesty builds trust)
  6. Recommended next steps

CASE STRENGTH SCORE — WHY IT WINS HACKATHONS:
  Abstract legal analysis is hard for judges to evaluate.
  A score ("Your case strength: 74/100") is immediately understandable.
  It shows the system is doing real analysis, not just rephrasing the question.
  Display this as a colored progress bar in the frontend:
    0-30  = red,  31-60 = yellow,  61-85 = green,  86-100 = dark green

HOW THE SCORE IS EXTRACTED:
  The LLM is instructed to end its response with a specific JSON block:
  {"case_strength_score": 74, "has_viable_case": true, "recommended_actions": [...]}
  _parse_opinion_json() extracts this with regex then removes it from
  the user-facing text (so the user doesn't see raw JSON).

STREAMING:
  This is the longest agent response. It MUST stream to the frontend or
  users will stare at a blank screen for 10-20 seconds. Streaming is
  implemented via the stream_callback from LangGraph config.

TEAM — WHERE HUMAN EFFORT IS NEEDED:
  1. JSON extraction regex is fragile for complex nested JSON.
     Test with outputs where the LLM puts line breaks inside the JSON block.
  2. The score calibration needs real testing. Does the LLM give scores
     that feel accurate? Have someone with legal knowledge review 5 cases.
  3. Disclaimer: The output MUST include a legal disclaimer
     ("This is not legal advice. Consult a licensed attorney.").
     The SYSTEM_PROMPT includes this — verify it's always in the output.
  4. Token cost: this agent sends the most tokens (all 3 research results).
     If OpenAI costs are high during testing, use gpt-4o-mini here only.

AI USAGE NOTE:
  The prompt here is the highest-value thing to iterate on. Have a team
  member refine the exact wording every few test runs. No code changes needed
  — just update SYSTEM_PROMPT. Use GPT-4 to help write better prompts.
"""

import json

# Import from state.py, NOT graph.py — avoids circular import
from app.agents.parsing import extract_json
from app.agents.state import AgentState
from app.config import get_settings
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI

settings = get_settings()

# The opinion ends with a machine-readable JSON block (sometimes inside a ```json
# fence). We never stream from the first such marker on, and strip it from the
# stored opinion. Legal prose effectively never contains "{" or "```", so cutting
# at the earliest marker is safe.
_OPINION_CUT_MARKERS = ("```", "{")
# Hold back enough trailing chars while streaming that a partial fence ("``")
# split across chunks can't leak before we recognize it.
_OPINION_HOLD = len("```")


def _opinion_visible(text: str) -> str:
    """Return the human-readable opinion: everything before the trailing JSON/fence."""
    cut = len(text)
    for marker in _OPINION_CUT_MARKERS:
        i = text.find(marker)
        if i != -1:
            cut = min(cut, i)
    return text[:cut].rstrip()


SYSTEM_PROMPT = """You are a senior US legal analyst writing a clear, rigorous opinion for a non-lawyer.

You are given the user's case, the research agents' analyst notes, and a `sources` object holding
the ACTUAL statutes and court cases retrieved for this matter — each item has a `url`.

GROUNDING RULES (critical — violating these makes the opinion worthless):
- Cite ONLY statutes and cases that appear in `sources`. NEVER invent a case name, citation,
  statute number, court, or URL.
- Every authority you cite MUST be a markdown link using its url: [Name or citation](url).
- If `sources` contains no on-point authority for a section, say so honestly
  (e.g. "No directly on-point cases were retrieved") instead of fabricating one.

Write the opinion in markdown with these sections:

## Case Overview
Plain-English summary of the situation and the precise legal question(s).

## Applicable Law
The relevant statutes/regulations from `sources`. For each: cite with a link, explain in plain
English what it requires or protects, and tie it to these specific facts.

## Relevant Case Law
A full paragraph PER relevant case in `sources` — go deep, this is the most valuable section:
- Start with **[Case name, citation](url)** (court, year).
- State the court's holding and the facts that drove it.
- Explain precisely why it is analogous to (or distinguishable from) the user's facts, and what
  that implies for their likelihood of success.
- Note the outcome/remedy (damages, injunction, etc.) where known.
If no retrieved case is on point, say so plainly rather than inventing precedent.

## Case Strength Score
A 0-100 score with a one-paragraph justification (0-30 weak, 31-60 moderate, 61-85 strong,
86-100 very strong).

## Viability
Direct yes/no on whether the user has a viable case, with reasoning.

## Risks & Weaknesses
Be honest: evidentiary gaps, deadlines (statute of limitations), counterarguments.

## Recommended Next Steps
3-5 concrete, prioritized actions.

End with: "*This is not legal advice. Consult a licensed attorney.*"

IMPORTANT: After the disclaimer, output a JSON block in EXACTLY this format and write nothing after it:
{"case_strength_score": <number>, "has_viable_case": <true|false>, "recommended_actions": ["action1", "action2", "action3"]}"""


def _sources(results: list[dict]) -> list[dict]:
    """Flatten the structured `raw` items (with real URLs) out of research results."""
    items: list[dict] = []
    for r in results or []:
        items.extend(r.get("raw", []) or [])
    return items


async def run_opinion_agent(state: AgentState, config: RunnableConfig) -> dict:
    intake = state.get("intake_summary", {})
    federal = state.get("federal_law_results", [])
    state_law = state.get("state_law_results", [])
    case_law = state.get("case_law_results", [])

    context = {
        "intake": intake,
        # Analyst notes from each research agent (prose).
        "analysis": {
            "federal": [r.get("analysis", "") for r in federal],
            "state": [r.get("analysis", "") for r in state_law],
            "case_law": [r.get("analysis", "") for r in case_law],
        },
        # The REAL retrieved authorities, each with a url — cite only from here.
        "sources": {
            "federal_statutes": _sources(federal),
            "state_statutes": _sources(state_law),
            "cases": _sources(case_law),
        },
    }

    llm = ChatOpenAI(model=settings.OPENAI_MODEL, api_key=settings.OPENAI_API_KEY, streaming=True)
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=f"Case file and retrieved sources:\n{json.dumps(context, indent=2)}"),
    ]

    opinion_text = ""
    sent = 0
    stream_cb = (config or {}).get("configurable", {}).get("stream_callback")

    if stream_cb:
        await stream_cb("\n\n---\n## 📊 Legal Analysis\n\n")

    # Stream only the human-readable analysis: forward the growing visible delta,
    # holding back a few trailing chars so the JSON block / code fence never leaks.
    async for chunk in llm.astream(messages):
        opinion_text += chunk.content
        if stream_cb:
            safe_end = len(_opinion_visible(opinion_text)) - _OPINION_HOLD
            if safe_end > sent:
                await stream_cb(_opinion_visible(opinion_text)[sent:safe_end])
                sent = safe_end

    clean_opinion = _opinion_visible(opinion_text)
    if stream_cb and len(clean_opinion) > sent:
        await stream_cb(clean_opinion[sent:])

    # Parse the structured JSON output (raw_decode handles nested braces).
    parsed = extract_json(opinion_text) or {}
    try:
        score = int(parsed.get("case_strength_score", 50))
    except (TypeError, ValueError):
        score = 50
    recommended_actions = parsed.get("recommended_actions", []) or []

    return {
        "opinion": clean_opinion,
        "case_strength_score": score,
        "recommended_actions": recommended_actions,
    }
