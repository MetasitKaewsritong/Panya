"""
Context Preparation Module for PDF Page Image RAG

This module handles extracting unique pages from selected chunks
and fetching corresponding page images from the database.
"""
import logging
import os
import re
import io
from typing import List, Dict, Any, Optional
from langchain_core.documents import Document
import time
import fitz
from PIL import Image
import pytesseract

logger = logging.getLogger(__name__)

_PDF_SEARCH_DIRS = ["/app/data/Knowledge", "/app/data/knowledge"]
_PDF_TEXT_CACHE: Dict[str, List[str]] = {}
_PDF_RAW_TEXT_CACHE: Dict[str, List[str]] = {}
_PDF_PATH_CACHE: Dict[str, Optional[str]] = {}
_TOKEN_PATTERN = re.compile(r"[a-z0-9\-]{4,}", re.IGNORECASE)
_QUERY_TOKEN_PATTERN = re.compile(r"[a-z0-9][a-z0-9\-]{1,}", re.IGNORECASE)
_STOPWORDS = {
    "with", "from", "that", "this", "only", "using", "into", "where", "which",
    "unit", "series", "guide", "manual", "command", "data", "computer", "adapter",
}
_QUERY_RERANK_STOPWORDS = {
    "about",
    "does",
    "from",
    "have",
    "how",
    "info",
    "information",
    "manual",
    "module",
    "page",
    "should",
    "tell",
    "that",
    "the",
    "their",
    "there",
    "these",
    "they",
    "what",
    "when",
    "where",
    "which",
    "with",
    "your",
}


def _normalize(text: str) -> str:
    return " ".join((text or "").lower().split())


def _display_source_name(source_value: str) -> str:
    cleaned = str(source_value or "").replace("\\", "/").rstrip("/")
    if not cleaned:
        return ""
    return cleaned.rsplit("/", 1)[-1]


def _find_pdf_path(source: str, source_id: Optional[str] = None) -> Optional[str]:
    cache_key = source_id or source
    if cache_key in _PDF_PATH_CACHE:
        return _PDF_PATH_CACHE[cache_key]
    if source_id and os.path.exists(source_id):
        _PDF_PATH_CACHE[cache_key] = source_id
        return source_id
    for base in _PDF_SEARCH_DIRS:
        candidate = os.path.join(base, _display_source_name(source_id or source))
        if os.path.exists(candidate):
            _PDF_PATH_CACHE[cache_key] = candidate
            return candidate
    _PDF_PATH_CACHE[cache_key] = None
    return None


def _get_pdf_page_texts(source: str, source_id: Optional[str] = None) -> List[str]:
    cache_key = source_id or source
    if cache_key in _PDF_TEXT_CACHE:
        return _PDF_TEXT_CACHE[cache_key]
    raw_page_texts = _get_pdf_page_raw_texts(source, source_id=source_id)
    page_texts = [_normalize(text) for text in raw_page_texts]
    _PDF_TEXT_CACHE[cache_key] = page_texts
    return page_texts


def _get_pdf_page_raw_texts(source: str, source_id: Optional[str] = None) -> List[str]:
    cache_key = source_id or source
    if cache_key in _PDF_RAW_TEXT_CACHE:
        return _PDF_RAW_TEXT_CACHE[cache_key]
    path = _find_pdf_path(source, source_id=source_id)
    if not path:
        _PDF_RAW_TEXT_CACHE[cache_key] = []
        return []
    try:
        doc = fitz.open(path)
        page_texts = [(page.get_text("text") or "") for page in doc]
        _PDF_RAW_TEXT_CACHE[cache_key] = page_texts
        return page_texts
    except Exception as e:
        logger.warning(f"⚠️ Could not read PDF text for page resolution ({source}): {e}")
        _PDF_RAW_TEXT_CACHE[cache_key] = []
        return []


