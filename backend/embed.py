"""
Batch embedding CLI script for documents.

PDF ingestion flow:
1. Render each PDF page as an image.
2. Send each page to gemma3:4b (or configured summary model) for one page summary.
3. Embed that summary text into pgvector.
4. Store the rendered page image with the same page-level metadata.
"""
import argparse
import gc
import glob
import hashlib
import io
import json
import logging
import os
import re
import time
from typing import Iterable, List

import psycopg2
import torch
from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from psycopg2.extras import execute_values
from PIL import Image
from sentence_transformers import SentenceTransformer
from tqdm import tqdm

from app.chat.text_utils import (
    build_openai_compatible_image_parts,
    call_llm_with_retry,
    extract_text_from_llm_response,
)
from app.embed_logic import create_json_qa_chunks, get_embedding_instruction
from app.pdf_image_utils import (
    delete_page_images,
    get_pdf_page_count,
    iter_pdf_page_assets,
    store_page_images,
)

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

DB_URL = os.getenv("DATABASE_URL")
EMBED_MODEL = os.getenv("EMBED_MODEL", "BAAI/bge-m3")
DEFAULT_SUMMARY_MODEL = os.getenv("EMBED_SUMMARY_MODEL", "gemma3:4b")
DEFAULT_SUMMARY_BASE_URL = (
    os.getenv("EMBED_SUMMARY_BASE_URL")
    or os.getenv("LLM_BASE_URL")
    or os.getenv("OLLAMA_BASE_URL")
    or "http://host.docker.internal:11434/v1"
)
DEFAULT_SUMMARY_API_KEY = (
    os.getenv("EMBED_SUMMARY_API_KEY")
    or os.getenv("LLM_API_KEY")
    or os.getenv("OLLAMA_API_KEY")
    or "ollama"
)


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except Exception:
        return default


def _env_bool(key: str, default: bool) -> bool:
    value = os.getenv(key)
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


PAGE_IMAGE_DPI = _env_int("PAGE_IMAGE_DPI", 150)
SUMMARY_TIMEOUT = _env_int("EMBED_SUMMARY_TIMEOUT", 120)
SUMMARY_MAX_OUTPUT_TOKENS = _env_int("EMBED_SUMMARY_MAX_OUTPUT_TOKENS", 320)
SUMMARY_INCLUDE_PAGE_IMAGE = _env_bool("EMBED_SUMMARY_INCLUDE_PAGE_IMAGE", True)
SUMMARY_IMAGE_MAX_DIM = _env_int("EMBED_SUMMARY_IMAGE_MAX_DIM", 1800)
BLANK_PAGE_IMAGE_MAX_BYTES = _env_int("EMBED_BLANK_PAGE_IMAGE_MAX_BYTES", 25000)
NO_READABLE_CONTENT_TOKEN = "NO_READABLE_CONTENT"
_CONTENTS_DOT_LEADER_RE = re.compile(r"(?:\.\s*){3,}\d{1,4}\b")
_HEADING_TOKEN_RE = re.compile(r"(?:chapter|section)\s+\d+|\b\d+(?:\.\d+)+\b", re.IGNORECASE)


def get_device() -> str:
    """Get the best available device."""
    if torch.cuda.is_available():
        device = "cuda:0"
        logging.info("Using GPU: %s", torch.cuda.get_device_name(0))
    else:
        device = "cpu"
        logging.info("GPU not available, using CPU")
    return device


def normalize_scope_value(value: str) -> str:
    return " ".join(str(value or "").strip().split())


def normalize_document_source(file_path: str) -> str:
    raw_path = str(file_path or "").strip()
    if not raw_path:
        return ""
    normalized = os.path.abspath(raw_path).replace("\\", "/")
    normalized = re.sub(r"/+", "/", normalized)
    return normalized


def get_display_source_name(source_value: str) -> str:
    cleaned = str(source_value or "").replace("\\", "/").rstrip("/")
    if not cleaned:
        return ""
    return os.path.basename(cleaned) or cleaned


def normalize_summary_text(text: str) -> str:
    """
    Light normalization that preserves Unicode content and only collapses noisy whitespace.
    """
    raw = str(text or "").replace("\x00", " ").strip()
    raw = re.sub(r"\s+", " ", raw)
    return raw.strip()


def is_visually_blank_page(page_asset: dict) -> bool:
    image_bytes = page_asset.get("image_data", b"")
    if not image_bytes:
        return True

    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            grayscale = img.convert("L")
            histogram = grayscale.histogram()
            total_pixels = grayscale.size[0] * grayscale.size[1]
    except Exception:
        return False

    if total_pixels <= 0:
        return True

    nearly_white_pixels = sum(histogram[250:256])
    return (nearly_white_pixels / total_pixels) >= 0.9995


