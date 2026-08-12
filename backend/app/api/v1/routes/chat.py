"""`POST /chat` — single-turn. No conversation_id, no streaming (PLAN.md Phase 5).

Validates and calls a service. No business logic here (CLAUDE.md 4.2).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.api.deps import AppSettings, DbSession
from app.core.exceptions import PipelineNotFound
from app.core.logging import get_logger
from app.schemas.chat import ChatRequest, ChatResponse
from app.services import chat_service

router = APIRouter(tags=["chat"])
log = get_logger(__name__)


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, session: DbSession, settings: AppSettings) -> ChatResponse:
    """Answer one question against the corpus, with citations.

    A refusal is a 200, not a 404: "no information found in the documents" is a successful,
    correct answer and the single most important one this system produces (ADR-0006). The
    client reads `refused`.
    """
    question = request.question.strip()
    if not question:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="question must not be blank",
        )

    try:
        return await chat_service.answer_question(session, question, settings=settings)
    except PipelineNotFound as exc:
        # Misconfiguration, not bad input: PIPELINE_NAME names a pipeline that is not
        # registered, so every request will fail the same way until .env is fixed.
        log.error("chat_pipeline_not_found", pipeline=settings.pipeline_name, error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc
    except Exception as exc:
        # The provider is the likeliest failure: a timeout, a 429, or a retired model
        # (ADR-0007). 502 says "the upstream failed", which is what actually happened.
        log.error("chat_failed", error=str(exc), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"answering failed: {type(exc).__name__}",
        ) from exc
