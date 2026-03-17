"""
PDF Page Image Extraction Utilities

This module provides functions for extracting PDF pages as images
and storing them in the database for vision LLM context.
"""
import logging
import io
from typing import List, Tuple
import fitz  # PyMuPDF
from PIL import Image

logger = logging.getLogger(__name__)


def extract_pdf_page_images(pdf_path: str, dpi: int = 150) -> List[bytes]:
    """
    Extract each page of PDF as PNG image.
    
    Args:
        pdf_path: Path to PDF file
        dpi: Resolution for rendering (default 150 DPI)
    
    Returns:
        List of PNG image bytes (one per page)
    
    Raises:
        Exception: If PDF cannot be opened or page rendering fails
    """
    images = []
    
    try:
        doc = fitz.open(pdf_path)
        total_pages = len(doc)
        
        logger.info(f"📸 Extracting {total_pages} page images at {dpi} DPI...")
        
        for page_num in range(total_pages):
            try:
                page = doc[page_num]
                
                # Render page to pixmap at specified DPI
                zoom = dpi / 72  # 72 DPI is PyMuPDF default
                mat = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=mat)
                
                # Convert to PNG bytes
                img_bytes = pix.tobytes("png")
                
                # Further compress with PIL for storage efficiency
                img = Image.open(io.BytesIO(img_bytes))
                output = io.BytesIO()
                img.save(output, format='PNG', optimize=True, compress_level=6)
                compressed_bytes = output.getvalue()
                
                images.append(compressed_bytes)
                
                size_kb = len(compressed_bytes) / 1024
                logger.debug(f"  Page {page_num + 1}/{total_pages}: {size_kb:.1f} KB")
                
            except Exception as e:
                logger.error(f"❌ Failed to extract page {page_num + 1}: {e}")
                # Continue with other pages even if one fails
                continue
        
        doc.close()
        
        total_size_mb = sum(len(img) for img in images) / (1024 * 1024)
        logger.info(f"✅ Extracted {len(images)}/{total_pages} pages ({total_size_mb:.1f} MB total)")
        
        return images
        
    except Exception as e:
        logger.error(f"❌ Failed to open PDF {pdf_path}: {e}")
        raise


def store_page_images(
    conn,
    images: List[bytes],
    document_source: str,
    collection: str
) -> int:
    """
    Store PDF page images in database.
    
    Args:
        conn: Database connection (psycopg2)
        images: List of PNG image bytes
        document_source: Filename (basename only, e.g., "user_manual.pdf")
        collection: Collection name (e.g., "plcnext")
    
    Returns:
        Number of pages successfully stored
    
    Raises:
        Exception: If database operation fails
    """
    if not images:
        logger.warning("⚠️ No images to store")
        return 0
    
    cur = conn.cursor()
    stored_count = 0
    
    try:
        for page_num, image_bytes in enumerate(images, start=1):
            try:
                cur.execute(
                    """
                    INSERT INTO pdf_pages 
                    (document_source, page_number, image_data, collection_name)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (document_source, page_number, collection_name) 
                    DO UPDATE SET 
                        image_data = EXCLUDED.image_data,
                        created_at = NOW()
                    """,
                    (document_source, page_num, image_bytes, collection)
                )
                stored_count += 1
                
            except Exception as e:
                logger.error(f"❌ Failed to store page {page_num}: {e}")
                # Continue with other pages
                continue
        
        conn.commit()
        cur.close()
        
        total_size_mb = sum(len(img) for img in images) / (1024 * 1024)
        logger.info(f"✅ Stored {stored_count}/{len(images)} page images ({total_size_mb:.1f} MB) for {document_source}")
        
        return stored_count
        
    except Exception as e:
        conn.rollback()
        logger.error(f"❌ Database error while storing images: {e}")
        raise


def delete_page_images(conn, document_source: str, collection: str) -> int:
    """
    Delete all page images for a document (used when re-embedding).
    
    Args:
        conn: Database connection
        document_source: Filename (basename only)
        collection: Collection name
    
    Returns:
        Number of pages deleted
    """
    cur = conn.cursor()
    
    try:
        cur.execute(
            """
            DELETE FROM pdf_pages
            WHERE document_source = %s AND collection_name = %s
            """,
            (document_source, collection)
        )
        deleted_count = cur.rowcount
        conn.commit()
        cur.close()
        
        if deleted_count > 0:
            logger.info(f"🗑️ Deleted {deleted_count} old page images for {document_source}")
        
        return deleted_count
        
    except Exception as e:
        conn.rollback()
        logger.error(f"❌ Failed to delete page images: {e}")
        raise


def get_page_image_stats(conn, collection: str = None) -> dict:
    """
    Get statistics about stored page images.
    
    Args:
        conn: Database connection
        collection: Optional collection filter
    
    Returns:
        Dict with stats: {total_pages, total_size_mb, documents}
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
                (collection,)
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
                'total_pages': row[0],
                'total_size_mb': (row[1] or 0) / (1024 * 1024),
                'total_documents': row[2]
            }
        else:
            return {
                'total_pages': 0,
                'total_size_mb': 0.0,
                'total_documents': 0
            }
            
    except Exception as e:
        logger.error(f"❌ Failed to get stats: {e}")
        return {
            'total_pages': 0,
            'total_size_mb': 0.0,
            'total_documents': 0
        }
