"""
Lawyer Finder tool — points the user at ways to find an attorney.

Rather than a single static list, this returns DYNAMIC, clickable resources built
from the user's location + case specialty. These work with NO API key:
  - a Google Maps *search* deep-link for "<specialty> near <location>"
  - a Justia practice-area directory for the user's state
  - the state-bar / ABA lawyer referral service (ethics-vetted, often free intake)
  - legal aid (LawHelp.org) for income-qualified users

If a Google Places API key is configured, we additionally enrich with named nearby
firms (ratings + addresses). See referral_agent.py for how specialty is chosen
(now driven by the classification bucket).
"""

import re
import urllib.parse

import httpx
from app.config import get_settings
from app.redis_client import cache_get, cache_set, make_cache_key

settings = get_settings()

PLACES_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"

# Specialty keyword → Justia practice-area URL slug.
_JUSTIA_PRACTICE = {
    "employment": "employment-law",
    "housing": "landlord-tenant-law",
    "tenant": "landlord-tenant-law",
    "consumer": "consumer-law",
    "personal injury": "personal-injury",
    "civil rights": "civil-rights",
}


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def _practice_slug(specialty: str) -> str:
    s = specialty.lower()
    for keyword, slug in _JUSTIA_PRACTICE.items():
        if keyword in s:
            return slug
    return ""


def _justia_url(specialty: str, state: str) -> str:
    practice, state_slug = _practice_slug(specialty), _slug(state)
    if practice and state_slug:
        return f"https://www.justia.com/lawyers/{practice}/{state_slug}"
    if practice:
        return f"https://www.justia.com/lawyers/{practice}"
    if state_slug:
        return f"https://www.justia.com/lawyers/{state_slug}"
    return "https://www.justia.com/lawyers"


def referral_resources(location: str, specialty: str, state: str = "") -> list[dict]:
    """Dynamic, no-API attorney-finding resources tailored to location + specialty."""
    where = location or state or "your area"
    maps_query = urllib.parse.quote_plus(f"{specialty} near {location} {state}".strip())
    return [
        {
            "name": "Find nearby attorneys on Google Maps",
            "address": where,
            "phone": "",
            "rating": None,
            "specialty": specialty,
            "url": f"https://www.google.com/maps/search/?api=1&query={maps_query}",
            "kind": "directory",
        },
        {
            "name": f"Justia — {specialty} directory",
            "address": state or "United States",
            "phone": "",
            "rating": None,
            "specialty": specialty,
            "url": _justia_url(specialty, state),
            "kind": "directory",
        },
        {
            "name": "State bar lawyer referral service",
            "address": state or "United States",
            "phone": "",
            "rating": None,
            "specialty": "Bar-vetted referral (often free intake)",
            "url": "https://www.americanbar.org/groups/legal_services/flh-home/",
            "kind": "referral_service",
        },
        {
            "name": "Free / low-cost legal aid (LawHelp.org)",
            "address": state or "United States",
            "phone": "",
            "rating": None,
            "specialty": "Legal aid for income-qualified users",
            "url": "https://www.lawhelp.org/",
            "kind": "legal_aid",
        },
    ]


async def find_lawyers_near(location: str, specialty: str, state: str = "") -> list[dict]:
    resources = referral_resources(location, specialty, state)

    # The dynamic resources above already give the user useful, real links with no
    # network call. Only reach out to Google Places (for named firms) when a key
    # is set and we're not in demo mode.
    if settings.DEMO_MODE or not settings.GOOGLE_MAPS_API_KEY:
        return resources

    cache_key = make_cache_key("lawyers", location=location, specialty=specialty)
    cached = await cache_get(cache_key)
    if cached:
        return cached

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                PLACES_URL,
                params={
                    "query": f"{specialty} near {location} {state}",
                    "key": settings.GOOGLE_MAPS_API_KEY,
                    "type": "lawyer",
                },
            )
            resp.raise_for_status()
            firms = [
                {
                    "name": p.get("name", ""),
                    "address": p.get("formatted_address", ""),
                    "phone": "",
                    "rating": p.get("rating"),
                    "specialty": specialty,
                    "url": "https://www.google.com/maps/search/?api=1&query="
                    + urllib.parse.quote_plus(p.get("name", "")),
                    "kind": "firm",
                }
                for p in resp.json().get("results", [])[:8]
            ]
            result = resources + firms
            await cache_set(cache_key, result, ttl=86400)  # 24h — firms don't move
            return result
    except Exception:
        return resources