def normalize_match_text(text: str) -> str:
    cleaned = str(text or "").lower()
    cleaned = cleaned.replace("\x00", " ")
    cleaned = re.sub(r"[^a-z0-9\-\+\./ ]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def filter_retrieval_note_by_page_text(note: str, page_asset: dict, page_type_hint: str) -> str:
    """
    Use extracted page text as a lightweight validator for list-like retrieval notes.
    The image remains the source of generation; extracted text only removes obviously
    hallucinated items that are not present on the page.
    """
    if page_type_hint not in {"introduction", "table_of_contents", "manual_list", "glossary_list"}:
        return note

    raw_page_text = str(page_asset.get("text") or "")
    if not raw_page_text:
        return note

    normalized_page_text = normalize_match_text(raw_page_text)
    if not normalized_page_text:
        return note

    kept_items = []
    seen = set()
    items = [part.strip() for part in str(note or "").split(";") if part.strip()]
    for item in items:
        normalized_item = normalize_match_text(item)
        if not normalized_item:
            continue
        if normalized_item in seen:
            continue

        tokens = [tok for tok in re.findall(r"[a-z0-9\-\+./]+", normalized_item) if len(tok) >= 2]
        if not tokens:
            continue

        token_hits = sum(1 for tok in tokens if tok in normalized_page_text)
        item_visible = normalized_item in normalized_page_text
        keep = item_visible
        if not keep and len(tokens) == 1:
            keep = tokens[0] in normalized_page_text
        if not keep and len(tokens) >= 2:
            keep = token_hits >= max(1, len(tokens) - 1)

        if keep:
            kept_items.append(item.strip())
            seen.add(normalized_item)

    if not kept_items:
        return note
    return "; ".join(kept_items[:12])


def build_summary_page_asset(page_asset: dict) -> dict:
    """
    Keep the stored page image at full quality, but downscale the image sent to the
    summary model so one page does not stall the entire embed run.
    """
    image_bytes = page_asset.get("image_data")
    if not image_bytes or SUMMARY_IMAGE_MAX_DIM <= 0:
        return page_asset

    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            width, height = image.size
            longest_side = max(width, height)
            if longest_side <= SUMMARY_IMAGE_MAX_DIM:
                return page_asset

            scale = SUMMARY_IMAGE_MAX_DIM / float(longest_side)
            resized_size = (
                max(1, int(round(width * scale))),
                max(1, int(round(height * scale))),
            )
            resampling = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
            resized = image.resize(resized_size, resampling)
            output = io.BytesIO()
            resized.save(output, format="PNG", optimize=True, compress_level=6)
            summary_asset = dict(page_asset)
            summary_asset["image_data"] = output.getvalue()
            summary_asset["summary_image_size"] = resized_size
            summary_asset["summary_image_original_size"] = (width, height)
            return summary_asset
    except Exception as exc:
        logging.warning(
            "Failed to resize page %s for summary input, using original image: %s",
            page_asset.get("page_number"),
            exc,
        )
        return page_asset


def get_files(paths: List[str]) -> List[str]:
    """Get all PDF and JSON files from input paths."""
    all_files = []
    for path in paths:
        if os.path.isfile(path):
            if path.lower().endswith((".pdf", ".json")):
                all_files.append(path)
        elif os.path.isdir(path):
            all_files.extend(glob.glob(os.path.join(path, "**/*.pdf"), recursive=True))
            all_files.extend(glob.glob(os.path.join(path, "**/*.json"), recursive=True))
    return sorted(set(all_files))


def is_golden_qa_file(file_path: str) -> bool:
    """Detect eval-only Golden QA JSON files by filename."""
    name = os.path.basename(file_path).lower()
    return name.endswith(".json") and "golden_qa" in name


def iter_batches(items: List[Document], batch_size: int) -> Iterable[List[Document]]:
    if batch_size <= 0:
        yield items
        return
    for start in range(0, len(items), batch_size):
        yield items[start:start + batch_size]


def ensure_storage_schema(conn) -> None:
    """
    Ensure the document and page-image storage schema exists on both fresh and
    already-initialized databases.
    """
    cur = conn.cursor()
    try:
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS documents (
                id SERIAL PRIMARY KEY,
                content TEXT NOT NULL,
                metadata JSONB,
                collection VARCHAR(255) NOT NULL,
                hash VARCHAR(64) UNIQUE NOT NULL,
                embedding VECTOR(1024),
                document_source VARCHAR(1024) NOT NULL DEFAULT '',
                page_number INTEGER NOT NULL DEFAULT 0,
                brand VARCHAR(255) NOT NULL DEFAULT '',
                model_subbrand VARCHAR(255) NOT NULL DEFAULT ''
            )
            """
        )
        cur.execute("ALTER TABLE documents ALTER COLUMN document_source TYPE VARCHAR(1024);")
        cur.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS document_source VARCHAR(1024) NOT NULL DEFAULT '';")
        cur.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS page_number INTEGER NOT NULL DEFAULT 0;")
        cur.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS brand VARCHAR(255) NOT NULL DEFAULT '';")
        cur.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS model_subbrand VARCHAR(255) NOT NULL DEFAULT '';")

        cur.execute(
            """
            UPDATE documents
            SET
                document_source = COALESCE(
                    NULLIF(metadata->>'source_id', ''),
                    NULLIF(document_source, ''),
                    COALESCE(metadata->>'source', '')
                ),
                page_number = CASE
                    WHEN page_number <> 0 THEN page_number
                    WHEN COALESCE(metadata->>'page', '') ~ '^[0-9]+$' THEN (metadata->>'page')::INTEGER
                    ELSE 0
                END,
                brand = COALESCE(NULLIF(brand, ''), COALESCE(metadata->>'brand', '')),
                model_subbrand = COALESCE(NULLIF(model_subbrand, ''), COALESCE(metadata->>'model_subbrand', ''))
            WHERE
                document_source = ''
                OR page_number = 0
                OR brand = ''
                OR model_subbrand = ''
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS pdf_pages (
                id SERIAL PRIMARY KEY,
                document_source VARCHAR(1024) NOT NULL,
                page_number INTEGER NOT NULL,
                brand VARCHAR(255) NOT NULL DEFAULT '',
                model_subbrand VARCHAR(255) NOT NULL DEFAULT '',
                collection_name VARCHAR(255) NOT NULL,
                metadata JSONB,
                image_data BYTEA NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE (document_source, page_number, collection_name, brand, model_subbrand)
            )
            """
        )
        cur.execute("ALTER TABLE pdf_pages ALTER COLUMN document_source TYPE VARCHAR(1024);")

        cur.execute("CREATE INDEX IF NOT EXISTS idx_hnsw_embedding ON documents USING hnsw (embedding vector_l2_ops);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_collection ON documents (collection);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_documents_lookup ON documents (collection, document_source, page_number);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_documents_brand_model ON documents (brand, model_subbrand);")
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_pdf_pages_lookup
            ON pdf_pages (collection_name, document_source, page_number, brand, model_subbrand)
            """
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


def create_summary_llm(model_name: str) -> ChatOpenAI:
    return ChatOpenAI(
        model=model_name,
        api_key=DEFAULT_SUMMARY_API_KEY,
        base_url=DEFAULT_SUMMARY_BASE_URL,
        temperature=0.0,
        timeout=SUMMARY_TIMEOUT,
        max_tokens=SUMMARY_MAX_OUTPUT_TOKENS,
    )


def build_chunk_hash(collection: str, chunk: Document) -> str:
    metadata = chunk.metadata or {}
    source = normalize_document_source(metadata.get("source_id") or metadata.get("source", ""))
    page_number = int(metadata.get("page", 0) or 0)
    brand = normalize_scope_value(metadata.get("brand", "")).lower()
    model_subbrand = normalize_scope_value(metadata.get("model_subbrand", "")).lower()
    chunk_type = metadata.get("chunk_type", "unknown")

    if chunk_type == "page_summary":
        hash_input = f"{collection}::{source}::{page_number}::{brand}::{model_subbrand}::{chunk_type}"
    else:
        hash_input = (
            f"{collection}::{source}::{page_number}::{brand}::{model_subbrand}"
            f"::{chunk_type}::{chunk.page_content}"
        )
    return hashlib.sha256(hash_input.encode("utf-8")).hexdigest()


def flush_chunks(
    chunks_to_embed: List[Document],
    embedder,
    conn,
    collection: str,
    *,
    commit: bool = True,
) -> int:
    """Embed and save a batch of chunks."""
    if not chunks_to_embed:
        return 0

    cur = conn.cursor()

    texts = []
    for chunk in chunks_to_embed:
        chunk_type = chunk.metadata.get("chunk_type", "prose")
        instruction = get_embedding_instruction(chunk_type)
        texts.append(instruction + chunk.page_content)

    logging.info("   Embedding %d chunks...", len(chunks_to_embed))
    embeddings = embedder.encode(texts, show_progress_bar=True, batch_size=32, normalize_embeddings=True)

    batch_data = []
    for chunk, embedding in zip(chunks_to_embed, embeddings):
        metadata = dict(chunk.metadata or {})
        source = normalize_document_source(metadata.get("source_id") or metadata.get("source", ""))
        display_source = metadata.get("source") or get_display_source_name(source)
        page_number = int(metadata.get("page", 0) or 0)
        brand = normalize_scope_value(metadata.get("brand", ""))
        model_subbrand = normalize_scope_value(metadata.get("model_subbrand", ""))

        metadata["source"] = display_source
        metadata["source_id"] = source
        metadata["page"] = page_number
        metadata["brand"] = brand
        metadata["model_subbrand"] = model_subbrand

        batch_data.append(
            (
                chunk.page_content,
                embedding.tolist(),
                collection,
                build_chunk_hash(collection, Document(page_content=chunk.page_content, metadata=metadata)),
                json.dumps(metadata, ensure_ascii=False),
                source,
                page_number,
                brand,
                model_subbrand,
            )
        )

    try:
        execute_values(
            cur,
            """
            INSERT INTO documents (
                content,
                embedding,
                collection,
                hash,
                metadata,
                document_source,
                page_number,
                brand,
                model_subbrand
            )
            VALUES %s
            ON CONFLICT (hash) DO UPDATE SET
                content = EXCLUDED.content,
                embedding = EXCLUDED.embedding,
                collection = EXCLUDED.collection,
                metadata = EXCLUDED.metadata,
                document_source = EXCLUDED.document_source,
                page_number = EXCLUDED.page_number,
                brand = EXCLUDED.brand,
                model_subbrand = EXCLUDED.model_subbrand
            """,
            batch_data,
            template="(%s, %s, %s, %s, %s, %s, %s, %s, %s)",
        )
        affected = max(cur.rowcount, 0)
        if commit:
            conn.commit()
    except Exception:
        if commit:
            conn.rollback()
        raise
    finally:
        cur.close()

    del embeddings
    del texts
    gc.collect()
    torch.cuda.empty_cache()
    return affected


def source_exists(conn, collection: str, document_source: str) -> bool:
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT 1
            FROM documents
            WHERE collection = %s AND document_source = %s
            LIMIT 1
            """,
            (collection, document_source),
        )
        return cur.fetchone() is not None
    finally:
        cur.close()


def inspect_pdf_embedding_state(
    conn,
    collection: str,
    document_source: str,
    brand: str,
    model_subbrand: str,
    *,
    expected_page_count: int | None = None,
) -> str:
    """
    Returns:
    - missing: no rows for this source
    - matching_page_summary: already embedded with the new page-level pipeline
    - partial_page_summary: some pages are fully committed and some are not
    - stale_or_mismatched: legacy rows or different metadata scope
    """
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT DISTINCT
                COALESCE(metadata->>'chunk_type', ''),
                brand,
                model_subbrand
            FROM documents
            WHERE collection = %s AND document_source = %s
            """,
            (collection, document_source),
        )
        rows = cur.fetchall()
        if not rows:
            legacy_source = get_display_source_name(document_source)
            if legacy_source and legacy_source != document_source:
                cur.execute(
                    """
                    SELECT 1
                    FROM documents
                    WHERE collection = %s
                      AND document_source = %s
                      AND brand = %s
                      AND model_subbrand = %s
                      AND COALESCE(metadata->>'source_id', '') = ''
                    LIMIT 1
                    """,
                    (collection, legacy_source, brand, model_subbrand),
                )
                if cur.fetchone():
                    return "stale_or_mismatched"
            return "missing"

        chunk_types = {row[0] for row in rows}
        brands = {normalize_scope_value(row[1]) for row in rows}
        models = {normalize_scope_value(row[2]) for row in rows}

        valid_chunk_types = {"page_summary", "page_unreadable"}
        if chunk_types.issubset(valid_chunk_types) and brands == {brand} and models == {model_subbrand}:
            if expected_page_count is None:
                return "partial_page_summary"
            completed_pages = get_completed_pdf_pages(
                conn,
                collection,
                document_source,
                brand,
                model_subbrand,
            )
            if len(completed_pages) >= expected_page_count:
                return "matching_page_summary"
            return "partial_page_summary"
        return "stale_or_mismatched"
    finally:
        cur.close()


