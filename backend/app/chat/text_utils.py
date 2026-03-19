import json
import logging
import re
import time
from typing import Any, Dict, List
import base64

from langchain_core.output_parsers import StrOutputParser

from app.chat.prompts import build_intent_extraction_prompt

logger = logging.getLogger(__name__)


def call_llm_with_retry(llm_callable, max_retries: int = 3, base_wait: float = 1.0):
    """
    Call LLM with exponential backoff retry logic.
    """
    for attempt in range(max_retries):
        try:
            return llm_callable()
        except Exception as e:
            err_text = str(e).lower()
            quota_exhausted = (
                "resource_exhausted" in err_text
                or "quota exceeded" in err_text
                or "generaterequestsperdayperprojectpermodel-freetier" in err_text
            )
            if quota_exhausted:
                logger.error("[LLM_ERROR] Quota exhausted, skipping retries: %s", e)
                raise
            if attempt < max_retries - 1:
                wait_time = base_wait * (2 ** attempt)
                logger.warning(
                    "[LLM_RETRY] Attempt %d/%d failed, retrying in %ss: %s",
                    attempt + 1,
                    max_retries,
                    wait_time,
                    e,
                )
                time.sleep(wait_time)
            else:
                logger.error("[LLM_ERROR] Failed after %d attempts: %s", max_retries, e)
                raise


def extract_text_from_llm_response(response) -> str:
    """
    Extract text from LLM response, handling common response formats.
    """
    if hasattr(response, "content"):
        content = response.content
    elif isinstance(response, str):
        content = response
    else:
        content = str(response)

    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict) and "text" in item:
                return item["text"]
        return str(content[0]) if content else ""

    return str(content)


def is_not_found_response(text: str) -> bool:
    """Detect the canonical fallback response."""
    if not text:
        return True
    normalized = " ".join(text.strip().lower().split())
    patterns = [
        "i couldn't find specific information about this",
        "i could not find specific information about this",
        "couldn't find specific information",
        "could not find specific information",
    ]
    return any(p in normalized for p in patterns)


def preprocess_query(query: str) -> str:
    if not query:
        return query

    abbreviations = {
        "plc": "Programmable Logic Controller",
        "hmi": "Human Machine Interface",
        "profinet": "PROFINET",
        "i/o": "input output",
        "gds": "Global Data Space",
        "esm": "Execution and Synchronization Manager",
    }

    processed = query.lower()
    for abbr, full in abbreviations.items():
        processed = re.sub(rf"\b{re.escape(abbr)}\b", full, processed)

    return processed if processed != query.lower() else query


def _clean_intent_query(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""

    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            for key in ("normalized_query", "retrieval_query", "query", "intent", "search_query"):
                value = parsed.get(key)
                if isinstance(value, str) and value.strip():
                    raw = value.strip()
                    break
    except Exception:
        pass

    lines = [line.strip(" -*\t") for line in raw.splitlines() if line.strip()]
    if not lines:
        return ""

    candidate = lines[0]
    candidate = re.sub(r"^(retrieval query|search query|query|intent)\s*:\s*", "", candidate, flags=re.IGNORECASE)
    candidate = candidate.strip().strip("`").strip('"').strip("'").strip()
    candidate = re.sub(r"\s+", " ", candidate)
    return candidate


def build_retrieval_query(
    question: str,
    *,
    intent_llm=None,
    history_section: str = "",
) -> tuple[str, str]:
    """
    Produce the retrieval query used before reranking.

    Returns:
        (query, source) where source indicates whether the query came from the
        intent model or from the fallback preprocessing path.
    """
    processed_question = preprocess_query((question or "").strip())
    if not processed_question:
        return "", "empty_question"

    if intent_llm is None:
        return processed_question, "fallback_no_intent_llm"

    try:
        chain = build_intent_extraction_prompt() | intent_llm | StrOutputParser()
        rewritten = call_llm_with_retry(
            lambda: chain.invoke(
                {
                    "history_section": history_section,
                    "question": question,
                }
            ),
            max_retries=2,
            base_wait=0.5,
        )
        cleaned = _clean_intent_query(rewritten)
        if not cleaned:
            return processed_question, "fallback_empty_intent_query"
        return preprocess_query(cleaned), "intent_llm"
    except Exception as e:
        logger.warning("[INTENT_LLM] Failed to extract intent, using original query: %s", e)
        return processed_question, "fallback_intent_error"


def build_openai_compatible_image_parts(page_images: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Build OpenAI-compatible image parts for multimodal chat models.
    """
    content_parts: List[Dict[str, Any]] = []
    for page in page_images:
        image_bytes = page["image_data"]
        base64_image = base64.b64encode(image_bytes).decode("utf-8")
        content_parts.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{base64_image}",
                },
            }
        )
    return content_parts


def format_chat_history(chat_history: List[dict], max_messages: int = 6) -> str:
    """
    Format chat history for inclusion in the prompt.
    """
    if not chat_history:
        return ""

    recent = chat_history[-max_messages:]
    if not recent:
        return ""

    formatted_lines = []
    exchange_num = 1
    i = 0

    while i < len(recent):
        msg = recent[i]
        if msg.get("role") == "user":
            user_content = msg.get("content", "")[:200]
            assistant_content = ""
            if i + 1 < len(recent) and recent[i + 1].get("role") == "assistant":
                assistant_content = recent[i + 1].get("content", "")[:200]
                i += 1

            formatted_lines.append(f"[Exchange {exchange_num}]")
            formatted_lines.append(f"  Q: {user_content}")
            if assistant_content:
                formatted_lines.append(f"  A: {assistant_content}")
            exchange_num += 1
        i += 1

    if not formatted_lines:
        return ""

    return "=== PREVIOUS CONVERSATION ===\n" + "\n".join(formatted_lines) + "\n=== END PREVIOUS CONVERSATION ===\n\n"
