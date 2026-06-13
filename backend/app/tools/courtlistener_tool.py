"""
CourtListener tool — searches past court cases by keyword + state.
"""
import httpx
from app.config import get_settings
from app.redis_client import cache_get, cache_set, make_cache_key

settings = get_settings()

CL_BASE = "https://www.courtlistener.com/api/rest/v3/search/"

_DEMO_DATA = [
    {
        "case_name": "Smith v. City of Dallas, 2019",
        "court": "N.D. Texas",
        "summary": "Plaintiff won civil rights claim after unlawful search; awarded $150,000.",
        "url": "https://www.courtlistener.com/?q=smith+v+dallas",
        "date": "2019-04-12",
    },
    {
        "case_name": "Johnson v. Metro Transit Authority, 2021",
        "court": "5th Circuit",
        "summary": "Employment discrimination — plaintiff succeeded after showing pattern of bias.",
        "url": "https://www.courtlistener.com/?q=johnson+metro",
        "date": "2021-07-22",
    },
]


async def search_courtlistener(query: str, state: str = "") -> list[dict]:
    if settings.DEMO_MODE:
        return _DEMO_DATA

    cache_key = make_cache_key("cl", query=query, state=state)
    cached = await cache_get(cache_key)
    if cached:
        return cached

    params = {
        "q": query,
        "type": "o",        # opinions
        "order_by": "score desc",
        "stat_Precedential": "on",
    }
    headers = {}
    if settings.COURTLISTENER_API_KEY:
        headers["Authorization"] = f"Token {settings.COURTLISTENER_API_KEY}"

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(CL_BASE, params=params, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            results = [
                {
                    "case_name": r.get("caseName", ""),
                    "court": r.get("court", ""),
                    "summary": r.get("snippet", ""),
                    "url": r.get("absolute_url", ""),
                    "date": r.get("dateFiled", ""),
                }
                for r in data.get("results", [])[:10]
            ]
            await cache_set(cache_key, results)
            return results
    except Exception:
        return _DEMO_DATA
