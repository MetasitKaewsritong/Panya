import json
import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional

from app.chat.pipeline import answer_question, stream_answer_question
from app.routes_auth import get_current_user
from app.chat_db import (
    create_chat_session,
    get_chat_sessions,
    insert_chat_message,
    get_chat_messages,
    update_chat_session_title,
    delete_chat_session,
    update_chat_message_metadata,
)
from app.db import get_db_pool
from app.embed_logic import get_embedder
from app.ragas_eval import evaluate_response_async
from app.retriever import (
    PostgresVectorRetriever,
    EnhancedFlashrankRerankRetriever,
)
from app.utils import get_intent_llm, get_llm

router = APIRouter(prefix="/api/chat", tags=["chat"])
logger = logging.getLogger(__name__)


# =========================
# Schemas
# =========================

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[int] = None
    collection: str = "plcnext"
    use_page_images: Optional[bool] = None
    ragas_ground_truth: Optional[str] = None


class CreateSessionRequest(BaseModel):
    title: Optional[str] = None

class UpdateSessionRequest(BaseModel):
    title: str


def _require_services(db_pool, llm, embedder):
    if db_pool is None:
        raise HTTPException(status_code=503, detail="Database service is unavailable")
    if llm is None:
        raise HTTPException(status_code=503, detail="LLM service is unavailable")
    if embedder is None:
        raise HTTPException(status_code=503, detail="Embedder service is unavailable")


def _has_primary_ragas_scores(scores: dict | None) -> bool:
    if not isinstance(scores, dict):
        return False
    return any(
        scores.get(key) is not None
        for key in ("faithfulness", "answer_relevancy", "answer_match", "context_precision", "context_recall")
    )


def _queue_ragas_persistence(db_pool, message_id: int | None, ragas_request: dict | None) -> None:
    if not message_id or not ragas_request:
        return

    evaluate_response_async(
        question=ragas_request.get("question", ""),
        answer=ragas_request.get("answer", ""),
        contexts=ragas_request.get("contexts", []) or [],
        ground_truth=ragas_request.get("ground_truth"),
        on_complete=lambda scores: update_chat_message_metadata(
            db_pool,
            message_id,
            {
                "ragas": scores,
                "ragas_status": "complete" if _has_primary_ragas_scores(scores) else "error",
            },
        ),
        on_error=lambda _err: update_chat_message_metadata(
            db_pool,
            message_id,
            {
                "ragas_status": "error",
            },
        ),
    )


# =========================
# Chat (Send message)
# =========================

