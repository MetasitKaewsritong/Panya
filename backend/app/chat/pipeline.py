import json
import logging
import os
import re
import time
from typing import List

from langchain_core.messages import HumanMessage
from langchain_core.output_parsers import StrOutputParser

from app.chat.config import USE_PAGE_IMAGES, VISION_STRICT_MODE
from app.chat.intent_extractor import resolve_question_intent
from app.chat.logging_utils import log_chat_request
from app.chat.prompts import build_enhanced_prompt, build_no_context_prompt, build_vision_prompt
from app.chat.scoring import get_doc_score
from app.chat.selection import select_context_docs
from app.ragas_eval import (
    ENABLE_BACKGROUND_RAGAS,
    ENABLE_RAGAS,
    calculate_answer_match,
    empty_ragas_scores,
    evaluate_response_async,
    resolve_ground_truth,
)
from app.chat.text_utils import (
    build_openai_compatible_image_parts,
    call_llm_with_retry,
    extract_text_from_llm_response,
    format_chat_history,
    is_not_found_response,
)

logger = logging.getLogger(__name__)

_MANUAL_SCOPE_RE = re.compile(
    r"^\s*(?:for|in|from)\s+(.{1,180}?)\s+manual\s*:\s*",
    re.IGNORECASE,
)
_TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)
_SCOPE_STOPWORDS = {
    "for",
    "manual",
    "the",
    "and",
    "or",
    "guide",
    "user",
    "series",
}


def _extract_manual_scope(question: str) -> str | None:
    match = _MANUAL_SCOPE_RE.match(question or "")
    if not match:
        return None
    scope = (match.group(1) or "").strip()
    return scope or None


def _normalize_tokens(text: str) -> set[str]:
    tokens = {
        token.lower()
        for token in _TOKEN_RE.findall((text or "").lower())
        if token and token not in _SCOPE_STOPWORDS
    }
    return tokens


def _source_matches_scope(scope: str, source: str) -> bool:
    scope_norm = " ".join((scope or "").lower().split())
    source_norm = " ".join((source or "").lower().split())
    if not scope_norm or not source_norm:
        return False

    # Explicit manual families first.
    if "a series" in scope_norm:
        return "a series" in source_norm
    if any(token in scope_norm for token in ("fx0n", "fx", "485adp", "melsec-f")):
        return "fx" in source_norm or "melsec-f" in source_norm or "485adp" in source_norm

    scope_tokens = _normalize_tokens(scope_norm)
    source_tokens = _normalize_tokens(source_norm)
    if not scope_tokens or not source_tokens:
        return False

    overlap = scope_tokens.intersection(source_tokens)
    return len(overlap) >= 1


def _filter_retrieved_docs_by_scope(question: str, docs: List) -> List:
    scope = _extract_manual_scope(question)
    if not scope or not docs:
        return docs

    matched = []
    for doc in docs:
        source = (doc.metadata or {}).get("source", "")
        if _source_matches_scope(scope, source):
            matched.append(doc)

    if matched:
        logger.info(
            "[SCOPE_FILTER] scope='%s' matched=%d/%d",
            scope,
            len(matched),
            len(docs),
        )
        return matched

    logger.warning(
        "[SCOPE_FILTER] scope='%s' matched=0/%d; keeping unfiltered retrieval",
        scope,
        len(docs),
    )
    return docs


def _has_primary_ragas_scores(scores: dict) -> bool:
    if not isinstance(scores, dict):
        return False
    return any(
        scores.get(key) is not None
        for key in ("faithfulness", "answer_relevancy", "answer_match", "context_precision", "context_recall")
    )


def _build_intent_only_result(
    reply: str,
    *,
    requested_mode: str = "text",
    intent_query: str = "",
    intent_source: str = "",
    intent_details: dict | None = None,
) -> dict:
    return {
        "reply": reply,
        "processing_time": 0.0,
        "retrieval_time": 0.0,
        "rerank_time": 0.0,
        "llm_time": 0.0,
        "context_count": 0,
        "max_score": None,
        "sources": [],
        "source_details": [],
        "ragas": empty_ragas_scores(),
        "ragas_status": "disabled",
        "response_mode": "unresolved",
        "requested_mode": requested_mode,
        "mode_fallback_reason": "intent_unresolved",
        "answer_support_status": "unsupported",
        "intent_query": intent_query,
        "intent_source": intent_source,
        "intent_details": intent_details or {},
        "ragas_request": None,
    }


