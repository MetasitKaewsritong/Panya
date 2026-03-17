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
_PDF_PATH_CACHE: Dict[str, Optional[str]] = {}
_TOKEN_PATTERN = re.compile(r"[a-z0-9\-]{4,}", re.IGNORECASE)
_STOPWORDS = {
    "with", "from", "that", "this", "only", "using", "into", "where", "which",
    "unit", "series", "guide", "manual", "command", "data", "computer", "adapter",
}


def _normalize(text: str) -> str:
    return " ".join((text or "").lower().split())


def _find_pdf_path(source: str) -> Optional[str]:
    if source in _PDF_PATH_CACHE:
        return _PDF_PATH_CACHE[source]
    for base in _PDF_SEARCH_DIRS:
        candidate = os.path.join(base, source)
        if os.path.exists(candidate):
            _PDF_PATH_CACHE[source] = candidate
            return candidate
    _PDF_PATH_CACHE[source] = None
    return None


def _get_pdf_page_texts(source: str) -> List[str]:
    if source in _PDF_TEXT_CACHE:
        return _PDF_TEXT_CACHE[source]
    path = _find_pdf_path(source)
    if not path:
        _PDF_TEXT_CACHE[source] = []
        return []
    try:
        doc = fitz.open(path)
        page_texts = [_normalize(page.get_text()) for page in doc]
        _PDF_TEXT_CACHE[source] = page_texts
        return page_texts
    except Exception as e:
        logger.warning(f"⚠️ Could not read PDF text for page resolution ({source}): {e}")
        _PDF_TEXT_CACHE[source] = []
        return []


def _resolve_pdf_page(source: str, chunk_text: str, current_page: Optional[int]) -> Optional[int]:
    """
    Resolve the best physical PDF page from chunk text to mitigate metadata page drift.
    """
    if not source or not source.lower().endswith(".pdf"):
        return current_page
    page_texts = _get_pdf_page_texts(source)
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
        List of dicts with {source, page, score} sorted by score (descending)
    """
    page_map = {}  # Key: (source, page), Value: max_score
    
    for doc in selected_docs:
        source = doc.metadata.get('source')
        page = doc.metadata.get('page')
        score = doc.metadata.get('score', 0.0)
        
        # Validate metadata
        if not source:
            logger.warning(f"⚠️ Skipping chunk with missing source")
            continue
        
        resolved_page = _resolve_pdf_page(source, doc.page_content, page)
        if resolved_page != page:
            logger.debug(f"🔎 Page remap for {source}: {page} -> {resolved_page}")
        page = resolved_page

        if not page or page == 0:
            logger.warning(f"⚠️ Skipping chunk from {source} with invalid page number: {page}")
            continue
        
        # Deduplicate: keep highest score for each (source, page) pair
        key = (source, page)
        if key not in page_map or score > page_map[key]:
            page_map[key] = score
    
    # Convert to list and sort by score (descending)
    unique_pages = [
        {'source': source, 'page': page, 'score': score}
        for (source, page), score in page_map.items()
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
            conditions.append("(document_source = %s AND page_number = %s)")
            params.extend([p['source'], p['page']])
        params.append(collection)
        
        query = f"""
            SELECT document_source, page_number, image_data
            FROM pdf_pages
            WHERE ({' OR '.join(conditions)})
            AND collection_name = %s
        """
        
        cur.execute(query, params)
        rows = cur.fetchall()
        cur.close()
        
        # Map results back to pages
        image_map = {(row[0], row[1]): row[2] for row in rows}
        
        results = []
        missing_pages = []
        
        for p in pages:
            key = (p['source'], p['page'])
            if key in image_map:
                results.append({
                    'source': p['source'],
                    'page': p['page'],
                    'score': p['score'],
                    'image_data': image_map[key]
                })
            else:
                missing_pages.append(f"{p['source']}:p{p['page']}")
        
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
