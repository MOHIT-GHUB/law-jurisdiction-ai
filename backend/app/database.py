"""
database.py — Async PostgreSQL connection via SQLAlchemy.

HOW IT WORKS:
  1. create_async_engine: creates a connection pool to Postgres
     pool_pre_ping=True  → tests connection before use (handles dropped connections)
     pool_size=10        → keep 10 connections open at all times
     max_overflow=20     → allow up to 20 extra connections under heavy load

  2. AsyncSessionLocal: a session factory. Every request gets its own
     session (like a unit of work). SQLAlchemy tracks all changes in the
     session and commits them together.

  3. Base: all models (User, Conversation, Message) inherit from this.
     SQLAlchemy uses it to discover tables when running init_db().

  4. get_db(): FastAPI dependency — inject into any route with Depends(get_db)
     Automatically commits on success, rolls back on error, always closes.

  5. init_db(): called ONCE at app startup to CREATE all tables if they
     don't exist. Safe to call multiple times (CREATE TABLE IF NOT EXISTS).

TEAM — WHAT YOU MUST DO:
  - Ensure Postgres is running (via docker-compose up)
  - DATABASE_URL in .env must match your docker-compose credentials
  - For schema changes: add Alembic migrations (AI can generate these)
    DO NOT rely on init_db() in production — use Alembic instead

TEAM — WHERE TO ADD EFFORT:
  - If you change models.py, you must also update the DB schema.
    Either drop+recreate (dev only) or write an Alembic migration.

AI USAGE NOTE:
  To generate Alembic migration: paste the old and new model class to
  ChatGPT and ask "write an Alembic upgrade/downgrade migration for this change".
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.config import get_settings

settings = get_settings()

# Connection pool — shared across the entire application lifetime
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,   # logs every SQL query when DEBUG=True — useful for debugging
    pool_pre_ping=True,    # verify connection alive before using (important for long-running apps)
    pool_size=10,          # persistent connections kept warm
    max_overflow=20,       # burst capacity for high traffic
)

# Session factory — each call to AsyncSessionLocal() gives a fresh session
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,  # keep ORM objects usable after commit (important for returning data)
)


class Base(DeclarativeBase):
    """Parent class for all ORM models. Do not put logic here."""
    pass


async def get_db():
    """
    FastAPI dependency. Usage in a route:
        async def my_route(db: AsyncSession = Depends(get_db)):

    The 'yield' makes this a context manager:
    - Code before yield: setup (open session)
    - Route runs here
    - Code after yield: teardown (commit or rollback, then close)
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()    # persist all changes made during this request
        except Exception:
            await session.rollback()  # undo partial changes on any error
            raise
        finally:
            await session.close()     # always return connection to the pool


async def init_db():
    """
    Called once at startup (in main.py lifespan).
    Creates all tables defined in models.py if they don't already exist.
    TEAM: For production, replace with Alembic. For hackathon, this is fine.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