def _resolve_pdf_page(source: str, source_id: Optional[str], chunk_text: str, current_page: Optional[int]) -> Optional[int]:
    """
    Resolve the best physical PDF page from chunk text to mitigate metadata page drift.
    """
    source_key = source_id or source
    if not source_key or not source_key.lower().endswith(".pdf"):
        return current_page
    page_texts = _get_pdf_page_texts(source, source_id=source_id)
    if not page_texts:
        return current_page

    tokens = []
    for tok in _TOKEN_PATTERN.findall(_normalize(chunk_text)):
        if tok not in _STOPWORDS:
            tokens.append(tok)
    if not tokens:
        return current_page
    tokens = tokens[:40]

    scores = [sum(1 for tok in tokens if tok in page_text) for page_text in page_texts]
    best_idx = max(range(len(scores)), key=lambda i: scores[i])
    best_score = scores[best_idx]
    best_page = best_idx + 1

    # Keep metadata page if it is already close in confidence.
    if current_page and 1 <= current_page <= len(scores):
        current_score = scores[current_page - 1]
        if current_score >= best_score - 1:
            return current_page

    # Guard against noisy remaps.
    if best_score < 6:
        return current_page
    return best_page


def extract_unique_pages(selected_docs: List[Document]) -> List[Dict[str, Any]]:
    """
    Extract unique pages from selected chunks with deduplication.
    
    When multiple chunks come from the same page, we keep the highest score
    for that page and deduplicate.
    
    Args:
        selected_docs: List of Document objects with metadata containing:
                      - source: document filename
                      - page: page number (1-indexed)
                      - score: relevance score
    
    Returns:
        List of dicts with {source, page, brand, model_subbrand, score}
        sorted by score (descending)
    """
    page_map = {}  # Key: (source_id, source, page, brand, model_subbrand), Value: max_score
    
    for doc in selected_docs:
        source = doc.metadata.get('source')
        source_id = doc.metadata.get('source_id') or source
        page = doc.metadata.get('page')
        score = doc.metadata.get('score', 0.0)
        brand = doc.metadata.get('brand', '')
        model_subbrand = doc.metadata.get('model_subbrand', '')
        
        # Validate metadata
        if not source:
            logger.warning(f"⚠️ Skipping chunk with missing source")
            continue
        
        resolved_page = _resolve_pdf_page(source, source_id, doc.page_content, page)
        if resolved_page != page:
            logger.debug(f"🔎 Page remap for {source}: {page} -> {resolved_page}")
        page = resolved_page

        if not page or page == 0:
            logger.warning(f"⚠️ Skipping chunk from {source} with invalid page number: {page}")
            continue
        
        # Deduplicate: keep highest score for each (source, page) pair
        key = (source_id, source, page, brand, model_subbrand)
        if key not in page_map or score > page_map[key]:
            page_map[key] = score
    
    # Convert to list and sort by score (descending)
    unique_pages = [
        {
            'source': source,
            'source_id': source_id,
            'page': page,
            'brand': brand,
            'model_subbrand': model_subbrand,
            'score': score,
        }
        for (source_id, source, page, brand, model_subbrand), score in page_map.items()
    ]
    unique_pages.sort(key=lambda x: x['score'], reverse=True)
    
    logger.info(f"📄 Extracted {len(unique_pages)} unique pages from {len(selected_docs)} chunks")
    
    # Log page details for debugging
    if unique_pages:
        page_summary = ", ".join([f"{p['source']}:p{p['page']}" for p in unique_pages[:5]])
        if len(unique_pages) > 5:
            page_summary += f", ... (+{len(unique_pages) - 5} more)"
        logger.debug(f"   Pages: {page_summary}")
    
    return unique_pages


