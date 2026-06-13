"""
Cornell LII tool — searches state statutes via LII's free API.
"""
import httpx
from app.config import get_settings
from app.redis_client import cache_get, cache_set, make_cache_key

settings = get_settings()

LII_BASE = "https://www.law.cornell.edu/search/search.json"

_DEMO_DATA = [
    {
        "title": "Texas Civil Practice and Remedies Code § 16.003",
        "summary": "Two-year statute of limitations for personal injury claims in Texas.",
        "url": "https://www.law.cornell.edu/statutes/Texas",
        "state": "Texas",
    },
    {
        "title": "Texas Labor Code § 21.051",
        "summary": "Prohibits employment discrimination based on protected characteristics.",
        "url": "https://www.law.cornell.edu/statutes/Texas/labor",
        "state": "Texas",
    },
]


async def search_cornell_lii(query: str, state: str = "") -> list[dict]:
    if settings.DEMO_MODE:
        return _DEMO_DATA

    cache_key = make_cache_key("lii", query=query, state=state)
    cached = await cache_get(cache_key)
    if cached:
        return cached

    search_query = f"{state} {query}".strip() if state else query

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                LII_BASE,
                params={"query": search_query, "collection": "statutes"},
            )
            resp.raise_for_status()
            data = resp.json()
            results = [
                {
                    "title": item.get("title", ""),
                    "summary": item.get("snippet", ""),
                    "url": item.get("url", ""),
                    "state": state,
                }
                for item in data.get("results", [])[:10]
            ]
            await cache_set(cache_key, results)
            return results
    except Exception:
        return _DEMO_DATA