def _format_intent_context(intent_details: dict | None) -> str:
    details = intent_details or {}
    lines = []

    brand = details.get("matched_brand") or details.get("brand")
    model = details.get("matched_model_subbrand") or details.get("model_input")
    intent = details.get("intent")
    topic = details.get("topic")
    retrieval_query = details.get("normalized_query")

    if brand:
        lines.append(f"Brand: {brand}")
    if model:
        lines.append(f"Model/Subbrand: {model}")
    if intent:
        lines.append(f"Intent: {intent}")
    if topic:
        lines.append(f"Topic: {topic}")
    if retrieval_query:
        lines.append(f"Retrieval Query: {retrieval_query}")

    if not lines:
        return "No structured intent was extracted."
    return "\n".join(lines)


def _determine_answer_support_status(reply: str, selected_docs: List, *, intent_ok: bool = True) -> str:
    if not intent_ok:
        return "unsupported"
    if not selected_docs:
        return "unsupported"
    if not (reply or "").strip():
        return "unsupported"
    if is_not_found_response(reply):
        return "unsupported"
    return "supported"


def answer_question(
    question: str,
    db_pool,
    llm,
    intent_llm,
    embedder,
    collection: str,
    retriever_class,
    reranker_class,
    chat_history: List[dict] = None,
    use_page_images_override: bool | None = None,
    ragas_ground_truth: str | None = None,
) -> dict:
    raw_question = (question or "").strip()
    if not raw_question:
        return {"reply": "Please enter a question."}
    requested_mode = "vision" if bool(use_page_images_override) else "text"

    t0 = time.perf_counter()
    history_section = format_chat_history(chat_history or [], max_messages=5)
    intent_resolution = resolve_question_intent(
        raw_question,
        db_pool=db_pool,
        collection=collection,
        intent_llm=intent_llm,
        history_section=history_section,
    )
    processed_msg = intent_resolution.normalized_query
    intent_source = intent_resolution.source
    if intent_resolution.status != "ok":
        return _build_intent_only_result(
            intent_resolution.reply or "I don't understand the question, could you be more specific?",
            requested_mode=requested_mode,
            intent_query=processed_msg,
            intent_source=intent_source,
            intent_details=intent_resolution.to_metadata(),
        )
    logger.info("[INTENT] source=%s query='%s'", intent_source, processed_msg[:200])
    logger.info(
        "[INTENT_SCOPE] brand_filters=%s model_filters=%s intent=%s",
        intent_resolution.brand_filters,
        intent_resolution.model_subbrand_filters,
        intent_resolution.intent,
    )

    t_retrieval_start = time.perf_counter()
    base_retriever = retriever_class(
        connection_pool=db_pool,
        embedder=embedder,
        collection=collection,
        brand_filters=intent_resolution.brand_filters,
        model_subbrand_filters=intent_resolution.model_subbrand_filters,
    )
    reranker = reranker_class(base_retriever=base_retriever)
    retrieved_docs = reranker.invoke(processed_msg) or []
    retrieved_docs = _filter_retrieved_docs_by_scope(question, retrieved_docs)
    try:
        from app.context_prep import boost_docs_with_source_page_text

        retrieved_docs = boost_docs_with_source_page_text(retrieved_docs, raw_question)
    except Exception as source_rerank_err:
        logger.warning("[SOURCE_RERANK] Falling back to retrieval order: %s", source_rerank_err)
    retrieval_time = time.perf_counter() - t_retrieval_start

    t_rerank_start = time.perf_counter()
    selected_docs, selection_metadata = select_context_docs(retrieved_docs)
    if not selected_docs:
        logger.warning("[CONTEXT_SELECTION] No context selected: %s", selection_metadata["reason"])
    rerank_time = time.perf_counter() - t_rerank_start

    context_texts = [d.page_content for d in selected_docs]
    context_sources = [d.metadata.get("source", f"Document {i + 1}") for i, d in enumerate(selected_docs)]
    max_score = selection_metadata.get("max_score") or (get_doc_score(retrieved_docs[0]) if retrieved_docs else None)
    intent_context = _format_intent_context(intent_resolution.to_metadata())
    answer_context_texts = context_texts
    source_page_contexts = []
    try:
        from app.context_prep import extract_source_page_contexts

        source_page_contexts = extract_source_page_contexts(selected_docs)
        if source_page_contexts:
            answer_context_texts = source_page_contexts
            logger.info(
                "[ANSWER_CONTEXT] Using exact source page text for non-stream answer (%d pages)",
                len(source_page_contexts),
            )
    except Exception as source_ctx_err:
        logger.warning("[ANSWER_CONTEXT] Falling back to retrieval notes: %s", source_ctx_err)

    t_llm_start = time.perf_counter()
    reply = None
    use_page_images = USE_PAGE_IMAGES if use_page_images_override is None else bool(use_page_images_override)
    strict_vision = bool(use_page_images_override) or (use_page_images and VISION_STRICT_MODE)
    requested_mode = "vision" if use_page_images else "text"
    use_image_mode = use_page_images and selected_docs
    mode_fallback_reason = "no_selected_docs" if use_page_images and not selected_docs else None
    page_images_for_ragas = None

    if strict_vision and not selected_docs:
        logger.warning("[VISION_MODE] strict mode with no selected docs; returning vision no-context response")
        reply = "I couldn't find relevant pages for this vision request."
        use_image_mode = True
        mode_fallback_reason = None

    if use_image_mode and not (strict_vision and not selected_docs and reply):
        try:
            from app.context_prep import prepare_page_context

            logger.info("Using PDF page image context mode")
            page_images = prepare_page_context(selected_docs, db_pool, collection)
            page_images_for_ragas = page_images

            if page_images and len(page_images) > 0:
                prompt_text = build_vision_prompt().format(
                    history_section=history_section,
                    page_count=len(page_images),
                    intent_context=intent_context,
                    question=raw_question,
                )

                content_parts = [{"type": "text", "text": prompt_text}]
                content_parts.extend(build_openai_compatible_image_parts(page_images))
                message = HumanMessage(content=content_parts)

                response = call_llm_with_retry(lambda: llm.invoke([message]))
                reply = extract_text_from_llm_response(response)

                if is_not_found_response(reply) and context_texts:
                    if strict_vision:
                        logger.warning("[VISION_MODE] strict mode keeps vision not-found response")
                        use_image_mode = True
                        mode_fallback_reason = None
                    else:
                        logger.warning("Vision returned 'not found'; falling back to text context")
                        use_image_mode = False
                        mode_fallback_reason = "vision_not_found"
                else:
                    logger.info("Sent %d page images to vision LLM", len(page_images))
                    use_image_mode = True
            else:
                if strict_vision:
                    logger.warning("[VISION_MODE] strict mode with no page images")
                    reply = "I couldn't load page images for this vision request."
                    use_image_mode = True
                    mode_fallback_reason = None
                else:
                    logger.warning("No page images found, falling back to text context")
                    use_image_mode = False
                    mode_fallback_reason = "no_page_images"
        except Exception as e:
            if strict_vision:
                logger.error("[VISION_MODE] strict mode preparation failure: %s", e)
                reply = "I couldn't prepare page images for this vision request."
                use_image_mode = True
                mode_fallback_reason = None
            else:
                logger.error("Image context preparation failed: %s", e)
                logger.warning("Falling back to text context")
                use_image_mode = False
                mode_fallback_reason = "vision_prepare_error"

    if not use_image_mode:
        if answer_context_texts:
            if answer_context_texts is context_texts:
                context_str = "\n\n---\n\n".join(f"[Source: {src}]\n{c}" for src, c in zip(context_sources, context_texts))
            else:
                context_str = "\n\n---\n\n".join(answer_context_texts)
            chain = (
                {
                    "history_section": (lambda _: history_section),
                    "context": (lambda _: context_str),
                    "intent_context": (lambda _: intent_context),
                    "question": (lambda _: raw_question),
                }
                | build_enhanced_prompt()
                | llm
                | StrOutputParser()
            )
        else:
            chain = (
                {
                    "history_section": (lambda _: history_section),
                    "intent_context": (lambda _: intent_context),
                    "question": (lambda _: raw_question),
                }
                | build_no_context_prompt()
                | llm
                | StrOutputParser()
            )
        if reply is None:
            try:
                reply = call_llm_with_retry(lambda: chain.invoke({}))
            except Exception as e:
                logger.error("[TEXT_MODE] Non-stream invoke failed: %s", e)
                reply = (
                    "I can't generate a response right now because the model service is temporarily unavailable "
                    "(often quota or rate-limit related). Please retry in a bit."
                )

    llm_time = time.perf_counter() - t_llm_start
    total_time = time.perf_counter() - t0
    answer_support_status = _determine_answer_support_status(
        reply,
        selected_docs,
        intent_ok=(intent_resolution.status == "ok"),
    )

    log_chat_request(
        question=question,
        retrieval_time=retrieval_time,
        rerank_time=rerank_time,
        llm_time=llm_time,
        total_time=total_time,
        retrieved_docs=retrieved_docs,
        selected_docs=selected_docs,
        max_score=max_score,
    )

    ragas_scores = empty_ragas_scores()
    ragas_status = "disabled"
    ragas_request = None
    resolved_ragas_ground_truth = ragas_ground_truth or resolve_ground_truth(question)
    prefilled_answer_match = calculate_answer_match(reply, resolved_ragas_ground_truth)
    if prefilled_answer_match is not None:
        ragas_scores["answer_match"] = prefilled_answer_match
        ragas_status = "complete"
    if ENABLE_RAGAS:
        try:
            ragas_contexts = context_texts

            if source_page_contexts:
                ragas_contexts = source_page_contexts
                logger.info(
                    "[RAGAS] Using exact source page contexts for evaluation (%d pages)",
                    len(source_page_contexts),
                )
            else:
                try:
                    from app.context_prep import extract_source_page_contexts

                    source_page_contexts = extract_source_page_contexts(selected_docs)
                    if source_page_contexts:
                        ragas_contexts = source_page_contexts
                        logger.info(
                            "[RAGAS] Using exact source page contexts for evaluation (%d pages)",
                            len(source_page_contexts),
                        )
                except Exception as source_ctx_err:
                    logger.warning("[RAGAS] Source page context extraction failed; using fallback contexts: %s", source_ctx_err)

            use_vision_ocr_context = os.getenv("RAGAS_USE_VISION_OCR_CONTEXT", "true").lower() in (
                "1",
                "true",
                "yes",
                "on",
            )
            if not source_page_contexts and use_image_mode and page_images_for_ragas and use_vision_ocr_context:
                try:
                    from app.context_prep import extract_ocr_contexts

                    ocr_contexts = extract_ocr_contexts(page_images_for_ragas)
                    if ocr_contexts:
                        ragas_contexts = ocr_contexts
                        logger.info("[RAGAS] Using OCR page contexts for vision evaluation (%d pages)", len(ocr_contexts))
                    else:
                        logger.warning("[RAGAS] OCR returned empty contexts; falling back to retrieved text")
                except Exception as ocr_err:
                    logger.warning("[RAGAS] OCR context extraction failed; using retrieved text: %s", ocr_err)

            if ENABLE_BACKGROUND_RAGAS:
                logger.info("[RAGAS] Queued evaluation for non-stream response")
                ragas_status = "pending"
                ragas_request = {
                    "question": question,
                    "answer": reply,
                    "contexts": ragas_contexts,
                    "ground_truth": resolved_ragas_ground_truth,
                }
            else:
                logger.info("[RAGAS] Triggering evaluation for non-stream response")
                ragas_scores = evaluate_response_async(
                    question=question,
                    answer=reply,
                    contexts=ragas_contexts,
                    ground_truth=resolved_ragas_ground_truth,
                )
                if _has_primary_ragas_scores(ragas_scores):
                    ragas_status = "complete"
                else:
                    logger.warning("[RAGAS] No primary scores returned in sync mode")
                    ragas_status = "error"
        except Exception as e:
            logger.error("[RAGAS] Failed to start evaluation: %s", e)
            ragas_scores = empty_ragas_scores()
            ragas_status = "error"

    response_mode = "vision" if use_image_mode else "text"

    return {
        "reply": reply,
        "processing_time": round(total_time, 2),
        "retrieval_time": round(retrieval_time, 2),
        "rerank_time": round(rerank_time, 2),
        "llm_time": round(llm_time, 2),
        "context_count": len(answer_context_texts),
        "max_score": max_score,
        "sources": context_sources,
        "source_details": [
            {
                "source": doc.metadata.get("source", "Unknown"),
                "source_id": doc.metadata.get("source_id", doc.metadata.get("source", "Unknown")),
                "page": doc.metadata.get("page", "N/A"),
                "brand": doc.metadata.get("brand", ""),
                "model_subbrand": doc.metadata.get("model_subbrand", ""),
                "chunk_id": doc.metadata.get("chunk_id", "N/A"),
                "score": get_doc_score(doc),
            }
            for doc in selected_docs
        ],
        "ragas": ragas_scores,
        "ragas_status": ragas_status,
        "response_mode": response_mode,
        "requested_mode": requested_mode,
        "mode_fallback_reason": mode_fallback_reason,
        "answer_support_status": answer_support_status,
        "intent_query": processed_msg,
        "intent_source": intent_source,
        "intent_details": intent_resolution.to_metadata(),
        "ragas_request": ragas_request,
    }


