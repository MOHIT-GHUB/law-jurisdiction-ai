"""
middleware/prompt_guard.py — Input safety layer between the user and the LLM.

Runs on every incoming user message (routers/chat.py) BEFORE it reaches any agent.
Layers, cheapest first:

  1. Rate limit   — Redis fixed-window per user (protects your token budget).
  2. Fast checks  — length cap + prompt-injection / jailbreak regex (local, instant).
  3. Moderation   — OpenAI's moderation endpoint (context-aware).

DESIGN NOTE — this is a LEGAL intake tool:
  We deliberately do NOT block legal subject-matter vocabulary (kill, murder,
  weapon, assault, hack, ...). Victims must be able to describe what happened.
  The old keyword blocklist rejected exactly the cases the app exists to handle.
  Moderation likewise only acts on clear MISUSE categories (CSAM, instructions to
  cause harm) — never on plain "violence"/"harassment", which are legal topics.

All external/Redis failures FAIL OPEN (allow) — a safety layer should never take
the app down or block legitimate users because infra hiccupped.
"""

import re

from app.config import get_settings
from app.redis_client import get_redis

settings = get_settings()

MAX_LENGTH = 4000
RATE_LIMIT = 20  # messages allowed...
RATE_WINDOW = 60  # ...per this many seconds, per user

MODERATION_MODEL = "omni-moderation-latest"
# Moderation categories we ACT on. We intentionally exclude violence / harassment /
# hate / self-harm(non-instructional) — those are legitimate legal subject matter.
# These three represent misuse of the tool itself.
_BLOCK_CATEGORIES = {"sexual_minors", "self_harm_instructions", "illicit_violent"}

# Prompt-injection / jailbreak patterns ONLY (not topic words).
BLOCKED_PATTERNS = [
    r"ignore (the |all |any |previous |above )*(instructions|prompt)",
    r"disregard (the |all |your |previous |above )*(instructions|prompt)",
    r"\byou are now\b",
    r"from now on,? you (are|will be|must)\b",
    r"act as (a |an )?(different|new|evil|unfiltered|dan)\b",
    r"pretend (to be|you are|you're|that you)\b",
    r"(reveal|repeat|show|print|output|tell me)\b.{0,30}(system prompt|your instructions|initial prompt)",
    r"\bDAN\b",  # "Do Anything Now" jailbreak
]
_blocked_re = re.compile("|".join(BLOCKED_PATTERNS), re.IGNORECASE)


class PromptGuardResult:
    """Check .allowed first; if False, .reason holds a user-facing message."""

    def __init__(self, allowed: bool, reason: str | None = None):
        self.allowed = allowed
        self.reason = reason


def _fast_checks(message: str) -> PromptGuardResult:
    if len(message) > MAX_LENGTH:
        return PromptGuardResult(
            False, f"Message too long. Please keep it under {MAX_LENGTH} characters."
        )
    if _blocked_re.search(message):
        return PromptGuardResult(
            False,
            "That looks like an attempt to manipulate the assistant. "
            "Please rephrase your legal question.",
        )
    return PromptGuardResult(True)


async def _is_rate_limited(user_id: str | None) -> bool:
    """Fixed-window limiter: RATE_LIMIT messages per RATE_WINDOW per user. Fails open."""
    if not user_id:
        return False
    try:
        redis = await get_redis()
        key = f"ratelimit:{user_id}"
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, RATE_WINDOW)
        return count > RATE_LIMIT
    except Exception:
        return False  # Redis down → don't block the user


async def _is_flagged(message: str) -> bool:
    """OpenAI moderation, restricted to misuse categories. Fails open."""
    if not settings.OPENAI_API_KEY:
        return False
    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        resp = await client.moderations.create(model=MODERATION_MODEL, input=message)
        categories = resp.results[0].categories.model_dump()
        return any(
            hit and name.replace("/", "_") in _BLOCK_CATEGORIES for name, hit in categories.items()
        )
    except Exception:
        return False  # moderation unavailable → don't block


async def check_prompt(message: str, user_id: str | None = None) -> PromptGuardResult:
    """Validate a user message before it reaches the LLM."""
    if await _is_rate_limited(user_id):
        return PromptGuardResult(
            False, "You're sending messages too quickly. Please wait a moment and try again."
        )

    fast = _fast_checks(message)
    if not fast.allowed:
        return fast

    if await _is_flagged(message):
        return PromptGuardResult(
            False,
            "Your message was flagged by our safety filter. LexAI is here to help with "
            "legal questions — please rephrase.",
        )

    return PromptGuardResult(True)
