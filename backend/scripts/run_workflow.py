#!/usr/bin/env python
"""
scripts/run_workflow.py — Manual smoke test for the LexAI agent graph.

Drives the compiled LangGraph pipeline as a MULTI-TURN conversation (no FastAPI /
DB / auth), simulating a user until intake completes or the pipeline early-exits.
This mirrors how chat.py works: one graph.ainvoke per user message, full history
passed each time, a stable thread_id (so MemorySaver resume is exercised too).

DEMO_MODE is forced on, so the four legal tools return canned data (no network).
The LLM is the only thing that would hit OpenAI, so there are two modes:

  # Deterministic, offline, free — LLM + simulated user are stubbed:
  uv run python scripts/run_workflow.py partial --mock

  # True end-to-end — real OpenAI (needs OPENAI_API_KEY); tools still mocked.
  # A persona LLM plays the user and answers the intake agent's questions:
  uv run python scripts/run_workflow.py complete

Scenarios:
  complete    → all intake fields in the first message → completes fast
  partial     → missing the date → intake asks, user answers → completes (multi-turn)
  no-perp     → no identifiable defendant → intake early-exit
  outside-us  → incident abroad          → intake early-exit
  criminal    → criminal-only matter     → classification early-exit
"""

import argparse
import asyncio
import json
import os
import re
import sys
from datetime import date, timedelta

# Make the backend package importable no matter the cwd (scripts/ -> backend/).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# DEMO_MODE must be set BEFORE app modules import (settings is cached at import).
os.environ.setdefault("DEMO_MODE", "True")

# Use a recent incident date so the classifier's statute-of-limitations gate
# doesn't early-exit a smoke run just because the example data went stale.
RECENT_DATE = (date.today() - timedelta(days=30)).isoformat()

SCENARIOS = {
    "complete": (
        f"I was fired from my job at Acme Corp in Austin, Texas on {RECENT_DATE} by my "
        "manager Jane Doe, right after I reported safety violations. I have the "
        "termination email and my complaint emails saved."
    ),
    "partial": (
        "I was fired from my job at Acme Corp in Austin, Texas by my manager Jane Doe "
        "right after I reported safety violations. I have the termination email saved."
    ),
    "no-perp": (
        "Someone smashed my car window overnight, but I have no idea who did it — "
        "no cameras, no witnesses, nothing."
    ),
    "outside-us": (
        f"I was wrongfully evicted from my apartment in Toronto, Canada by my landlord "
        f"on {RECENT_DATE}. I have the lease and our text messages."
    ),
    "criminal": (
        f"My neighbor John Smith punched me in the face on {RECENT_DATE} in Austin, Texas. "
        "I have a police report. I just want him arrested and prosecuted — nothing else."
    ),
}

# Full facts the simulated user "knows" — may be richer than the opening message.
# `partial` opens WITHOUT a date, but the user does know it (a recent one) when asked,
# so the persona must be seeded with the date or it will invent a stale one.
FACTS = {
    "partial": SCENARIOS["complete"],
}

MAX_TURNS = 8
_YEAR = re.compile(r"\b(19|20)\d\d\b")


def _facts(scenario: str) -> str:
    return FACTS.get(scenario, SCENARIOS[scenario])


# ── Mock LLM ─────────────────────────────────────────────────────────────────


class _Chunk:
    """Minimal stand-in for a LangChain streamed chunk (only .content is read)."""

    def __init__(self, content: str) -> None:
        self.content = content


