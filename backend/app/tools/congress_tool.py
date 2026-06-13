"""
tools/congress_tool.py — Federal legislation search via Congress.gov API.

HOW IT WORKS:
  GET https://api.congress.gov/v3/bill?query=...&api_key=...
  Returns a list of bills with title, number, congress session, URL.
  The federal_law_agent passes these results to the LLM for analysis.

CACHING STRATEGY:
  Redis cache key = hash of (query + state).
  First call: hits API, stores result for 1 hour.
  Repeat calls: returns from Redis instantly.
  WHY: Congress.gov has rate limits. Caching means the same query
  (e.g., "employment discrimination Texas") only hits the API once
  even across multiple user conversations.

DEMO MODE:
  If DEMO_MODE=True in .env, always returns _DEMO_DATA.
  If the API call fails for ANY reason, falls back to _DEMO_DATA.
  This means the app NEVER crashes during the demo, even on bad wifi.

  ⚠️ _DEMO_DATA TEAM TASK: Update _DEMO_DATA with laws relevant to
     your planned demo scenario. If you'll demo an employment case in
     Texas, make sure _DEMO_DATA has Title VII + FLSA + relevant statutes.

API KEY:
  Free signup: https://api.congress.gov/sign-up/
  Add to .env: CONGRESS_API_KEY=your_key_here
  Without a key, the API still works but with stricter rate limits.

TEAM — WHAT YOU MUST DO:
  1. Get a Congress.gov API key
  2. Update _DEMO_DATA for your specific demo use case
  3. Test with a real query: python -c "import asyncio; from app.tools.congress_tool import search_congress; print(asyncio.run(search_congress('employment discrimination', 'Texas')))"
"""
import httpx
from app.config import get_settings
from app.redis_client import cache_get, cache_set, make_cache_key

settings = get_settings()

CONGRESS_BASE = "https://api.congress.gov/v3"

# TEAM: Update this with real, relevant statutes for your demo scenario
_DEMO_DATA = [
    {
        "title": "Civil Rights Act of 1964 - Title VII",
        "citation": "42 U.S.C. § 2000e",
        "summary": "Prohibits employment discrimination based on race, color, religion, sex, or national origin.",
        "url": "https://api.congress.gov/v3/bill/88/hr/7152",
    },
    {
        "title": "Americans with Disabilities Act",
        "citation": "42 U.S.C. § 12101",
        "summary": "Prohibits discrimination against individuals with disabilities in all areas of public life.",
        "url": "https://api.congress.gov/v3/bill/101/s/933",
    },
]


async def search_congress(query: str, state: str = "") -> list[dict]:
    """
    Search Congress.gov for bills/statutes relevant to the query.

    Args:
        query: Natural language description (e.g., "employment discrimination")
        state: US state name for context (doesn't filter API, used in cache key)

    Returns:
        List of bill dicts with title, citation, url, congress fields.
        Falls back to _DEMO_DATA on any error.
    """
    # DEMO_MODE bypass — set in .env before hackathon demo
    if settings.DEMO_MODE:
        return _DEMO_DATA

    # Check Redis cache before hitting the API
    cache_key = make_cache_key("congress", query=query, state=state)
    cached = await cache_get(cache_key)
    if cached:
        return cached  # cache hit — instant return

    params = {
        "query": query,
        "api_key": settings.CONGRESS_API_KEY,
        "limit": 10,
        "sort": "relevanceScore",  # most relevant first
    }

    try:
        # timeout=15.0: don't hang forever if Congress.gov is slow
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(f"{CONGRESS_BASE}/bill", params=params)
            resp.raise_for_status()  # raises on 4xx/5xx
            data = resp.json()
            bills = data.get("bills", [])
            results = [
                {
                    "title": b.get("title", ""),
                    "citation": f"Bill {b.get('number', '')}",
                    "url": b.get("url", ""),
                    "congress": b.get("congress", ""),
                }
                for b in bills
            ]
            await cache_set(cache_key, results)  # store for 1 hour
            return results
    except Exception:
        # Graceful fallback — never let an API failure crash the demo
        return _DEMO_DATA
