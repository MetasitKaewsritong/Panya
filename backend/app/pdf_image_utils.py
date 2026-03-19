"""
PDF page asset utilities.

This module handles:
- rendering PDF pages into PNG images
- extracting machine-readable text per page
- storing rendered pages in the database with page-level metadata
"""
import io
import json
import logging
from typing import Any, Dict, Iterator, List

import fitz  # PyMuPDF
from PIL import Image

logger = logging.getLogger(__name__)


def _display_source_name(source_value: str) -> str:
    cleaned = str(source_value or "").replace("\\", "/").rstrip("/")
    if not cleaned:
        return ""
    return cleaned.rsplit("/", 1)[-1]


def _render_pdf_page_asset(page, page_number: int, dpi: int) -> Dict[str, Any]:
    zoom = dpi / 72
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))

    img_bytes = pix.tobytes("png")
    img = Image.open(io.BytesIO(img_bytes))
    output = io.BytesIO()
    img.save(output, format="PNG", optimize=True, compress_level=6)

    return {
        "page_number": page_number,
        "image_data": output.getvalue(),
        "text": page.get_text("text") or "",
    }


def get_pdf_page_count(pdf_path: str) -> int:
    with fitz.open(pdf_path) as doc:
        return len(doc)


def iter_pdf_page_assets(pdf_path: str, dpi: int = 150, start_page: int = 1) -> Iterator[Dict[str, Any]]:
    """
    Stream PDF page assets one page at a time so resume runs do not need to
    render the entire document before the next commit.
    """
    first_page = max(int(start_page or 1), 1)

    try:
        doc = fitz.open(pdf_path)
        total_pages = len(doc)
        logger.info(
            "Streaming page assets for %s from page %d/%d at %d DPI...",
            pdf_path,
            first_page,
            total_pages,
            dpi,
        )

        yielded = 0
        try:
            for page_idx in range(first_page - 1, total_pages):
                try:
                    page = doc[page_idx]
                    yield _render_pdf_page_asset(page, page_idx + 1, dpi)
                    yielded += 1
                except Exception as e:
                    logger.error("Failed to extract page %d from %s: %s", page_idx + 1, pdf_path, e)
        finally:
            doc.close()

        logger.info(
            "Streamed %d page assets from %s starting at page %d",
            yielded,
            pdf_path,
            first_page,
        )
    except Exception as e:
        logger.error("Failed to open PDF %s: %s", pdf_path, e)
        raise


def extract_pdf_page_assets(pdf_path: str, dpi: int = 150) -> List[Dict[str, Any]]:
    """
    Extract each PDF page as a page asset.

    Returns:
        A list of dicts with:
        - page_number: 1-indexed page number
        - image_data: PNG bytes
        - text: machine-extracted page text
    """
    assets: List[Dict[str, Any]] = []

    try:
        total_pages = get_pdf_page_count(pdf_path)
        logger.info("Extracting %d page assets at %d DPI...", total_pages, dpi)
        assets.extend(iter_pdf_page_assets(pdf_path, dpi=dpi, start_page=1))
        logger.info("Extracted %d/%d page assets from %s", len(assets), total_pages, pdf_path)
        return assets
    except Exception as e:
        logger.error("Failed to open PDF %s: %s", pdf_path, e)
        raise


def extract_pdf_page_images(pdf_path: str, dpi: int = 150) -> List[bytes]:
    """
    Backward-compatible helper that returns only PNG bytes.
    """
    return [asset["image_data"] for asset in extract_pdf_page_assets(pdf_path, dpi=dpi)]


