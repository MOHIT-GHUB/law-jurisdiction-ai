"""
Lawyer Finder tool — uses Google Maps Places API to find
licensed attorneys near the user's location by specialty.
"""
import httpx
from app.config import get_settings
from app.redis_client import cache_get, cache_set, make_cache_key

settings = get_settings()

PLACES_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"

_DEMO_DATA = [
    {
        "name": "Smith & Associates Law Firm",
        "address": "123 Main St, Austin, TX 78701",
        "phone": "(512) 555-0101",
        "rating": 4.8,
        "specialty": "Employment & Civil Rights",
        "url": "https://maps.google.com",
    },
    {
        "name": "Texas Legal Aid Center",
        "address": "456 Congress Ave, Austin, TX 78701",
        "phone": "(512) 555-0202",
        "rating": 4.5,
        "specialty": "Civil Rights",
        "url": "https://maps.google.com",
    },
    {
        "name": "Garcia Law Group",
        "address": "789 6th St, Austin, TX 78702",
        "phone": "(512) 555-0303",
        "rating": 4.7,
        "specialty": "Personal Injury & Civil Litigation",
        "url": "https://maps.google.com",
    },
]


async def find_lawyers_near(location: str, specialty: str, state: str = "") -> list[dict]:
    if settings.DEMO_MODE or not settings.GOOGLE_MAPS_API_KEY:
        return _DEMO_DATA

    cache_key = make_cache_key("lawyers", location=location, specialty=specialty)
    cached = await cache_get(cache_key)
    if cached:
        return cached

    query = f"{specialty} near {location} {state}"

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                PLACES_URL,
                params={"query": query, "key": settings.GOOGLE_MAPS_API_KEY, "type": "lawyer"},
            )
            resp.raise_for_status()
            data = resp.json()
            results = [
                {
                    "name": p.get("name", ""),
                    "address": p.get("formatted_address", ""),
                    "rating": p.get("rating", 0),
                    "url": f"https://maps.google.com/?q={p.get('name', '')}",
                }
                for p in data.get("results", [])[:10]
            ]
            await cache_set(cache_key, results, ttl=86400)  # 24h cache for lawyer data
            return results
    except Exception:
        return _DEMO_DATA