class FakeChat:
    """Drop-in for ChatOpenAI that returns scripted output based on the system prompt.

    Implements .ainvoke() and .astream() — the only two methods the agents use.
    Branches on the SystemMessage content so one fake serves every agent. The intake
    branch is turn-aware: it only completes once a date (a year) appears in the
    conversation, so the `partial` scenario genuinely needs a second user turn.
    """

    def __init__(self, scenario: str, **_kwargs) -> None:
        self.scenario = scenario

    async def ainvoke(self, messages):
        from langchain_core.messages import AIMessage

        return AIMessage(content=self._respond(messages))

    async def astream(self, messages):
        text = self._respond(messages)
        for i in range(0, len(text), 48):
            yield _Chunk(text[i : i + 48])

    def _respond(self, messages) -> str:
        system = " ".join(m.content for m in messages if getattr(m, "type", "") == "system").lower()
        if "intake agent" in system:
            return self._intake(messages)
        if "compress" in system:
            return "[Earlier conversation summary] User described their situation."
        if "triage classifier" in system:
            return self._classify()
        if "federal law research" in system:
            return "Federal: Title VII, 42 U.S.C. § 2000e — strong applicability to this case."
        if "state law research" in system:
            return "State: Texas Labor Code § 21.051 — strong; statute of limitations ~2 years."
        if "case law research" in system:
            return "Case: Doe v. Acme (5th Cir. 2019), plaintiff prevailed — relevance 8/10."
        if "case strength score" in system or "senior us legal analyst" in system:
            return self._opinion()
        if "referral specialist" in system:
            return (
                "Recommended 3 local attorneys. Bring your termination email and complaint records."
            )
        return "OK"

    def _intake(self, messages) -> str:
        if self.scenario == "no-perp":
            reason = (
                "This tool helps build civil suits, which require an identifiable "
                "defendant. Without someone to hold responsible, we can't proceed."
            )
            return f"I'm sorry that happened.\n[EARLY_EXIT]\n{json.dumps({'reason': reason})}"
        if self.scenario == "outside-us":
            reason = "This tool only covers US jurisdictions; the incident occurred outside the US."
            return f"Thanks for sharing.\n[EARLY_EXIT]\n{json.dumps({'reason': reason})}"

        # Need a date before completing — drives the multi-turn `partial` scenario.
        human_text = " ".join(m.content for m in messages if getattr(m, "type", "") == "human")
        if not _YEAR.search(human_text):
            return "Thanks — that's helpful. One more thing: what date did the incident occur?"

        summary = {
            "criminal": {
                "incident": "Physical assault by a neighbor",
                "location": "Austin, Texas",
                "state": "Texas",
                "perpetrator": "John Smith (neighbor)",
                "written_proof": "yes - police report",
                "date_of_incident": RECENT_DATE,
            },
        }.get(
            self.scenario,
            {
                "incident": "Wrongful termination after reporting safety violations",
                "location": "Austin, Texas",
                "state": "Texas",
                "perpetrator": "Acme Corp / manager Jane Doe",
                "written_proof": "yes - termination and complaint emails",
                "date_of_incident": RECENT_DATE,
            },
        )
        return f"Thank you, I have everything I need.\n[INTAKE_COMPLETE]\n{json.dumps(summary)}"

    def _classify(self) -> str:
        if self.scenario == "criminal":
            payload = {
                "bucket": "personal_injury",
                "early_exit": True,
                "early_exit_reason": (
                    "This appears to be a criminal matter with no civil cause of action. "
                    "Please contact law enforcement or a prosecutor."
                ),
            }
        else:
            payload = {"bucket": "employment", "early_exit": False, "early_exit_reason": ""}
        return json.dumps(payload)

    def _opinion(self) -> str:
        payload = {
            "case_strength_score": 72,
            "has_viable_case": True,
            "recommended_actions": [
                "File a charge with the EEOC",
                "Preserve all termination and complaint emails",
                "Consult an employment attorney",
            ],
        }
        return (
            "## Case Overview\nYou likely have a viable retaliation claim.\n\n"
            "## Strongest Arguments\nTitle VII + Texas Labor Code § 21.051.\n\n"
            f"{json.dumps(payload)}"
        )


def _install_mock(scenario: str) -> None:
    """Replace ChatOpenAI in every agent module with the scenario-bound FakeChat."""
    from app.agents import (
        case_law_agent,
        classification_agent,
        federal_law_agent,
        intake_agent,
        opinion_agent,
        referral_agent,
        state_law_agent,
    )

    def factory(**kwargs):
        return FakeChat(scenario, **kwargs)

    for module in (
        intake_agent,
        classification_agent,
        federal_law_agent,
        state_law_agent,
        case_law_agent,
        opinion_agent,
        referral_agent,
    ):
        module.ChatOpenAI = factory


# ── Simulated user ───────────────────────────────────────────────────────────


async def _simulate_user(seed: str, assistant_question: str, mock: bool) -> str:
    """Produce the next user message in reply to the intake agent's question.

    Mock: a canned answer (includes a date so `partial` completes on turn 2).
    Real: a persona LLM that answers using only the scenario's facts.
    """
    if mock:
        return f"Yes, that's right. For the record, it happened on {RECENT_DATE}."

    from app.config import get_settings
    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_openai import ChatOpenAI

    settings = get_settings()
    llm = ChatOpenAI(model=settings.OPENAI_MODEL, api_key=settings.OPENAI_API_KEY)
    persona = (
        "You are role-playing a person seeking legal help. Answer the assistant's latest "
        "question in the first person, briefly and naturally, using ONLY these facts. When "
        "asked for a date, give the EXACT date in the facts — never say you don't remember "
        "and never invent a different date. If asked for something not in the facts, give a "
        f"brief plausible answer consistent with them. Never ask questions.\nFACTS: {seed}"
    )
    resp = await llm.ainvoke(
        [
            SystemMessage(content=persona),
            HumanMessage(content=f"The assistant said:\n{assistant_question}\n\nYour reply:"),
        ]
    )
    return resp.content.strip()


