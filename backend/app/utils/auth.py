"""
utils/auth.py — Password hashing and JWT token utilities.

HOW AUTH FLOW WORKS:
  1. User POSTs /auth/signup or /auth/login with username + password
  2. We verify/create user in DB, then call create_access_token()
  3. Token is returned to the frontend and stored in localStorage
  4. Every subsequent request includes: Authorization: Bearer <token>
  5. get_current_user() is a FastAPI Depends() — it decodes the token,
     looks up the user in DB, and injects the User object into the route

JWT PAYLOAD STRUCTURE:
  { "sub": "<user_uuid>", "exp": <unix_timestamp> }
  'sub' (subject) = user's UUID. We look them up by this on every request.
  'exp' = expiry time. jose library auto-rejects expired tokens.

WHY BCRYPT?
  bcrypt is a slow hash — intentionally. Even if someone gets your DB,
  they can't brute-force all passwords quickly. NEVER use md5/sha256 for passwords.

TEAM — WHAT YOU MUST DO:
  - SECRET_KEY in .env MUST be changed before demo. See config.py.
  - Token expiry is 7 days (good for hackathon). Adjust if needed.
  - If you want logout functionality: implement a Redis token blacklist
    (store revoked token JTI in Redis until expiry). Low priority for hackathon.

AI USAGE NOTE:
  This file is complete and correct. No changes needed.
  If you want refresh tokens, ask an AI to add a /auth/refresh endpoint.
"""

from datetime import datetime, timedelta

from app.config import get_settings
from app.database import get_db
from app.models.models import User
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

settings = get_settings()

# CryptContext manages hashing scheme. 'deprecated="auto"' means old hashes
# are automatically re-hashed to the current scheme on next login.
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# HTTPBearer extracts the token from the Authorization header automatically.
# It returns 403 if the header is missing entirely.
bearer_scheme = HTTPBearer()


def hash_password(password: str) -> str:
    """Hash a plain-text password using bcrypt. Used at signup."""
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plain password against a stored bcrypt hash. Used at login."""
    return pwd_context.verify(plain, hashed)


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """
    Create a signed JWT token.
    'data' should contain {"sub": user_id}.
    Returns the encoded token string to send to the frontend.
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode["exp"] = expire
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    FastAPI dependency — inject into any protected route:
        async def my_route(current_user: User = Depends(get_current_user)):

    Steps:
      1. Extract token from Authorization: Bearer <token> header
      2. Decode and validate JWT signature + expiry
      3. Look up user by 'sub' (user_id) in database
      4. Return User ORM object — available directly in the route

    Raises HTTP 401 if token is invalid, expired, or user not found.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            credentials.credentials, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception from None

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise credentials_exception
    return user
