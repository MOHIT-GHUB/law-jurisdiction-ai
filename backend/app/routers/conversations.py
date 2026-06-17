"""
routers/conversations.py — REST endpoints for conversation history.

ENDPOINTS:
  GET    /conversations/              — list all conversations for logged-in user
  GET    /conversations/{id}          — get a conversation + all its messages
  GET    /conversations/{id}/export-pdf — download full analysis as PDF
  DELETE /conversations/{id}          — delete a conversation

All endpoints require a valid JWT token (Depends(get_current_user)).
A user can only access their OWN conversations (user_id check in every query).

PDF EXPORT — WHY IT'S A WIN FACTOR:
  The user can download a professional PDF of their case analysis.
  They can physically take this to a lawyer's office.
  This makes the product feel REAL and useful, not just a chatbot.
  Judges notice when a product has a tangible, real-world deliverable.

TEAM — WHAT YOU MUST DO:
  1. Create utils/pdf_export.py with a generate_pdf(conversation) function.
     This file is currently MISSING — the import will fail until you create it.
     Ask an AI: "write a generate_pdf function using reportlab that formats
     a conversation's intake_summary, opinion, case_strength_score, and
     referred_lawyers into a clean PDF"
  2. Wire this router into main.py:
       app.include_router(conversations_router)
  3. Test the PDF export — it's a demo moment, make it look polished

TEAM — MISSING FILES THAT WILL CAUSE IMPORT ERRORS:
  - app/utils/pdf_export.py (generate_pdf function) — MUST CREATE
  - app/main.py (FastAPI app entry point) — MUST CREATE
  - app/routers/chat.py (WebSocket handler) — MUST CREATE

AI USAGE NOTE:
  PDF generation is boilerplate. Paste the Conversation model schema to
  ChatGPT and ask for a reportlab PDF generator. Should take < 30 minutes.
"""

from app.database import get_db
from app.models.models import Conversation, User
from app.schemas.conversation import ConversationOut, ConversationWithMessages
from app.utils.auth import get_current_user
from app.utils.pdf_export import generate_pdf  # TEAM: create this file first!
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("/", response_model=list[ConversationOut])
async def list_conversations(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns all conversations for the current user, newest first.
    Used to populate the sidebar in the frontend (like ChatGPT's history panel).
    """
    result = await db.execute(
        select(Conversation)
        .where(Conversation.user_id == current_user.id)
        .order_by(Conversation.created_at.desc())
    )
    return result.scalars().all()


@router.get("/{conversation_id}", response_model=ConversationWithMessages)
async def get_conversation(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Fetch a single conversation with all messages.
    Used when the user clicks on a past conversation in the sidebar.
    The user_id check ensures users can only read their own conversations.
    """
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == current_user.id,  # security: own conversations only
        )
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv


@router.get("/{conversation_id}/export-pdf")
async def export_conversation_pdf(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Export the full legal analysis as a downloadable PDF.

    The PDF should contain:
    - User's case summary (intake_summary)
    - Case Strength Score with visual bar
    - Federal law findings
    - State law findings
    - Relevant past cases
    - Full opinion text
    - Recommended next steps
    - Referred attorney list
    - Legal disclaimer

    TEAM: The quality of this PDF is a demo moment. Make it look professional.
    Use reportlab or weasyprint. WeasyPrint can render HTML — easier to style.
    """
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == current_user.id,
        )
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    from fastapi.responses import Response

    pdf_bytes = generate_pdf(conv)  # TEAM: implement this in utils/pdf_export.py
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=lexai-report-{conversation_id[:8]}.pdf"
        },
    )


@router.delete("/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a conversation. Only the owner can delete it (user_id check)."""
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == current_user.id,
        )
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    await db.delete(conv)