# ── Driver ───────────────────────────────────────────────────────────────────


def _initial_state(history: list[dict]) -> dict:
    return {
        "conversation_id": "smoke-conv",
        "user_id": "smoke-user",
        "messages": list(history),
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


def _summarize(final: dict, turns: int) -> None:
    classification = final.get("legal_classification") or {}
    if final.get("early_exit"):
        where = "classification" if classification else "intake"
        terminal = f"EARLY EXIT at {where}"
    elif final.get("intake_complete"):
        terminal = "FULL PIPELINE → referral"
    else:
        terminal = f"INTAKE INCOMPLETE (gave up after {turns} turns)"

    print("\n\n" + "=" * 60)
    print(f"RESULT: {terminal}  (turns={turns})")
    print("=" * 60)
    print(f"  intake_complete     : {final.get('intake_complete')}")
    print(f"  early_exit          : {final.get('early_exit')}")
    if final.get("early_exit"):
        print(f"  early_exit_reason   : {final.get('early_exit_reason')}")
    print(f"  classification      : {classification.get('bucket')}")
    print(f"  case_strength_score : {final.get('case_strength_score')}")
    print(
        "  research results    : "
        f"federal={len(final.get('federal_law_results', []))} "
        f"state={len(final.get('state_law_results', []))} "
        f"case={len(final.get('case_law_results', []))}"
    )
    print(f"  referred_lawyers    : {len(final.get('referred_lawyers', []))}")
    opinion = (final.get("opinion") or "").strip().replace("\n", " ")
    if opinion:
        print(f"  opinion (snippet)   : {opinion[:120]}...")


async def _run(scenario: str, mock: bool, max_turns: int) -> None:
    if mock:
        os.environ.setdefault("OPENAI_API_KEY", "sk-mock")
        _install_mock(scenario)

    # Import after env + mock are in place.
    from app.agents.graph import graph
    from app.config import get_settings

    # Real mode needs a key — read it from Settings (which loads backend/.env),
    # NOT from os.environ, since pydantic doesn't export .env into the environment.
    if not mock and not get_settings().OPENAI_API_KEY:
        raise SystemExit(
            "Real mode needs OPENAI_API_KEY — set it in backend/.env or the environment "
            "(run from backend/ or via `make smoke`), or use --mock."
        )

    async def stream_cb(token: str) -> None:
        print(token, end="", flush=True)

    # Stable thread_id across turns → exercises MemorySaver resume (like chat.py).
    config = {"configurable": {"thread_id": "smoke-conv", "stream_callback": stream_cb}}

    print(
        f">>> scenario={scenario} mode={'mock' if mock else 'real'} demo_mode={os.environ['DEMO_MODE']}"
    )

    history: list[dict] = []
    user_msg = SCENARIOS[scenario]
    final: dict = {}
    turn = 0
    for turn in range(1, max_turns + 1):
        history = history + [{"role": "user", "content": user_msg}]
        print(f"\n>>> user (turn {turn}): {user_msg}\n--- assistant ---")
        final = await graph.ainvoke(_initial_state(history), config=config)
        history = final.get("messages", history)

        if final.get("early_exit") or final.get("intake_complete"):
            break

        # Intake asked a follow-up — answer as the user and go again.
        assistant_last = next(
            (m["content"] for m in reversed(history) if m["role"] == "assistant"), ""
        )
        user_msg = await _simulate_user(_facts(scenario), assistant_last, mock)

    _summarize(final, turn)


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke-test the LexAI agent graph.")
    parser.add_argument("scenario", choices=sorted(SCENARIOS), help="which scenario to run")
    parser.add_argument(
        "--mock", action="store_true", help="stub the LLM + user (deterministic, offline, free)"
    )
    parser.add_argument(
        "--max-turns", type=int, default=MAX_TURNS, help=f"max user turns (default {MAX_TURNS})"
    )
    args = parser.parse_args()
    asyncio.run(_run(args.scenario, args.mock, args.max_turns))


if __name__ == "__main__":
    main()
