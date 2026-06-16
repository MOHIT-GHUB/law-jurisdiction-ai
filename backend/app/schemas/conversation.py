"""
schemas/conversation.py — Pydantic response models for conversations.

WHY THESE EXIST:
  The ORM Conversation model has a relationship to messages (SQLAlchemy list).
  We can't return raw ORM objects from FastAPI — they need to be serialized.
  These Pydantic models define exactly what fields the API returns.

MODEL HIERARCHY:
  ConversationOut          — base: id, title, state, timestamps, summaries
  ConversationWithMessages — extends ConversationOut + full messages list
  MessageOut               — individual message shape

  GET /conversations/      → returns list[ConversationOut] (no messages, fast)
  GET /conversations/{id}  → returns ConversationWithMessages (includes messages)

  This separation is intentional: loading messages for every conversation
  in the sidebar list would be very slow. We only load them when a specific
  conversation is opened.

model_config = {"from_attributes": True}:
  Tells Pydantic to read data from ORM object attributes (not just dicts).
  Required for converting SQLAlchemy ORM objects to Pydantic models.
  Without this, FastAPI throws a validation error on every response.

TEAM — WHAT YOU MUST DO:
  1. This file is complete for the current use case.
  2. If you add new fields to the Conversation model, add them here too
     if you want them exposed in the API response.
  3. research_result is intentionally included — the frontend uses
     case_strength_score from it to render the progress bar.

AI USAGE NOTE:
  Stable file. No changes needed unless you add new DB columns.
"""

from datetime import datetime

from pydantic import BaseModel


class ConversationOut(BaseModel):
    """
    Lightweight conversation summary for the sidebar list.
    Does not include messages (too heavy to load for every item).
    """

    id: str
    title: str | None  # short label like "Employment case - Austin TX"
    state: str  # "intake" | "active" | "completed"
    created_at: datetime
    intake_summary: dict | None = None  # the structured case info
    research_result: dict | None = None  # includes case_strength_score

    model_config = {"from_attributes": True}  # enable ORM → Pydantic conversion


class MessageOut(BaseModel):
    """Individual chat message shape returned by the API."""

    id: str
    role: str  # "user" | "assistant"
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ConversationWithMessages(ConversationOut):
    """
    Full conversation detail including all messages.
    Used when user opens a past conversation to continue or review it.
    """

    messages: list[MessageOut] = []  # empty list default (no messages yet)