def fetch_page_images(
    conn_pool,
    pages: List[Dict[str, Any]],
    collection: str
) -> List[Dict[str, Any]]:
    """
    Fetch PDF page images from database.
    
    Args:
        conn_pool: Database connection pool (psycopg2.pool)
        pages: List of {source, page, score} dicts
        collection: Collection name (e.g., "plcnext")
    
    Returns:
        List of dicts with {source, page, score, image_data}
        Only includes pages where images were successfully fetched.
    """
    if not pages:
        return []
    
    t_start = time.perf_counter()
    
    conn = conn_pool.getconn()
    try:
        cur = conn.cursor()
        
        # Build query for batch fetch (more efficient than individual queries)
        conditions = []
        params = []
        for p in pages:
            conditions.append(
                "(document_source = %s AND page_number = %s AND brand = %s AND model_subbrand = %s)"
            )
            params.extend([p.get('source_id') or p['source'], p['page'], p.get('brand', ''), p.get('model_subbrand', '')])
        params.append(collection)
        
        query = f"""
            SELECT document_source, page_number, brand, model_subbrand, image_data
            FROM pdf_pages
            WHERE ({' OR '.join(conditions)})
            AND collection_name = %s
        """
        
        cur.execute(query, params)
        rows = cur.fetchall()
        cur.close()
        
        # Map results back to pages
        image_map = {(row[0], row[1], row[2], row[3]): row[4] for row in rows}
        
        results = []
        missing_pages = []
        
        for p in pages:
            source_key = p.get('source_id') or p['source']
            key = (source_key, p['page'], p.get('brand', ''), p.get('model_subbrand', ''))
            if key in image_map:
                results.append({
                    'source': p['source'],
                    'source_id': source_key,
                    'page': p['page'],
                    'brand': p.get('brand', ''),
                    'model_subbrand': p.get('model_subbrand', ''),
                    'score': p['score'],
                    'image_data': image_map[key]
                })
            else:
                missing_pages.append(
                    f"{source_key}:p{p['page']}:{p.get('brand', '')}:{p.get('model_subbrand', '')}"
                )
        
        t_elapsed = time.perf_counter() - t_start
        
        logger.info(f"✅ Fetched {len(results)}/{len(pages)} page images in {t_elapsed*1000:.0f}ms")
        
        if missing_pages:
            logger.warning(f"⚠️ Missing page images: {', '.join(missing_pages[:5])}")
            if len(missing_pages) > 5:
                logger.warning(f"   ... and {len(missing_pages) - 5} more")
        
        return results
        
    except Exception as e:
        logger.error(f"❌ Error fetching page images: {e}")
        return []
    finally:
        conn_pool.putconn(conn)


def prepare_page_context(
    selected_docs: List[Document],
    conn_pool,
    collection: str
) -> Optional[List[Dict[str, Any]]]:
    """
    Main function: Extract unique pages and fetch their images.
    
    This is the primary entry point for converting selected text chunks
    into page images for vision LLM context.
    
    Args:
        selected_docs: Selected chunks from retrieval (with metadata)
        conn_pool: Database connection pool
        collection: Collection name
    
    Returns:
        List of page dicts with image_data, or None if no pages found
        Each dict contains: {source, page, score, image_data}
    """
    if not selected_docs:
        logger.warning("⚠️ No selected documents provided")
        return None
    
    # Step 1: Extract unique pages with deduplication
    unique_pages = extract_unique_pages(selected_docs)
    
    if not unique_pages:
        logger.warning("⚠️ No valid pages found in selected chunks")
        return None
    
    # Step 2: Fetch page images from database
    page_images = fetch_page_images(conn_pool, unique_pages, collection)
    
    if not page_images:
        logger.error("❌ Failed to fetch any page images")
        return None
    
    # Log summary
    total_size_mb = sum(len(p['image_data']) for p in page_images) / (1024 * 1024)
    logger.info(f"📦 Prepared {len(page_images)} page images ({total_size_mb:.1f} MB) for vision LLM")
    
    return page_images


