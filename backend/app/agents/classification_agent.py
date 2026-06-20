"""
agents/classification_agent.py — Triage classifier + early-exit gate.

WHERE IT RUNS:
  intake_agent  →  [intake_complete]  →  classification_agent  →  fan_out_research
  It sits between intake and research so we can (a) label the case for the
  research agents and (b) stop early on cases this tool can't help with —
  before spending time/tokens on external legal-API research.

WHAT IT DOES:
  1. Reads intake_summary from state.
  2. Classifies the matter into EXACTLY ONE bucket:
       employment, housing, consumer, personal_injury, civil_rights
  3. Decides whether to early-exit:
       - criminal-only matter with no civil cause of action, OR
       - the statute of limitations has very likely expired (judged from the
         incident date relative to today and typical US civil limitation
         periods for the bucket).

  It does NOT infer jurisdiction tier (federal vs state) — that is resolved
  downstream by the opinion agent after research.

OUTPUT (to state):
  legal_classification = {bucket, early_exit, early_exit_reason}
  When early_exit is True it also sets the top-level early_exit /
  early_exit_reason fields so graph.py can route straight to END.

LLM USAGE:
  LangChain only as the LLM wrapper (ChatOpenAI + message types). No tools,
  no AgentExecutor. JSON output parsed with the shared raw_decode helper.
"""

import json
from datetime import UTC, datetime

# Import from state.py, NOT graph.py — avoids circular import
from app.agents.parsing import extract_json
from app.agents.state import AgentState
from langchain_core.runnables import RunnableConfig
from app.config import get_settings
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

settings = get_settings()

# The only valid classification buckets.
LEGAL_BUCKETS = ("employment", "housing", "consumer", "personal_injury", "civil_rights")

CLASSIFY_SYSTEM_PROMPT = """You are a legal triage classifier for a US CIVIL litigation assistant.

Classify the case into EXACTLY ONE of these buckets:
- employment       (workplace: discrimination, wrongful termination, wage/hour, harassment)
- housing          (landlord/tenant, eviction, habitability, housing discrimination)
- consumer         (fraud, defective products, debt collection, deceptive business practices)
- personal_injury  (negligence causing physical/emotional harm, accidents, medical)
- civil_rights     (constitutional violations, police/government misconduct, discrimination in public services)

Then decide whether the pipeline should STOP EARLY. Set "early_exit": true when EITHER:
1. The matter is criminal-only with NO civil cause of action (e.g. the user only wants
   someone arrested/prosecuted and there is no civil claim to pursue).
2. The statute of limitations has very likely EXPIRED — judge this from the incident date
   versus today's date and typical US civil limitation periods for the chosen bucket.
Otherwise set "early_exit": false.

Do NOT infer jurisdiction tier (federal vs state) — that is decided later.

Respond with ONLY a JSON object, no other text:
{"bucket": "<one bucket>", "early_exit": <true|false>, "early_exit_reason": "<short reason, or empty string>"}"""


async def run_classification_agent(state: AgentState, config: RunnableConfig) -> dict:
    stream_cb = (config or {}).get("configurable", {}).get("stream_callback")
    intake = state.get("intake_summary", {})

    today = datetime.now(UTC).date().isoformat()

    llm = ChatOpenAI(model=settings.OPENAI_MODEL, api_key=settings.OPENAI_API_KEY)
    response = await llm.ainvoke(
        [
            SystemMessage(content=CLASSIFY_SYSTEM_PROMPT),
            HumanMessage(content=f"Today's date: {today}\nCase intake:\n{json.dumps(intake)}"),
        ]
    )

    parsed = extract_json(response.content) or {}
    bucket = parsed.get("bucket")
    if bucket not in LEGAL_BUCKETS:
        bucket = None
    early_exit = bool(parsed.get("early_exit", False))
    reason = parsed.get("early_exit_reason") or ""

    classification = {
        "bucket": bucket,
        "early_exit": early_exit,
        "early_exit_reason": reason,
    }

    if stream_cb:
        if early_exit:
            await stream_cb(f"\n\nℹ️ {reason}")
        elif bucket:
            await stream_cb(f"\n\n🏷️ Classified as: **{bucket.replace('_', ' ')}**\n")

    result: dict = {"legal_classification": classification}
    if early_exit:
        result["early_exit"] = True
        result["early_exit_reason"] = reason
    return result
