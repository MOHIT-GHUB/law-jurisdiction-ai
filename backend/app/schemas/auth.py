"""
schemas/auth.py — Pydantic request/response models for authentication.

WHAT ARE SCHEMAS?
  Pydantic models validate incoming request data and shape outgoing responses.
  FastAPI automatically:
    - Parses JSON request body into these models
    - Returns 422 Unprocessable Entity if validation fails
    - Generates OpenAPI documentation from these types

WHY SEPARATE FROM ORM MODELS?
  ORM models (models.py) define database tables.
  Schemas define API contract (what goes in/out of HTTP endpoints).
  They're kept separate because:
    - You never want to expose password_hash in an API response
    - Request shapes often differ from DB shapes
    - Cleaner separation of concerns

TEAM — WHAT YOU MUST DO:
  1. This file is complete. No changes needed.
  2. If you add an email field to User, add it here too.
  3. TokenResponse.username is included so the frontend can display
     the username immediately after login without a second API call.

AI USAGE NOTE:
  This file is stable. Low priority for changes.
"""
from pydantic import BaseModel, field_validator
import re


class SignupRequest(BaseModel):
    """
    Validates the signup request body.
    Pydantic runs field_validators before the route handler runs.
    """
    username: str
    password: str

    @field_validator("username")
    @classmethod
    def username_valid(cls, v):
        # Only allow alphanumeric + underscore, 3-50 chars
        # Prevents SQL injection via username, XSS, and weird display issues
        if not re.match(r"^[a-zA-Z0-9_]{3,50}$", v):
            raise ValueError("Username must be 3-50 alphanumeric characters or underscores")
        return v

    @field_validator("password")
    @classmethod
    def password_strong(cls, v):
        # Minimum 8 chars. TEAM: increase to 12 + require special char for production.
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v


class LoginRequest(BaseModel):
    """Simple login body. No validation needed — wrong credentials handled in route."""
    username: str
    password: str


class TokenResponse(BaseModel):
    """
    What the frontend receives after successful signup or login.
    Store access_token in localStorage and send as: Authorization: Bearer <token>
    """
    access_token: str
    token_type: str = "bearer"  # always "bearer" for JWT
    username: str               # so frontend knows who is logged in immediately