def stream_answer_question(
    question: str,
    db_pool,
    llm,
    intent_llm,
    embedder,
    collection: str,
    retriever_class,
    reranker_class,
    chat_history: List[dict] = None,
    use_page_images_override: bool | None = None,
    ragas_ground_truth: str | None = None,
):
    """
    Generator that yields:
    - {"type": "status", "msg": "..."}
    - {"type": "context", "sources": [...]}
    - {"type": "token", "text": "..."} (streaming)
    - {"type": "stats", "data": {...}}
    - {"type": "done"}
    """

    raw_question = (question or "").strip()
    history_section = format_chat_history(chat_history or [], max_messages=5)
    intent_resolution = resolve_question_intent(
        raw_question,
        db_pool=db_pool,
        collection=collection,
        intent_llm=intent_llm,
        history_section=history_section,
    )
    processed_msg = intent_resolution.normalized_query
    intent_source = intent_resolution.source
    if intent_resolution.status != "ok":
        yield json.dumps({"type": "token", "text": intent_resolution.reply or "I don't understand the question, could you be more specific?"})
        yield json.dumps(
            {
                "type": "stats",
                "data": {
                    "processing_time": 0.0,
                    "retrieval_time": 0.0,
                    "llm_time": 0.0,
                    "context_count": 0,
                    "max_score": 0.0,
                    "sources": [],
                    "source_details": [],
                    "ragas": empty_ragas_scores(),
                    "ragas_status": "disabled",
                    "response_mode": "text",
                    "requested_mode": "text",
                    "mode_fallback_reason": None,
                    "intent_query": processed_msg,
                    "intent_source": intent_source,
                    "intent_details": intent_resolution.to_metadata(),
                    "full_reply": intent_resolution.reply or "I don't understand the question, could you be more specific?",
                },
            }
        )
        yield json.dumps({"type": "done"})
        return

    t0 = time.perf_counter()
    yield json.dumps({"type": "status", "msg": "Thinking..."})
    logger.info("[INTENT] source=%s query='%s'", intent_source, processed_msg[:200])
    logger.info(
        "[INTENT_SCOPE] brand_filters=%s model_filters=%s intent=%s",
        intent_resolution.brand_filters,
        intent_resolution.model_subbrand_filters,
        intent_resolution.intent,
    )

    t_retrieval_start = time.perf_counter()
    base_retriever = retriever_class(
        connection_pool=db_pool,
        embedder=embedder,
        collection=collection,
        brand_filters=intent_resolution.brand_filters,
        model_subbrand_filters=intent_resolution.model_subbrand_filters,
    )
    reranker = reranker_class(base_retriever=base_retriever)
    retrieved_docs = reranker.invoke(processed_msg) or []
    retrieved_docs = _filter_retrieved_docs_by_scope(question, retrieved_docs)
    try:
        from app.context_prep import boost_docs_with_source_page_text

        retrieved_docs = boost_docs_with_source_page_text(retrieved_docs, raw_question)
    except Exception as source_rerank_err:
        logger.warning("[SOURCE_RERANK] Stream fallback to retrieval order: %s", source_rerank_err)
    retrieval_time = time.perf_counter() - t_retrieval_start

    t_rerank_start = time.perf_counter()
    selected_docs, selection_metadata = select_context_docs(retrieved_docs)
    if not selected_docs:
        logger.warning("[CONTEXT_SELECTION] No context selected: %s", selection_metadata["reason"])
    rerank_time = time.perf_counter() - t_rerank_start

    logger.info(
        "[RETRIEVAL] query='%s' retrieved=%d selected=%d",
        processed_msg[:50],
        len(retrieved_docs),
        len(selected_docs),
    )

    if selected_docs:
        for i, doc in enumerate(selected_docs):
            source = doc.metadata.get("source", "Unknown")
            page = doc.metadata.get("page", 0)
            chunk_type = doc.metadata.get("chunk_type", "unknown")
            score = doc.metadata.get("score", 0.0)
            char_count = doc.metadata.get("char_count", len(doc.page_content))
            logger.debug(
                "[CHUNK_%d] source='%s' page=%s type=%s score=%.4f chars=%s",
                i + 1,
                source,
                page,
                chunk_type,
                score,
                char_count,
            )

    if selected_docs:
        chunk_types = {}
        for doc in selected_docs:
            ctype = doc.metadata.get("chunk_type", "unknown")
            chunk_types[ctype] = chunk_types.get(ctype, 0) + 1
        logger.info("[DISTRIBUTION] types=%s", dict(sorted(chunk_types.items())))

    context_texts = [d.page_content for d in selected_docs]
    context_sources = list(dict.fromkeys([d.metadata.get("source", "Unknown") for d in selected_docs]))
    intent_context = _format_intent_context(intent_resolution.to_metadata())
    answer_context_texts = context_texts
    source_page_contexts = []
    try:
        from app.context_prep import extract_source_page_contexts

        source_page_contexts = extract_source_page_contexts(selected_docs)
        if source_page_contexts:
            answer_context_texts = source_page_contexts
            logger.info(
                "[ANSWER_CONTEXT] Using exact source page text for stream answer (%d pages)",
                len(source_page_contexts),
            )
    except Exception as source_ctx_err:
        logger.warning("[ANSWER_CONTEXT] Stream fallback to retrieval notes: %s", source_ctx_err)

    page_references = []
    seen_pages = set()
    for d in selected_docs:
        source = d.metadata.get("source", "Unknown")
        source_id = d.metadata.get("source_id", source)
        page = d.metadata.get("page", 0)
        brand = d.metadata.get("brand", "")
        model_subbrand = d.metadata.get("model_subbrand", "")
        score = d.metadata.get("score", 0.0)
        page_key = (source_id, page, brand, model_subbrand)
        if page_key not in seen_pages and page > 0:
            page_references.append(
                {
                    "source": source,
                    "source_id": source_id,
                    "page": page,
                    "brand": brand,
                    "model_subbrand": model_subbrand,
                    "score": score,
                }
            )
            seen_pages.add(page_key)
    page_references.sort(key=lambda x: x["score"], reverse=True)

    max_score = selection_metadata.get("max_score") or (get_doc_score(retrieved_docs[0]) if retrieved_docs else None)

    yield json.dumps(
        {
            "type": "context",
            "sources": context_sources,
            "doc_count": len(selected_docs),
            "page_references": page_references,
        }
    )

    t_llm_start = time.perf_counter()
    full_reply = ""
    use_page_images = USE_PAGE_IMAGES if use_page_images_override is None else bool(use_page_images_override)
    strict_vision = bool(use_page_images_override) or (use_page_images and VISION_STRICT_MODE)
    requested_mode = "vision" if use_page_images else "text"
    use_image_mode = use_page_images and selected_docs
    mode_fallback_reason = "no_selected_docs" if use_page_images and not selected_docs else None
    page_images_for_ragas = None
    logger.debug(
        "[VISION_CHECK] enabled=%s has_docs=%s will_use=%s",
        USE_PAGE_IMAGES,
        len(selected_docs) > 0,
        use_image_mode,
    )

    if strict_vision and not selected_docs:
        logger.warning("[VISION_MODE] strict mode with no selected docs; returning vision no-context response")
        full_reply = "I couldn't find relevant pages for this vision request."
        yield json.dumps({"type": "token", "text": full_reply})
        use_image_mode = True
        mode_fallback_reason = None

    if use_image_mode and not (strict_vision and not selected_docs and full_reply):
        logger.info("[VISION_MODE] Preparing page images")
        try:
            from app.context_prep import prepare_page_context

            page_images = prepare_page_context(selected_docs, db_pool, collection)
            page_images_for_ragas = page_images
            if page_images and len(page_images) > 0:
                total_size_mb = sum(len(img["image_data"]) for img in page_images) / (1024 * 1024)
                logger.info("[VISION_MODE] prepared=%d pages size=%.1fMB", len(page_images), total_size_mb)

                for i, img in enumerate(page_images):
                    size_mb = len(img["image_data"]) / (1024 * 1024)
                    logger.debug(
                        "[IMAGE_%d] source='%s' page=%s size=%.1fMB score=%.4f",
                        i + 1,
                        img["source"],
                        img["page"],
                        size_mb,
                        img["score"],
                    )

                prompt_text = build_vision_prompt().format(
                    question=raw_question,
                    history_section=history_section,
                    page_count=len(page_images),
                    intent_context=intent_context,
                )

                content_parts = [{"type": "text", "text": prompt_text}]
                content_parts.extend(build_openai_compatible_image_parts(page_images))
                message = HumanMessage(content=content_parts)

                logger.debug(
                    "[VISION_API] sending parts=%d (1 text + %d images)",
                    len(content_parts),
                    len(page_images),
                )

                try:
                    response = call_llm_with_retry(lambda: llm.invoke([message]))
                    full_reply = extract_text_from_llm_response(response)
                    if is_not_found_response(full_reply) and answer_context_texts:
                        if strict_vision:
                            logger.warning("[VISION_MODE] strict mode keeps vision not-found response")
                            if full_reply:
                                chunk_size = 50
                                for i in range(0, len(full_reply), chunk_size):
                                    chunk = full_reply[i : i + chunk_size]
                                    yield json.dumps({"type": "token", "text": chunk})
                            use_image_mode = True
                            mode_fallback_reason = None
                        else:
                            logger.warning("[VISION_MODE] returned not-found; fallback=text")
                            use_image_mode = False
                            full_reply = ""
                            mode_fallback_reason = "vision_not_found"
                    else:
                        logger.info("[VISION_MODE] success response_length=%d", len(full_reply))
                        if full_reply:
                            chunk_size = 50
                            for i in range(0, len(full_reply), chunk_size):
                                chunk = full_reply[i : i + chunk_size]
                                yield json.dumps({"type": "token", "text": chunk})
                        else:
                            error_msg = "I apologize, but I couldn't generate a proper response from the images."
                            full_reply = error_msg
                            yield json.dumps({"type": "token", "text": error_msg})
                        use_image_mode = True
                except Exception as e:
                    if strict_vision:
                        logger.error("[VISION_MODE] strict mode invoke error='%s'", e)
                        full_reply = "I couldn't process the page images right now. Please retry vision mode."
                        yield json.dumps({"type": "token", "text": full_reply})
                        use_image_mode = True
                        mode_fallback_reason = None
                    else:
                        logger.error("[VISION_MODE] failed error='%s' fallback=text", e)
                        use_image_mode = False
                        full_reply = ""
                        mode_fallback_reason = "vision_invoke_error"
            else:
                if strict_vision:
                    logger.warning("[VISION_MODE] strict mode no_images_available")
                    full_reply = "I couldn't load page images for this vision request."
                    yield json.dumps({"type": "token", "text": full_reply})
                    use_image_mode = True
                    mode_fallback_reason = None
                else:
                    logger.warning("[VISION_MODE] no_images_available fallback=text")
                    use_image_mode = False
                    mode_fallback_reason = "no_page_images"
        except Exception as e:
            if strict_vision:
                logger.error("[VISION_MODE] strict mode preparation_failed error='%s'", e)
                full_reply = "I couldn't prepare page images for this vision request."
                yield json.dumps({"type": "token", "text": full_reply})
                use_image_mode = True
                mode_fallback_reason = None
            else:
                logger.error("[VISION_MODE] preparation_failed error='%s' fallback=text", e)
                use_image_mode = False
                mode_fallback_reason = "vision_prepare_error"

    if not use_image_mode:
        logger.info("[TEXT_MODE] chunks=%d", len(answer_context_texts))

        if answer_context_texts:
            total_chars = sum(len(text) for text in answer_context_texts)
            logger.debug("[TEXT_MODE] context_chars=%d", total_chars)

            if answer_context_texts is context_texts:
                full_context_str = "\n\n---\n\n".join(
                    f"[Source: {d.metadata.get('source', 'Doc')}]\n{d.page_content}" for d in selected_docs
                )
            else:
                full_context_str = "\n\n---\n\n".join(answer_context_texts)
            chain = (
                {
                    "history_section": (lambda _: history_section),
                    "context": (lambda _: full_context_str),
                    "intent_context": (lambda _: intent_context),
                    "question": (lambda _: raw_question),
                }
                | build_enhanced_prompt()
                | llm
                | StrOutputParser()
            )
        else:
            logger.warning("[TEXT_MODE] no_context using_fallback_prompt")
            chain = (
                {
                    "history_section": (lambda _: history_section),
                    "intent_context": (lambda _: intent_context),
                    "question": (lambda _: raw_question),
                }
                | build_no_context_prompt()
                | llm
                | StrOutputParser()
            )

        try:
            for chunk in chain.stream({}):
                full_reply += chunk
                yield json.dumps({"type": "token", "text": chunk})
            logger.info("[TEXT_MODE] success response_length=%d", len(full_reply))
        except Exception as e:
            logger.error("[TEXT_MODE] failed error='%s'", e)
            yield json.dumps({"type": "token", "text": f"\\n[Error generating response: {e}]"})

    llm_time = time.perf_counter() - t_llm_start
    total_time = time.perf_counter() - t0
    mode_str = "vision" if use_image_mode else "text"
    answer_support_status = _determine_answer_support_status(
        full_reply,
        selected_docs,
        intent_ok=(intent_resolution.status == "ok"),
    )
    logger.info(
        "[COMPLETE] mode=%s response_length=%d llm_time=%.2fs total_time=%.2fs",
        mode_str,
        len(full_reply),
        llm_time,
        total_time,
    )

    ragas_scores = empty_ragas_scores()
    ragas_status = "disabled"
    ragas_request = None
    resolved_ragas_ground_truth = ragas_ground_truth or resolve_ground_truth(question)
    prefilled_answer_match = calculate_answer_match(full_reply, resolved_ragas_ground_truth)
    if prefilled_answer_match is not None:
        ragas_scores["answer_match"] = prefilled_answer_match
        ragas_status = "complete"
    if ENABLE_RAGAS:
        try:
            ragas_contexts = context_texts

            if source_page_contexts:
                ragas_contexts = source_page_contexts
                logger.info(
                    "[RAGAS] Using exact source page contexts for stream evaluation (%d pages)",
                    len(source_page_contexts),
                )
            else:
                try:
                    from app.context_prep import extract_source_page_contexts

                    source_page_contexts = extract_source_page_contexts(selected_docs)
                    if source_page_contexts:
                        ragas_contexts = source_page_contexts
                        logger.info(
                            "[RAGAS] Using exact source page contexts for stream evaluation (%d pages)",
                            len(source_page_contexts),
                        )
                except Exception as source_ctx_err:
                    logger.warning("[RAGAS] Stream source page context extraction failed; using fallback contexts: %s", source_ctx_err)

            use_vision_ocr_context = os.getenv("RAGAS_USE_VISION_OCR_CONTEXT", "true").lower() in (
                "1",
                "true",
                "yes",
                "on",
            )
            if not source_page_contexts and use_image_mode and page_images_for_ragas and use_vision_ocr_context:
                try:
                    from app.context_prep import extract_ocr_contexts

                    ocr_contexts = extract_ocr_contexts(page_images_for_ragas)
                    if ocr_contexts:
                        ragas_contexts = ocr_contexts
                        logger.info("[RAGAS] Using OCR page contexts for vision evaluation (%d pages)", len(ocr_contexts))
                    else:
                        logger.warning("[RAGAS] OCR returned empty contexts; falling back to retrieved text")
                except Exception as ocr_err:
                    logger.warning("[RAGAS] OCR context extraction failed; using retrieved text: %s", ocr_err)

            if ENABLE_BACKGROUND_RAGAS:
                logger.info("[RAGAS] Queued evaluation for stream response")
                ragas_status = "pending"
                ragas_request = {
                    "question": question,
                    "answer": full_reply,
                    "contexts": ragas_contexts,
                    "ground_truth": resolved_ragas_ground_truth,
                }
            else:
                logger.info("[RAGAS] Triggering evaluation for stream response")
                ragas_scores = evaluate_response_async(
                    question=question,
                    answer=full_reply,
                    contexts=ragas_contexts,
                    ground_truth=resolved_ragas_ground_truth,
                )
                if _has_primary_ragas_scores(ragas_scores):
                    ragas_status = "complete"
                else:
                    logger.warning("[RAGAS] No primary scores returned in sync mode")
                    ragas_status = "error"
        except Exception as e:
            logger.error("[RAGAS] Failed to start evaluation: %s", e)
            ragas_scores = empty_ragas_scores()
            ragas_status = "error"

    yield json.dumps(
        {
            "type": "stats",
                "data": {
                    "processing_time": round(total_time, 2),
                    "retrieval_time": round(retrieval_time, 2),
                    "llm_time": round(llm_time, 2),
                    "context_count": len(answer_context_texts),
                    "max_score": max_score or 0.0,
                    "sources": context_sources,
                "source_details": [
                    {
                        "source": doc.metadata.get("source", "Unknown"),
                        "source_id": doc.metadata.get("source_id", doc.metadata.get("source", "Unknown")),
                        "page": doc.metadata.get("page", "N/A"),
                        "brand": doc.metadata.get("brand", ""),
                        "model_subbrand": doc.metadata.get("model_subbrand", ""),
                        "chunk_id": doc.metadata.get("chunk_id", "N/A"),
                        "score": get_doc_score(doc),
                    }
                    for doc in selected_docs
                ],
                "ragas": ragas_scores,
                "ragas_status": ragas_status,
                "response_mode": mode_str,
                "requested_mode": requested_mode,
                "mode_fallback_reason": mode_fallback_reason,
                "answer_support_status": answer_support_status,
                "intent_query": processed_msg,
                "intent_source": intent_source,
                "intent_details": intent_resolution.to_metadata(),
                "ragas_request": ragas_request,
                "full_reply": full_reply,
            },
        }
    )

    yield json.dumps({"type": "done"})
