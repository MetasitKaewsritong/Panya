import base64
import logging
import re
import time
from typing import Any, Dict, List

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


def fix_markdown_tables(text: str) -> str:
    """
    Fix malformed markdown tables that are on a single line.
    Converts: | A | B | | --- | --- | | 1 | 2 |
    To proper multi-line format.
    """
    if not text or "|" not in text:
        return text

    lines = text.split("\n")
    fixed_lines = []

    for line in lines:
        if re.search(r"\|\s*-{2,}\s*\|.*\|", line) and line.count("|") > 8:
            parts = [p.strip() for p in line.split("|")]
            parts = [p for p in parts if p]

            if len(parts) >= 4:
                sep_indices = [i for i, p in enumerate(parts) if re.match(r"^-+$", p)]

                if sep_indices and len(sep_indices) >= 1:
                    num_cols = sep_indices[0]

                    if num_cols > 0 and num_cols == len(sep_indices):
                        result_rows = []
                        for i in range(0, len(parts), num_cols):
                            row_parts = parts[i : i + num_cols]
                            if len(row_parts) == num_cols:
                                result_rows.append("| " + " | ".join(row_parts) + " |")

                        if result_rows:
                            fixed_lines.append("\n".join(result_rows))
                            continue

        fixed_lines.append(line)

    return "\n".join(fixed_lines)


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


def encode_images_for_gemini(page_images: List[Dict[str, Any]]) -> List[str]:
    """
    Encode page images as base64 for Gemini vision API.
    """
    encoded_images = []
    for page in page_images:
        image_bytes = page["image_data"]
        base64_image = base64.b64encode(image_bytes).decode("utf-8")
        encoded_images.append(base64_image)
    return encoded_images


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
