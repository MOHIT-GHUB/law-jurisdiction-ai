"""
models.py — Database table definitions (ORM models).

HOW IT WORKS:
  SQLAlchemy ORM = Python classes → database tables.
  Each attribute with Mapped[] becomes a column.
  'relationship()' lets you do user.conversations without writing SQL.

TABLE STRUCTURE (matches your architecture diagram):

  users
    id            UUID string (primary key, auto-generated)
    username      unique, indexed for fast lookups
    password_hash bcrypt hash — the plain password is NEVER stored
    created_at    auto-set on insert

  conversations
    id            UUID string
    user_id       foreign key → users.id
    state         enum: intake | active | completed
                  intake    = agent is still gathering info
                  active    = research is running / in progress
                  completed = full analysis delivered
    intake_summary   JSONB column: stores the structured {incident, location,
                     state, perpetrator, proof, date} after intake is done
    research_result  JSONB column: stores the full analysis result + case score
    title            auto-generated short title for the sidebar (e.g. "Employment dispute - TX")

  messages
    id               UUID string
    conversation_id  foreign key → conversations.id
    role             "user" | "assistant" | "system"
    content          full message text
    created_at       used for ordering in sliding window

TEAM — WHAT YOU MUST DO:
  - Run init_db() (called in main.py startup) to create tables
  - If you add a new column here, you MUST also migrate the DB
    (drop and recreate in dev, Alembic migration in prod)
  - JSONB is Postgres-specific. If you switch to SQLite for testing,
    change JSONB to JSON (from sqlalchemy import JSON)

AI USAGE NOTE:
  This file is solid. You can ask Cursor/ChatGPT to add a new column
  by saying "add an email column to the User model in models.py".
"""

import enum
import uuid
from datetime import datetime

from app.database import Base
from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship


class ConversationState(str, enum.Enum):
    """
    Tracks where a conversation is in the pipeline.
    str enum means it stores as a plain string in Postgres (not integer).
    """

    INTAKE = "intake"  # agent is collecting incident info
    ACTIVE = "active"  # research agents are running
    COMPLETED = "completed"  # analysis delivered, conversation archived


class User(Base):
    __tablename__ = "users"

    # UUID primary key — safer than auto-increment (no enumeration attacks)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)  # bcrypt hash only
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # ORM relationship: user.conversations gives all their conversations
    conversations: Mapped[list["Conversation"]] = relationship(
        "Conversation", back_populates="user"
    )


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Current stage in the agent pipeline
    state: Mapped[ConversationState] = mapped_column(
        SAEnum(ConversationState), default=ConversationState.INTAKE
    )

    # Structured intake data — set by intake_agent when [INTAKE_COMPLETE] fires
    # Example: {"incident": "...", "location": "Austin TX", "state": "Texas", ...}
    intake_summary: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Full research output from opinion_agent including case_strength_score
    # Saved here so users can review old analyses without re-running agents
    research_result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Short human-readable title shown in the sidebar
    # TEAM: set this in the WebSocket handler after intake completes
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="conversations")
    messages: Mapped[list["Message"]] = relationship(
        "Message", back_populates="conversation", order_by="Message.created_at"
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id: Mapped[str] = mapped_column(
        String, ForeignKey("conversations.id"), nullable=False
    )
    # "user" = human message, "assistant" = AI response, "system" = internal only
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    conversation: Mapped["Conversation"] = relationship("Conversation", back_populates="messages")
