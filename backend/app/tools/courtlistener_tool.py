"""
CourtListener tool — searches past court cases by keyword + state.
"""

import httpx
from app.config import get_settings
from app.redis_client import cache_get, cache_set, make_cache_key

settings = get_settings()

# v4 — the v3 search endpoint now returns HTTP 403.
CL_BASE = "https://www.courtlistener.com/api/rest/v4/search/"

CL_ROOT = "https://www.courtlistener.com"

_DEMO_DATA = [
    {
        "case_name": "Smith v. City of Dallas",
        "court": "N.D. Texas",
        "citation": "412 F. Supp. 3d 567",
        "summary": "Plaintiff won civil rights claim after unlawful search; awarded $150,000.",
        "url": "https://www.courtlistener.com/?q=smith+v+dallas",
        "date": "2019-04-12",
    },
    {
        "case_name": "Johnson v. Metro Transit Authority",
        "court": "5th Cir.",
        "citation": "998 F.3d 210",
        "summary": "Employment discrimination — plaintiff succeeded after showing pattern of bias.",
        "url": "https://www.courtlistener.com/?q=johnson+metro",
        "date": "2021-07-22",
    },
]


def _absolute(url: str) -> str:
    """CourtListener's `absolute_url` is a site-relative path — make it clickable."""
    if url.startswith("/"):
        return f"{CL_ROOT}{url}"
    return url


async def search_courtlistener(query: str, state: str = "") -> list[dict]:
    if settings.DEMO_MODE:
        return _DEMO_DATA

    cache_key = make_cache_key("cl", query=query, state=state)
    cached = await cache_get(cache_key)
    if cached:
        return cached

    # Bias results toward the user's state without over-filtering.
    params = {
        "q": f"{query} {state}".strip(),
        "type": "o",  # opinions
        "order_by": "score desc",
    }
    headers = {}
    if settings.COURTLISTENER_API_KEY:
        headers["Authorization"] = f"Token {settings.COURTLISTENER_API_KEY}"

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(CL_BASE, params=params, headers=headers)
            resp.raise_for_status()
            results, seen = [], set()
            for r in resp.json().get("results", [])[:20]:
                case = _parse_result(r)
                # Dedup on the opinion cluster (same case can appear under several
                # captions); fall back to the case name.
                key = r.get("cluster_id") or r.get("docket_id") or case["case_name"].strip().lower()
                if not case["case_name"] or key in seen:
                    continue
                seen.add(key)
                results.append(case)
                if len(results) >= 10:
                    break
            if not results:
                return _DEMO_DATA
            await cache_set(cache_key, results)
            return results
    except Exception:
        return _DEMO_DATA


def _parse_result(r: dict) -> dict:
    """Map a CourtListener v4 search result to our normalized case shape."""
    citations = r.get("citation") or []
    opinions = r.get("opinions") or []
    snippet = (opinions[0].get("snippet") if opinions else "") or r.get("syllabus") or ""
    return {
        "case_name": r.get("caseName", ""),
        "court": r.get("court") or r.get("court_citation_string", ""),
        "citation": ", ".join(citations) if isinstance(citations, list) else str(citations),
        "summary": snippet,
        "url": _absolute(r.get("absolute_url", "")),
        "date": r.get("dateFiled", ""),
    }
