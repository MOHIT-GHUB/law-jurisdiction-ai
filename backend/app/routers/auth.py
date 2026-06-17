"""
routers/auth.py — User signup and login endpoints.

ENDPOINTS:
  POST /auth/signup  — creates a new user account, returns JWT token
  POST /auth/login   — verifies credentials, returns JWT token

BOTH endpoints return a TokenResponse with:
  { access_token: "...", token_type: "bearer", username: "..." }

The frontend stores the token in localStorage and sends it as:
  Authorization: Bearer <token>
on every subsequent API request and WebSocket connection.

SECURITY NOTES:
  - Passwords are bcrypt-hashed (in hash_password) — plain text never stored
  - Username conflict is caught before insert (409 Conflict response)
  - Login uses constant-time comparison via passlib (no timing attacks)
  - The 'sub' claim in the JWT is the user's UUID, not username
    (avoids leaking username structure in the token payload)

TEAM — WHAT YOU MUST DO:
  1. This file is complete. Wire it into main.py:
       app.include_router(auth_router)
  2. Test both endpoints with Postman or the FastAPI /docs UI
  3. If you want email-based auth later, add an email field to
     SignupRequest and the User model. Ask an AI to do this.

AI USAGE NOTE:
  This file needs no changes. Safe to leave as-is for the hackathon.
"""

from app.database import get_db
from app.models.models import User
from app.schemas.auth import LoginRequest, SignupRequest, TokenResponse
from app.utils.auth import create_access_token, hash_password, verify_password
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def signup(body: SignupRequest, db: AsyncSession = Depends(get_db)):
    """
    Create a new user account.
    Validates username format and password length (done by SignupRequest validators).
    Returns a JWT token so the user is immediately logged in after signup.
    """
    # Check if username already exists (unique constraint would also catch this,
    # but checking first gives a cleaner error message)
    result = await db.execute(select(User).where(User.username == body.username))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Username already taken")

    user = User(username=body.username, password_hash=hash_password(body.password))
    db.add(user)
    await db.flush()  # flush assigns the UUID without full commit; get_db commits after

    token = create_access_token({"sub": user.id})
    return TokenResponse(access_token=token, username=user.username)


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    """
    Authenticate a user and return a JWT token.
    Returns 401 for both "user not found" and "wrong password" — intentionally
    vague to prevent username enumeration attacks.
    """
    result = await db.execute(select(User).where(User.username == body.username))
    user = result.scalar_one_or_none()

    # Both checks in one condition — same error message either way (security)
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token({"sub": user.id})
    return TokenResponse(access_token=token, username=user.username)
