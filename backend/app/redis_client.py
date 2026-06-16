"""
redis_client.py — Shared Redis connection + cache helpers.

WHY REDIS?
  The 3 research agents (federal, state, case law) call external APIs
  (Congress.gov, Cornell LII, CourtListener). Without caching:
    - Same query = 3 API calls every single time
    - Demo could fail if APIs are slow or rate-limit us
    - Adds 3-10 seconds of latency per conversation

  With Redis caching:
    - First query hits the API and stores result for 1 hour
    - Repeat queries for same case type return instantly
    - Demo is fast and reliable even on bad wifi

HOW THE CACHE KEY WORKS:
  make_cache_key("congress", query="employment discrimination", state="Texas")
  → SHA256 hash of sorted JSON → "congress:a3f9b1c2d4e5f6a7"
  Deterministic: same inputs always produce the same key.
  The hash keeps keys short even for long queries.

TEAM — WHAT YOU MUST DO:
  - Redis must be running (via docker-compose up)
  - No code changes needed here unless you want to add cache invalidation
  - To clear ALL cache during testing: redis-cli FLUSHALL

AI USAGE NOTE:
  This file is complete. No changes needed. Low priority.
"""

import hashlib
import json

import redis.asyncio as aioredis
from app.config import get_settings

settings = get_settings()

# Singleton connection — created once, reused across all requests
_redis_client = None


async def get_redis():
    """
    Lazy singleton: creates the Redis connection on first call, reuses it after.
    This avoids creating a new TCP connection on every request.
    """
    global _redis_client
    if _redis_client is None:
        _redis_client = await aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,  # automatically decode bytes → str
        )
    return _redis_client


def make_cache_key(prefix: str, **kwargs) -> str:
    """
    Build a short, deterministic Redis key from any keyword arguments.
    Example: make_cache_key("congress", query="civil rights", state="TX")
             → "congress:8f3a1b2c9d4e5f6a"
    """
    raw = json.dumps(kwargs, sort_keys=True)  # sort_keys = same dict always same string
    digest = hashlib.sha256(raw.encode()).hexdigest()[:16]  # first 16 chars of SHA256
    return f"{prefix}:{digest}"


async def cache_get(key: str):
    """
    Fetch a cached value. Returns parsed Python object or None if not cached.
    All cached values are stored as JSON strings in Redis.
    """
    redis = await get_redis()
    val = await redis.get(key)
    if val:
        return json.loads(val)
    return None


async def cache_set(key: str, value, ttl: int = None):
    """
    Store a value in Redis with a TTL (time-to-live) in seconds.
    Uses CACHE_TTL from config (default 1 hour) if ttl not specified.
    setex = SET + EXPIRE in one atomic operation.
    """
    redis = await get_redis()
    ttl = ttl or settings.CACHE_TTL
    await redis.setex(key, ttl, json.dumps(value))