def get_completed_pdf_pages(
    conn,
    collection: str,
    document_source: str,
    brand: str,
    model_subbrand: str,
) -> set[int]:
    """
    A page is considered complete only if both the vector row and page image row exist.
    """
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT page_number
            FROM documents
            WHERE collection = %s
              AND document_source = %s
              AND brand = %s
              AND model_subbrand = %s
              AND COALESCE(metadata->>'chunk_type', '') IN ('page_summary', 'page_unreadable')
            """,
            (collection, document_source, brand, model_subbrand),
        )
        document_pages = {int(row[0]) for row in cur.fetchall()}

        cur.execute(
            """
            SELECT page_number
            FROM pdf_pages
            WHERE collection_name = %s
              AND document_source = %s
              AND brand = %s
              AND model_subbrand = %s
            """,
            (collection, document_source, brand, model_subbrand),
        )
        image_pages = {int(row[0]) for row in cur.fetchall()}
        return document_pages & image_pages
    finally:
        cur.close()


def delete_existing_source_records(conn, document_source: str, collection: str) -> None:
    legacy_source = get_display_source_name(document_source)
    cur = conn.cursor()
    try:
        cur.execute(
            """
            DELETE FROM documents
            WHERE collection = %s
              AND (
                    document_source = %s
                    OR (
                        document_source = %s
                        AND COALESCE(metadata->>'source_id', '') = ''
                    )
                  )
            """,
            (collection, document_source, legacy_source),
        )
        delete_page_images(conn, document_source, collection, legacy_source=legacy_source, commit=False)
    finally:
        cur.close()


def attach_scope_metadata(
    chunks: List[Document],
    *,
    document_source: str,
    brand: str,
    model_subbrand: str,
) -> List[Document]:
    source_id = normalize_document_source(document_source)
    display_source = get_display_source_name(source_id)
    for chunk in chunks:
        metadata = dict(chunk.metadata or {})
        metadata["source"] = metadata.get("source") or display_source
        metadata["source_id"] = metadata.get("source_id") or source_id
        metadata["page"] = int(metadata.get("page", 0) or 0)
        metadata["brand"] = brand
        metadata["model_subbrand"] = model_subbrand
        metadata.setdefault("char_count", len(chunk.page_content))
        metadata.setdefault("word_count", len(chunk.page_content.split()))
        chunk.metadata = metadata
    return chunks


def detect_page_type_hint(page_asset: dict) -> str:
    raw_text = str(page_asset.get("text") or "")
    normalized_text = normalize_summary_text(raw_text)
    lowered = normalized_text.lower()
    if not lowered:
        return "blank_or_unreadable"

    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    dot_leader_count = len(_CONTENTS_DOT_LEADER_RE.findall(raw_text))
    heading_count = len(_HEADING_TOKEN_RE.findall(raw_text))
    short_line_count = sum(1 for line in lines if len(line.split()) <= 10)

    if "introduction" in lowered and ("this manual describes" in lowered or "target modules" in lowered):
        return "introduction"
    if "regarding use of this product" in lowered or "before using the product for special purposes" in lowered:
        return "introduction"
    if "table of contents" in lowered or ("contents" in lowered and dot_leader_count >= 3):
        return "table_of_contents"
    if "contents" in lowered and heading_count >= 4:
        return "table_of_contents"
    if dot_leader_count >= 8 and heading_count >= 8:
        return "table_of_contents"
    if "relevant manuals" in lowered or "manual name [manual number]" in lowered:
        return "manual_list"
    if "generic terms and abbreviations" in lowered or "term description" in lowered:
        return "glossary_list"
    if dot_leader_count >= 6 and short_line_count >= 6:
        return "table_of_contents"
    return "normal_content"


def build_page_type_guidance(page_type_hint: str) -> str:
    if page_type_hint == "introduction":
        return (
            "This page appears to be an introduction or scope page. "
            "Extract only visible routing signals such as the section title, manual title, target module families, warning labels, and note headings. "
            "If the page contains a long or dense target-module list, do not copy exact model numbers from that list. Keep only the higher-level family names or group labels that are clearly readable. "
            "Do not invent model numbers or expand partial lists."
        )
    if page_type_hint == "table_of_contents":
        return (
            "This page appears to be a table of contents or section listing. "
            "Extract only visible section headings, labels, and page numbers. "
            "Include several visible entries when available. "
            "Do not expand the listed sections into chapter descriptions or infer their contents."
        )
    if page_type_hint == "manual_list":
        return (
            "This page appears to be a manual list or reference list. "
            "Extract only the manual titles, manual numbers, and short descriptions that are visibly printed on this page. "
            "Do not add descriptions that are not explicitly shown."
        )
    if page_type_hint == "glossary_list":
        return (
            "This page appears to be a glossary or abbreviation list. "
            "Extract only the visible terms and their definitions or descriptions shown on this page."
        )
    return (
        "Extract only routing signals that are directly visible on this page, especially headings, labels, warnings, model names, connector names, commands, table headers, and distinctive technical terms. "
        "If small text or dense lists are hard to read, keep only high-confidence visible terms instead of guessing. "
        "Do not infer details from headings alone."
    )


def summarize_pdf_page(
    summary_llm,
    page_asset: dict,
    *,
    document_source: str,
    display_source: str,
    brand: str,
    model_subbrand: str,
) -> str:
    page_type_hint = detect_page_type_hint(page_asset)
    page_type_guidance = build_page_type_guidance(page_type_hint)
    visually_blank = is_visually_blank_page(page_asset) if page_type_hint == "blank_or_unreadable" else False
    if page_type_hint == "blank_or_unreadable" and (
        len(page_asset.get("image_data", b"")) <= BLANK_PAGE_IMAGE_MAX_BYTES or visually_blank
    ):
        logging.info(
            "Skipping summary call for %s page %d because it appears blank/unreadable (%.1f KB, visually_blank=%s)",
            display_source,
            page_asset["page_number"],
            len(page_asset.get("image_data", b"")) / 1024.0,
            visually_blank,
        )
        return NO_READABLE_CONTENT_TOKEN
    prompt = f"""
