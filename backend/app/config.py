"""
config.py — Single source of truth for ALL environment configuration.

HOW IT WORKS:
  - Pydantic reads every value from the .env file (copy .env.example → .env)
  - @lru_cache means Settings() is only built ONCE — cheap to call anywhere
  - All defaults are safe for local dev; override in .env for production

TEAM — WHAT YOU MUST DO:
  1. Copy .env.example to .env and fill in your real API keys
  2. Generate a strong SECRET_KEY:  python -c "import secrets; print(secrets.token_hex(32))"
  3. Before hackathon demo, set DEMO_MODE=True in .env so the app
     never crashes if Congress.gov / CourtListener are slow or rate-limited
  4. Never commit your .env file — it's in .gitignore

AI USAGE NOTE:
  You can ask ChatGPT/Claude to generate a .env.example file from this class.
  Just paste the class and say "make me a .env.example with placeholder values".
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── App identity ───────────────────────────────────────────────────────────
    APP_NAME: str = "LexAI - US Jurisdiction Assistant"
    DEBUG: bool = False

    # HACKATHON CRITICAL: flip to True before your live demo
    # When True, all external API calls return realistic mock data instead
    # of hitting real APIs. This prevents crashes if APIs are slow/rate-limited.
    DEMO_MODE: bool = False

    # ── Database (PostgreSQL) ──────────────────────────────────────────────────
    # Format: postgresql+asyncpg://USER:PASSWORD@HOST:PORT/DBNAME
    # asyncpg = async Postgres driver (required for FastAPI async routes)
    # TEAM: change user/password/dbname to match your docker-compose.yml
    DATABASE_URL: str = "postgresql+asyncpg://lexai:lexai@localhost:5432/lexai"

    # ── Redis (caching layer) ──────────────────────────────────────────────────
    # Redis stores API responses so we don't call Congress.gov 100 times
    # for the same query. Massive speed improvement + avoids rate limits.
    REDIS_URL: str = "redis://localhost:6379"
    CACHE_TTL: int = 3600  # seconds — 1 hour cache per unique query

    # ── JWT Authentication ─────────────────────────────────────────────────────
    # SECRET_KEY signs every JWT token. If someone gets this, they can forge tokens.
    # TEAM: MUST generate a real random key before demo/deployment
    # Run: python -c "import secrets; print(secrets.token_hex(32))"
    SECRET_KEY: str = "change-this-in-production-use-openssl-rand-hex-32"
    ALGORITHM: str = "HS256"  # standard JWT signing algorithm
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # tokens last 7 days

    # ── LLM (OpenAI) ──────────────────────────────────────────────────────────
    # All agents use this. gpt-5.1 is the strongest model that works with the
    # pinned langchain-openai; drop to gpt-4.1-mini to cut costs during testing.
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-5.1"
    OPENAI_BASE_URL: str = ""

    # ── External Legal APIs ───────────────────────────────────────────────────
    # Congress.gov: free API key at https://api.congress.gov/sign-up/
    # CourtListener: free at https://www.courtlistener.com/api/ — optional, works without key
    # Google Maps: needed ONLY for the lawyer-finder referral feature
    CONGRESS_API_KEY: str = ""
    COURTLISTENER_API_KEY: str = ""
    GOOGLE_MAPS_API_KEY: str = ""

    # ── Context window ────────────────────────────────────────────────────────
    # We only send the last 20 messages to the LLM (sliding window).
    # This prevents the token count from growing infinitely in long conversations,
    # which would make requests slow and expensive.
    MAX_CONTEXT_MESSAGES: int = 20

    # Pydantic v2 style config (replaces deprecated inner class Config)
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    """
    Returns a cached singleton Settings instance.
    Use: from app.config import get_settings; settings = get_settings()
    Call get_settings.cache_clear() in tests to reset between test cases.
    """
    return Settings()
