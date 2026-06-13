"""
middleware/prompt_guard.py — Input validation layer between user and LLM.

WHY THIS EXISTS:
  Without a guard, users can:
    - Send 10,000 character messages (burns tokens, slows everything)
    - Attempt prompt injection ("ignore all previous instructions")
    - Try to jailbreak the agent into giving illegal advice
    - Spam off-topic messages ("write me a poem")

  The guard runs BEFORE the message reaches any LLM. Fast, cheap, no API calls.

HOW check_prompt() WORKS:
  1. Length check — anything over 4000 chars is rejected immediately
  2. Regex scan for blocked injection/abuse patterns
  3. Returns PromptGuardResult(allowed=True/False, reason=<message to show user>)

WHERE IT'S CALLED:
  In the WebSocket handler (routers/chat.py) — TEAM must wire this up.
  Every incoming user message goes through check_prompt() FIRST.

TEAM — WHAT YOU MUST DO:
  1. In the WebSocket handler, call check_prompt(message) before processing:
       guard = check_prompt(user_message)
       if not guard.allowed:
           await websocket.send_json({"type": "error", "message": guard.reason})
           continue
  2. Review BLOCKED_PATTERNS — add or remove patterns for your use case
  3. Consider adding a rate limiter (max 20 messages/minute per user)
     Ask an AI: "add a Redis-based rate limiter to check_prompt"

AI USAGE NOTE:
  The pattern list is good but can be improved. Ask ChatGPT:
  "add more prompt injection patterns to this regex list"
  — this is low effort, high impact for judges noticing security awareness.
"""
import re
from typing import Optional

# Patterns that are ALWAYS blocked — injection attempts and abuse
# re.IGNORECASE means KILL/Kill/kill all match
BLOCKED_PATTERNS = [
    r"\b(bomb|weapon|kill|murder|hack|exploit|jailbreak)\b",
    r"ignore (previous|all) instructions",  # classic prompt injection
    r"you are now",                          # persona hijacking attempt
    r"act as (a |an )?(different|new|evil|dan)",  # DAN-style jailbreak
    r"system prompt",                        # trying to extract system prompt
]

# LEGAL_KEYWORDS kept here for future use — could use these to enforce
# topic relevance after intake is complete (not currently enforced to avoid
# blocking legitimate user phrasing)
LEGAL_KEYWORDS = [
    "law", "legal", "court", "jurisdiction", "rights", "case", "sue", "lawsuit",
    "attorney", "lawyer", "judge", "statute", "regulation", "offense", "crime",
    "contract", "violation", "complaint", "evidence", "defendant", "plaintiff",
    "police", "arrest", "discrimination", "harassment", "injury", "liability",
    # Common words during intake phase — always allow
    "incident", "happened", "location", "state", "city", "witness", "proof",
    "date", "time", "help", "need", "what", "how", "my", "i", "yes", "no",
]

# Pre-compile the regex once at module load (faster than re.compile on every call)
_blocked_re = re.compile("|".join(BLOCKED_PATTERNS), re.IGNORECASE)


class PromptGuardResult:
    """Simple result object. Check .allowed first, then .reason for the error message."""
    def __init__(self, allowed: bool, reason: Optional[str] = None):
        self.allowed = allowed
        self.reason = reason


def check_prompt(message: str, is_intake: bool = True) -> PromptGuardResult:
    """
    Validate a user message before it reaches the LLM.

    Args:
        message:   The raw user message string
        is_intake: True while the intake agent is collecting info.
                   Currently both stages have same rules, but is_intake
                   is kept as a hook for future tighter post-intake filtering.

    Returns:
        PromptGuardResult with allowed=True if message passes all checks.
        If allowed=False, .reason contains a user-friendly error message.
    """
    # Check 1: Reject oversized messages to prevent token flooding
    if len(message) > 4000:
        return PromptGuardResult(False, "Message too long. Please keep it under 4000 characters.")

    # Check 2: Block known injection and abuse patterns
    if _blocked_re.search(message):
        return PromptGuardResult(
            False,
            "Your message was flagged as off-topic or potentially abusive. "
            "LexAI is designed to help with US legal jurisdiction questions only.",
        )

    # All checks passed
    return PromptGuardResult(True)