You are preparing a single searchable retrieval note for one technical manual PDF page.

Return exactly one plain-text retrieval note optimized for vector search.
Prefer short exact phrases separated by semicolons instead of long prose.
Keep only visible page-routing signals, especially:
- section titles, chapter titles, table titles, headings
- brand names, product names, model numbers, subbrands
- commands, registers, parameters, protocols, ports, menus, labels
- warnings, cautions, error codes, connector names, table headers
- manual numbers, glossary terms, page numbers on contents pages

Do not invent information.
Do not explain or expand items beyond what is visible.
Do not mention that this is a summary or retrieval note.
Do not use bullets or markdown.
Preserve the original language of the page exactly as seen.
Preserve exact model names, labels, numbers, and accented characters.
Keep the note concise and information-dense.
If tiny text, dense lists, or repeated model numbers are uncertain, omit them rather than guessing.
Prefer a few high-confidence exact identifiers over a long uncertain list.
Limit the note to about 12 semicolon-separated items or fewer.
If the page is blank, unreadable, or does not contain readable technical content, return exactly {NO_READABLE_CONTENT_TOKEN}.

Page Type Hint: {page_type_hint}
Page-Type Guidance: {page_type_guidance}
Brand: {brand}
Model/Subbrand: {model_subbrand}
Source File: {display_source}
Page Number: {page_asset["page_number"]}
""".strip()

    content_parts = [{"type": "text", "text": prompt}]
    summary_asset = page_asset
    if SUMMARY_INCLUDE_PAGE_IMAGE:
        summary_asset = build_summary_page_asset(page_asset)
        content_parts.extend(build_openai_compatible_image_parts([summary_asset]))

    image_size = summary_asset.get("summary_image_size")
    original_size = summary_asset.get("summary_image_original_size")
    if image_size and original_size:
        logging.info(
            "Summarizing %s page %d with resized image %sx%s (from %sx%s, %.1f KB)",
            display_source,
            page_asset["page_number"],
            image_size[0],
            image_size[1],
            original_size[0],
            original_size[1],
            len(summary_asset["image_data"]) / 1024.0,
        )
    else:
        logging.info(
            "Summarizing %s page %d with image %.1f KB",
            display_source,
            page_asset["page_number"],
            len(summary_asset.get("image_data", b"")) / 1024.0,
        )

    started_at = time.perf_counter()
    response = call_llm_with_retry(
        lambda: summary_llm.invoke([HumanMessage(content=content_parts)]),
        max_retries=2,
        base_wait=1.0,
    )
    logging.info(
        "Summary call finished for %s page %d in %.1fs",
        display_source,
        page_asset["page_number"],
        time.perf_counter() - started_at,
    )
    summary = normalize_summary_text(extract_text_from_llm_response(response))
    summary = filter_retrieval_note_by_page_text(summary, page_asset, page_type_hint)
    if not summary:
        raise ValueError(f"Summary model returned empty output for {display_source} page {page_asset['page_number']}")
    return summary


def build_pdf_page_summary_chunk(
    summary_llm,
    page_asset: dict,
    *,
    document_source: str,
    display_source: str,
    brand: str,
    model_subbrand: str,
) -> Document:
    page_type_hint = detect_page_type_hint(page_asset)
    summary_text = summarize_pdf_page(
        summary_llm,
        page_asset,
        document_source=document_source,
        display_source=display_source,
        brand=brand,
        model_subbrand=model_subbrand,
    )
    unreadable = summary_text == NO_READABLE_CONTENT_TOKEN
    stored_text = summary_text if not unreadable else "No readable content detected on this page."
    return Document(
        page_content=stored_text,
        metadata={
            "source": display_source,
            "source_id": document_source,
            "page": page_asset["page_number"],
            "brand": brand,
            "model_subbrand": model_subbrand,
            "page_type_hint": page_type_hint,
            "chunk_type": "page_unreadable" if unreadable else "page_summary",
            "readable": not unreadable,
            "char_count": len(stored_text),
            "word_count": len(stored_text.split()),
        },
    )


def main():
    parser = argparse.ArgumentParser(
        description="Embed documents into pgvector and store rendered PDF pages with matching metadata."
    )
    parser.add_argument("files", nargs="+", help="Path(s) to PDF/JSON file(s) or folder(s) to embed.")
    parser.add_argument("--brand", required=True, help="Brand name to attach to every embedded file in this run.")
    parser.add_argument(
        "--model-subbrand",
        "--model",
        dest="model_subbrand",
        required=True,
        help="Model or subbrand to attach to every embedded file in this run.",
    )
    parser.add_argument("--collection", default="plcnext", help="Collection name.")
    parser.add_argument("--batch-size", type=int, default=1000, help="Embeddings per batch.")
    parser.add_argument("--model-cache", default="/app/models", help="Model cache directory.")
    parser.add_argument("--summary-model", default=DEFAULT_SUMMARY_MODEL, help="Page summary model name.")
    parser.add_argument("--dry-run", action="store_true", help="Parse files without summarizing, embedding, or saving.")
    parser.add_argument(
        "--replace-existing",
        action="store_true",
        help="Force re-embedding even if the file already exists in the collection.",
    )
    parser.add_argument(
        "--include-golden-qa",
        action="store_true",
        help="Include Golden QA JSON files in embedding (disabled by default for unbiased eval).",
    )
    args = parser.parse_args()

    if not DB_URL and not args.dry_run:
        raise RuntimeError("DATABASE_URL environment variable is required.")

    brand = normalize_scope_value(args.brand)
    model_subbrand = normalize_scope_value(args.model_subbrand)
    if not brand:
        raise ValueError("--brand is required.")
    if not model_subbrand:
        raise ValueError("--model-subbrand/--model is required.")

    all_files = get_files(args.files)
    if not args.include_golden_qa:
        filtered_files = []
        skipped = []
        for path in all_files:
            if is_golden_qa_file(path):
                skipped.append(path)
            else:
                filtered_files.append(path)
        all_files = filtered_files
        if skipped:
            logging.info(
                "Skipping %d Golden QA file(s) (eval-only mode). Use --include-golden-qa to embed them.",
                len(skipped),
            )

    if not all_files:
        logging.error("No PDF/JSON files found.")
        raise SystemExit(1)

    logging.info("Found %d files to process", len(all_files))
    logging.info("Embedding scope: brand='%s' model_subbrand='%s'", brand, model_subbrand)

    if args.dry_run:
        logging.info("DRY RUN MODE - will inspect files only")

    device = get_device()

    embedder = None
    summary_llm = None
    conn = None

    total_vector_rows = 0
    total_image_pages = 0
    total_chunks_created = 0
    total_files_processed = 0

    if not args.dry_run:
        logging.info("Loading embedding model: %s", EMBED_MODEL)
        embedder = SentenceTransformer(EMBED_MODEL, device=device, cache_folder=args.model_cache)
        logging.info("Embedding model loaded on %s", device)

        conn = psycopg2.connect(DB_URL)
        ensure_storage_schema(conn)

        if any(path.lower().endswith(".pdf") for path in all_files):
            logging.info("Loading page summary model: %s", args.summary_model)
            summary_llm = create_summary_llm(args.summary_model)

    try:
        for file_idx, file_path in enumerate(tqdm(all_files, desc="Processing files", unit="file"), start=1):
            if not os.path.exists(file_path):
                logging.warning("File not found: %s", file_path)
                continue

            document_source = normalize_document_source(file_path)
            filename = get_display_source_name(document_source)
            is_pdf = file_path.lower().endswith(".pdf")

            if not args.dry_run and is_pdf:
                state = inspect_pdf_embedding_state(conn, args.collection, document_source, brand, model_subbrand)
                if state == "matching_page_summary" and not args.replace_existing:
                    logging.info("[%d/%d] Skipping %s (already embedded with matching page summaries)", file_idx, len(all_files), filename)
                    continue

            if not args.dry_run and not is_pdf and source_exists(conn, args.collection, document_source) and not args.replace_existing:
                logging.info("[%d/%d] Skipping %s (already embedded)", file_idx, len(all_files), filename)
                continue

            try:
                if is_pdf:
                    page_count = get_pdf_page_count(file_path)
                    total_chunks_created += page_count
                    total_files_processed += 1
                    logging.info("[%d/%d] %s: %d pages", file_idx, len(all_files), filename, page_count)

                    if args.dry_run:
                        continue

                    if page_count <= 0:
                        logging.warning("Skipping %s because no pages could be extracted", filename)
                        continue

                    state = inspect_pdf_embedding_state(
                        conn,
                        args.collection,
                        document_source,
                        brand,
                        model_subbrand,
                        expected_page_count=page_count,
                    )
                    if state == "matching_page_summary" and not args.replace_existing:
                        logging.info(
                            "[%d/%d] Skipping %s (all pages already embedded)",
                            file_idx,
                            len(all_files),
                            filename,
                        )
                        continue

                    completed_pages: set[int] = set()
                    if args.replace_existing or state == "stale_or_mismatched":
                        delete_existing_source_records(conn, document_source, args.collection)
                    elif state == "partial_page_summary":
                        completed_pages = get_completed_pdf_pages(
                            conn,
                            args.collection,
                            document_source,
                            brand,
                            model_subbrand,
                        )
                        logging.info(
                            "Resuming %s: %d/%d pages already committed",
                            filename,
                            len(completed_pages),
                            page_count,
                        )

                    start_page = 1
                    if completed_pages:
                        highest_completed = max(completed_pages)
                        contiguous_pages = set(range(1, highest_completed + 1))
                        if completed_pages == contiguous_pages:
                            start_page = highest_completed + 1
                            if start_page <= page_count:
                                logging.info(
                                    "Fast resume for %s: starting from page %d",
                                    filename,
                                    start_page,
                                )

                    desc = f"Embedding {filename}"
                    remaining_pages = max(page_count - start_page + 1, 0)
                    page_stream = iter_pdf_page_assets(file_path, dpi=PAGE_IMAGE_DPI, start_page=start_page)
                    for page_asset in tqdm(page_stream, total=remaining_pages, desc=desc, unit="page", leave=False):
                        page_number = int(page_asset["page_number"])
                        if page_number in completed_pages and not args.replace_existing:
                            continue

                        page_started_at = time.perf_counter()
                        logging.info(
                            "Starting %s page %d/%d",
                            filename,
                            page_number,
                            page_count,
                        )
                        page_chunk = build_pdf_page_summary_chunk(
                            summary_llm,
                            page_asset,
                            document_source=document_source,
                            display_source=filename,
                            brand=brand,
                            model_subbrand=model_subbrand,
                        )

                        try:
                            total_vector_rows += flush_chunks(
                                [page_chunk],
                                embedder,
                                conn,
                                args.collection,
                                commit=False,
                            )
                            total_image_pages += store_page_images(
                                conn,
                                [page_asset["image_data"]],
                                document_source,
                                args.collection,
                                brand=brand,
                                model_subbrand=model_subbrand,
                                page_metadata=[dict(page_chunk.metadata or {})],
                                commit=False,
                            )
                            conn.commit()
                            completed_pages.add(page_number)
                            logging.info(
                                "Committed %s page %d/%d in %.1fs",
                                filename,
                                page_number,
                                page_count,
                                time.perf_counter() - page_started_at,
                            )
                        except Exception:
                            conn.rollback()
                            raise
                else:
                    json_chunks = attach_scope_metadata(
                        create_json_qa_chunks(file_path),
                        document_source=document_source,
                        brand=brand,
                        model_subbrand=model_subbrand,
                    )
                    total_chunks_created += len(json_chunks)
                    total_files_processed += 1
                    logging.info("[%d/%d] %s: %d chunks", file_idx, len(all_files), filename, len(json_chunks))

                    if args.dry_run:
                        continue

                    try:
                        if args.replace_existing and source_exists(conn, args.collection, document_source):
                            delete_existing_source_records(conn, document_source, args.collection)

                        for batch in iter_batches(json_chunks, args.batch_size):
                            total_vector_rows += flush_chunks(
                                batch,
                                embedder,
                                conn,
                                args.collection,
                                commit=False,
                            )
                        conn.commit()
                    except Exception:
                        conn.rollback()
                        raise
            except Exception as e:
                logging.error("Failed to process %s: %s", file_path, e, exc_info=True)

        if args.dry_run:
            logging.info(
                "DRY RUN COMPLETE: Would create %d vector chunks/page summaries from %d files",
                total_chunks_created,
                total_files_processed,
            )
        else:
            logging.info(
                "Done! Stored %d vector rows and %d page images from %d files",
                total_vector_rows,
                total_image_pages,
                total_files_processed,
            )
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    main()