@router.post("")
def chat(
    payload: ChatRequest,
    current_user: dict = Depends(get_current_user),
):
    db_pool = get_db_pool()
    llm = get_llm()
    intent_llm = get_intent_llm()
    embedder = get_embedder()
    _require_services(db_pool, llm, embedder)

    message = (payload.message or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message must not be empty")

    # 1) Create session if not provided
    if payload.session_id is None:
        session_id = create_chat_session(
            db_pool=db_pool,
            user_id=current_user["id"],
            title=message[:50],
        )
        chat_history = []  # New session, no history
    else:
        session_id = payload.session_id
        # Fetch recent messages for context (last 10 messages = 5 exchanges)
        result = get_chat_messages(db_pool, session_id, current_user["id"])
        messages = result.get("items", []) if result else []
        chat_history = [{"role": m["role"], "content": m["content"]} for m in messages[-10:]]

    # 2) Save USER message
    insert_chat_message(
        db_pool=db_pool,
        session_id=session_id,
        role="user",
        content=message,
    )

    # 3) Ask LLM with chat history for context
    result = answer_question(
        question=message,
        db_pool=db_pool,
        llm=llm,
        intent_llm=intent_llm,
        embedder=embedder,
        collection=payload.collection,
        retriever_class=PostgresVectorRetriever,
        reranker_class=EnhancedFlashrankRerankRetriever,
        chat_history=chat_history,  # Pass conversation history
        use_page_images_override=payload.use_page_images,
        ragas_ground_truth=payload.ragas_ground_truth,
    )

    if "reply" not in result:
        raise HTTPException(status_code=500, detail="LLM did not return a reply")

    # 4) Save ASSISTANT message with metrics
    assistant_message_id = insert_chat_message(
        db_pool=db_pool,
        session_id=session_id,
        role="assistant",
        content=result["reply"],
        metadata={
            "collection": payload.collection,
            "processing_time": result.get("processing_time", 0.0),
            "retrieval_time": result.get("retrieval_time", 0.0),
            "llm_time": result.get("llm_time", 0.0),
            "context_count": result.get("context_count", 0),
            "sources": result.get("sources", []),
            "source_details": result.get("source_details", []),
            "ragas": result.get("ragas", {}),
            "ragas_status": result.get("ragas_status", "disabled"),
            "response_mode": result.get("response_mode", "text"),
            "requested_mode": result.get("requested_mode", "text"),
            "mode_fallback_reason": result.get("mode_fallback_reason"),
            "answer_support_status": result.get("answer_support_status"),
            "intent_query": result.get("intent_query"),
            "intent_source": result.get("intent_source"),
            "intent_details": result.get("intent_details", {}),
        },
    )
    _queue_ragas_persistence(db_pool, assistant_message_id, result.get("ragas_request"))

    return {
        "session_id": session_id,
        "reply": result["reply"],
        "processing_time": result.get("processing_time", 0.0),
        "llm_time": result.get("llm_time", 0.0),
        "sources": result.get("sources", []),
        "source_details": result.get("source_details", []),
        "ragas": result.get("ragas", {}),
        "response_mode": result.get("response_mode", "text"),
        "requested_mode": result.get("requested_mode", "text"),
        "mode_fallback_reason": result.get("mode_fallback_reason"),
        "answer_support_status": result.get("answer_support_status"),
        "collection": payload.collection,
        "intent_query": result.get("intent_query"),
        "intent_source": result.get("intent_source"),
        "intent_details": result.get("intent_details", {}),
        "metadata": {
            "collection": payload.collection,
            "retrieval_time": result.get("retrieval_time", 0.0),
            "llm_time": result.get("llm_time", 0.0),
            "context_count": result.get("context_count", 0),
            "max_score": result.get("max_score"),
            "source_details": result.get("source_details", []),
            "ragas": result.get("ragas", {}),
            "ragas_status": result.get("ragas_status", "disabled"),
            "response_mode": result.get("response_mode", "text"),
            "requested_mode": result.get("requested_mode", "text"),
            "mode_fallback_reason": result.get("mode_fallback_reason"),
            "answer_support_status": result.get("answer_support_status"),
            "intent_query": result.get("intent_query"),
            "intent_source": result.get("intent_source"),
            "intent_details": result.get("intent_details", {}),
        },
    }


# =========================
# Chat Sessions
# =========================

@router.get("/sessions")
def list_chat_sessions(
    current_user: dict = Depends(get_current_user),
):
    db_pool = get_db_pool()
    sessions = get_chat_sessions(db_pool, current_user["id"])

    return {
        "count": len(sessions),
        "items": sessions,
    }


@router.post("/sessions")
def create_session(
    payload: CreateSessionRequest,
    current_user: dict = Depends(get_current_user),
):
    db_pool = get_db_pool()
    session_id = create_chat_session(
        db_pool=db_pool,
        user_id=current_user["id"],
        title=payload.title,
    )

    return {
        "session_id": session_id
    }


@router.patch("/sessions/{session_id}")
def rename_chat_session(
    session_id: int,
    payload: UpdateSessionRequest,
    current_user: dict = Depends(get_current_user),
):
    db_pool = get_db_pool()

    updated = update_chat_session_title(
        db_pool=db_pool,
        session_id=session_id,
        user_id=current_user["id"],
        title=payload.title,
    )

    if not updated:
        raise HTTPException(status_code=404, detail="Chat session not found")

    return {
        "session_id": session_id,
        "title": payload.title,
    }


@router.delete("/sessions/{session_id}")
def delete_chat_session_route(
    session_id: int,
    current_user: dict = Depends(get_current_user),
):
    db_pool = get_db_pool()

    deleted = delete_chat_session(
        db_pool=db_pool,
        session_id=session_id,
        user_id=current_user["id"],
    )

    if not deleted:
        raise HTTPException(status_code=404, detail="Chat session not found")

    return {
        "success": True,
        "session_id": session_id,
    }


# =========================
# Chat Messages
# =========================

@router.get("/sessions/{session_id}")
def get_messages(
    session_id: int,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
):
    db_pool = get_db_pool()
    result = get_chat_messages(
        db_pool,
        session_id,
        current_user["id"],
        limit=limit,
        offset=offset,
    )

    if result is None:
        raise HTTPException(status_code=404, detail="Chat session not found")

    return {
        "session_id": session_id,
        "count": len(result["items"]),
        "total": result["total"],
        "has_more": result["has_more"],
        "items": result["items"],
    }


@router.post("/stream")
def chat_stream(
    payload: ChatRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Streaming chat endpoint (SSE).
    1. Yields JSON events (status, context, token, stats, done)
    2. Saves message to DB after generation
    """
    db_pool = get_db_pool()
    llm = get_llm()
    intent_llm = get_intent_llm()
    embedder = get_embedder()
    _require_services(db_pool, llm, embedder)

    message = (payload.message or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message must not be empty")

    # 1) Create session if needed
    if payload.session_id is None:
        session_id = create_chat_session(
            db_pool=db_pool,
            user_id=current_user["id"],
            title=message[:50],
        )
        chat_history = []
    else:
        session_id = payload.session_id
        result = get_chat_messages(db_pool, session_id, current_user["id"])
        messages = result.get("items", []) if result else []
        chat_history = [{"role": m["role"], "content": m["content"]} for m in messages[-10:]]

    # 2) Save USER message
    insert_chat_message(
        db_pool=db_pool,
        session_id=session_id,
        role="user",
        content=message,
    )

    # 3) Define generator wrapper to capture full reply for DB
    def iter_response():
        full_reply = ""
        
        # Generator from chatbot.py
        gen = stream_answer_question(
            question=message,
            db_pool=db_pool,
            llm=llm,
            intent_llm=intent_llm,
            embedder=embedder,
            collection=payload.collection,
            retriever_class=PostgresVectorRetriever,
            reranker_class=EnhancedFlashrankRerankRetriever,
            chat_history=chat_history,
            use_page_images_override=payload.use_page_images,
            ragas_ground_truth=payload.ragas_ground_truth,
        )

        # Consumes generator
        # Send session ID first
        yield json.dumps({"type": "session", "id": session_id}) + "\n"
        
        for event_str in gen:
            try:
                event = json.loads(event_str)
                if event["type"] == "token":
                    full_reply += event["text"]
                elif event["type"] == "stats":
                    stats = event["data"]
                    ragas_request = stats.pop("ragas_request", None)
                    # 4) Save ASSISTANT message
                    assistant_message_id = insert_chat_message(
                        db_pool=db_pool,
                        session_id=session_id,
                        role="assistant",
                        content=full_reply,
                        metadata={
                            "collection": payload.collection,
                            "processing_time": stats.get("processing_time"),
                            "retrieval_time": stats.get("retrieval_time"),
                            "llm_time": stats.get("llm_time"),
                            "context_count": stats.get("context_count", 0),
                            "sources": stats.get("sources", []),
                            "source_details": stats.get("source_details", []),
                            "ragas": stats.get("ragas", {}),
                            "ragas_status": stats.get("ragas_status", "disabled"),
                            "response_mode": stats.get("response_mode", "text"),
                            "requested_mode": stats.get("requested_mode", "text"),
                            "mode_fallback_reason": stats.get("mode_fallback_reason"),
                            "answer_support_status": stats.get("answer_support_status"),
                            "intent_query": stats.get("intent_query"),
                            "intent_source": stats.get("intent_source"),
                            "intent_details": stats.get("intent_details", {}),
                        },
                    )
                    _queue_ragas_persistence(db_pool, assistant_message_id, ragas_request)
                    yield json.dumps({"type": "stats", "data": stats}) + "\n"
                    continue
            except Exception:
                logger.debug("Failed to parse stream event for persistence", exc_info=True)

            yield event_str + "\n"

    return StreamingResponse(iter_response(), media_type="application/x-ndjson")