def store_page_images(
    conn,
    images: List[bytes],
    document_source: str,
    collection: str,
    brand: str = "",
    model_subbrand: str = "",
    page_metadata: List[Dict[str, Any]] | None = None,
    *,
    commit: bool = True,
) -> int:
    """
    Store rendered PDF page images in the database.
    """
    if not images:
        logger.warning("No images to store for %s", document_source)
        return 0

    cur = conn.cursor()
    stored_count = 0

    try:
        for idx, image_bytes in enumerate(images):
            try:
                metadata = {}
                if page_metadata and len(page_metadata) > idx and page_metadata[idx]:
                    metadata = dict(page_metadata[idx])
                actual_page_number = int(metadata.get("page", idx + 1) or (idx + 1))
                metadata = {
                    "source": metadata.get("source") or _display_source_name(document_source),
                    "source_id": metadata.get("source_id") or document_source,
                    "page": actual_page_number,
                    "brand": brand,
                    "model_subbrand": model_subbrand,
                }
                if page_metadata and len(page_metadata) > idx and page_metadata[idx]:
                    metadata.update(page_metadata[idx])

                cur.execute(
                    """
                    INSERT INTO pdf_pages (
                        document_source,
                        page_number,
                        brand,
                        model_subbrand,
                        image_data,
                        collection_name,
                        metadata
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (document_source, page_number, collection_name, brand, model_subbrand)
                    DO UPDATE SET
                        image_data = EXCLUDED.image_data,
                        metadata = EXCLUDED.metadata,
                        created_at = NOW()
                    """,
                    (
                        document_source,
                        actual_page_number,
                        brand,
                        model_subbrand,
                        image_bytes,
                        collection,
                        json.dumps(metadata, ensure_ascii=False),
                    ),
                )
                stored_count += 1
            except Exception as e:
                logger.error("Failed to store page %d for %s: %s", idx + 1, document_source, e)

        if commit:
            conn.commit()
        cur.close()

        total_size_mb = sum(len(img) for img in images) / (1024 * 1024)
        logger.info(
            "Stored %d/%d page images (%.1f MB) for %s",
            stored_count,
            len(images),
            total_size_mb,
            document_source,
        )
        return stored_count
    except Exception as e:
        if commit:
            conn.rollback()
        logger.error("Database error while storing images for %s: %s", document_source, e)
        raise


def delete_page_images(
    conn,
    document_source: str,
    collection: str,
    *,
    legacy_source: str | None = None,
    commit: bool = True,
) -> int:
    """
    Delete all stored page images for one source document within a collection.
    """
    cur = conn.cursor()

    try:
        cur.execute(
            """
            DELETE FROM pdf_pages
            WHERE collection_name = %s
              AND (
                    document_source = %s
                    OR (
                        document_source = %s
                        AND COALESCE(metadata->>'source_id', '') = ''
                    )
                  )
            """,
            (collection, document_source, legacy_source or _display_source_name(document_source)),
        )
        deleted_count = cur.rowcount
        if commit:
            conn.commit()
        cur.close()

        if deleted_count > 0:
            logger.info("Deleted %d page images for %s", deleted_count, document_source)
        return deleted_count
    except Exception as e:
        if commit:
            conn.rollback()
        logger.error("Failed to delete page images for %s: %s", document_source, e)
        raise


def get_page_image_stats(conn, collection: str = None) -> dict:
    """
    Get statistics about stored page images.
    """
    cur = conn.cursor()

    try:
        if collection:
            cur.execute(
                """
                SELECT
                    COUNT(*) as total_pages,
                    SUM(LENGTH(image_data)) as total_bytes,
                    COUNT(DISTINCT document_source) as total_docs
                FROM pdf_pages
                WHERE collection_name = %s
                """,
                (collection,),
            )
        else:
            cur.execute(
                """
                SELECT
                    COUNT(*) as total_pages,
                    SUM(LENGTH(image_data)) as total_bytes,
                    COUNT(DISTINCT document_source) as total_docs
                FROM pdf_pages
                """
            )

        row = cur.fetchone()
        cur.close()

        if row and row[0] > 0:
            return {
                "total_pages": row[0],
                "total_size_mb": (row[1] or 0) / (1024 * 1024),
                "total_documents": row[2],
            }
        return {
            "total_pages": 0,
            "total_size_mb": 0.0,
            "total_documents": 0,
        }
    except Exception as e:
        logger.error("Failed to get page image stats: %s", e)
        return {
            "total_pages": 0,
            "total_size_mb": 0.0,
            "total_documents": 0,
        }