def _sanitize_ocr_text(text: str) -> str:
    cleaned = (text or "").replace("\x0c", " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _tokenize_query_for_source_rerank(query: str) -> List[str]:
    if not query:
        return []

    tokens: List[str] = []
    for token in _QUERY_TOKEN_PATTERN.findall((query or "").lower()):
        compact = re.sub(r"[^a-z0-9]+", "", token.lower())
        if not compact:
            continue
        if compact in _QUERY_RERANK_STOPWORDS:
            continue
        if len(compact) < 3 and not any(ch.isdigit() for ch in compact):
            continue
        tokens.append(compact)
    return list(dict.fromkeys(tokens))


def boost_docs_with_source_page_text(
    docs: List[Document],
    query: str,
    *,
    max_bonus: float = 0.35,
) -> List[Document]:
    """
    Re-rank retrieved docs using the original PDF page text when available.

    The vector store uses short page summaries for retrieval. This helper adds a
    small score bonus when the real source page text matches the query more
    directly, which helps tables/spec pages beat nearby-but-wrong summary pages.
    """
    if not docs or not query:
        return docs

    query_tokens = _tokenize_query_for_source_rerank(query)
    if not query_tokens:
        return docs

    identifier_tokens = [token for token in query_tokens if any(ch.isdigit() for ch in token)]
    rescored = False

    for doc in docs:
        metadata = doc.metadata or {}
        source = metadata.get("source", "")
        source_id = metadata.get("source_id") or source
        page_num = int(metadata.get("page", 0) or 0)
        if not source or page_num <= 0:
            continue

        raw_page_texts = _get_pdf_page_raw_texts(source, source_id=source_id)
        if page_num > len(raw_page_texts):
            continue

        page_text = _normalize(raw_page_texts[page_num - 1])
        if not page_text:
            continue

        token_hits = sum(1 for token in query_tokens if token in page_text)
        if token_hits <= 0:
            continue

        coverage = token_hits / len(query_tokens)
        identifier_hits = sum(1 for token in identifier_tokens if token in page_text)
        identifier_coverage = (identifier_hits / len(identifier_tokens)) if identifier_tokens else 0.0

        bonus = min(max_bonus, (coverage * 0.20) + (identifier_coverage * 0.15))
        if bonus <= 0:
            continue

        base_score = float(metadata.get("score") or 0.0)
        metadata["source_text_bonus"] = round(bonus, 4)
        metadata["score"] = base_score + bonus
        rescored = True

    if not rescored:
        return docs

    docs.sort(key=lambda doc: float((doc.metadata or {}).get("score") or 0.0), reverse=True)
    logger.info(
        "Applied source-page text rerank to %d docs for query '%s'",
        len(docs),
        (query or "")[:120],
    )
    return docs


def extract_ocr_contexts(
    page_images: List[Dict[str, Any]],
    max_pages: Optional[int] = None,
    max_chars: Optional[int] = None,
) -> List[str]:
    """
    OCR page images to text contexts for fairer RAGAS evaluation in vision mode.

    Returns a list of context strings; each item includes source/page metadata.
    Falls back to empty list on OCR failure.
    """
    if not page_images:
        return []

    if max_pages is None:
        try:
            max_pages = int(os.getenv("RAGAS_OCR_MAX_PAGES", "3"))
        except Exception:
            max_pages = 3
    if max_chars is None:
        try:
            max_chars = int(os.getenv("RAGAS_OCR_MAX_CHARS", "1800"))
        except Exception:
            max_chars = 1800

    contexts: List[str] = []
    pages_to_process = page_images[: max(1, max_pages)]

    for page in pages_to_process:
        source = page.get("source", "Unknown")
        page_num = page.get("page", "N/A")
        image_bytes = page.get("image_data")
        if not image_bytes:
            continue
        try:
            image = Image.open(io.BytesIO(image_bytes))
            text = pytesseract.image_to_string(image)
            text = _sanitize_ocr_text(text)
            if not text:
                continue
            if max_chars > 0 and len(text) > max_chars:
                text = text[:max_chars]
            contexts.append(f"[Source: {source} | Page: {page_num}] {text}")
        except Exception as e:
            logger.warning("⚠️ OCR failed for %s page %s: %s", source, page_num, e)

    logger.info("🧾 OCR extracted %d/%d page contexts for RAGAS", len(contexts), len(pages_to_process))
    return contexts


def extract_source_page_contexts(
    selected_docs: List[Document],
    max_pages: Optional[int] = None,
    max_chars: Optional[int] = None,
) -> List[str]:
    """
    Build evaluation contexts directly from the original PDF page text.

    This is more trustworthy than OCR or page-summary notes when the original
    source page is available, because it reflects the exact manual content.
    """
    if not selected_docs:
        return []

    if max_pages is None:
        try:
            max_pages = int(os.getenv("RAGAS_SOURCE_TEXT_MAX_PAGES", "3"))
        except Exception:
            max_pages = 3
    if max_chars is None:
        try:
            max_chars = int(os.getenv("RAGAS_SOURCE_TEXT_MAX_CHARS", "2400"))
        except Exception:
            max_chars = 2400

    unique_pages = extract_unique_pages(selected_docs)
    if not unique_pages:
        return []

    contexts: List[str] = []
    pages_to_process = unique_pages[: max(1, max_pages)]

    for page in pages_to_process:
        source = page.get("source", "Unknown")
        source_id = page.get("source_id") or source
        page_num = int(page.get("page", 0) or 0)
        if page_num <= 0:
            continue

        raw_page_texts = _get_pdf_page_raw_texts(source, source_id=source_id)
        if page_num > len(raw_page_texts):
            continue

        text = _sanitize_ocr_text(raw_page_texts[page_num - 1])
        if not text:
            continue
        if max_chars > 0 and len(text) > max_chars:
            text = text[:max_chars]

        contexts.append(f"[Source: {source} | Page: {page_num}] {text}")

    logger.info(
        "Prepared %d/%d exact source-page contexts for RAGAS",
        len(contexts),
        len(pages_to_process),
    )
    return contexts
