# Design Document: PDF Page Context RAG Enhancement

## 1. Overview

This design document describes the technical implementation for enhancing the RAG system to use full PDF page images as context instead of text chunks. The system will maintain text-based retrieval for efficiency while switching to image-based context for generation to provide better visual understanding.

### 1.1 Design Goals

- Maintain fast text-based retrieval (vector search + reranking)
- Enhance generation with full PDF page images for better context
- Preserve page number metadata for accurate chunk-to-page mapping
- Minimize token consumption through intelligent page deduplication
- Support backward compatibility with text-based mode

### 1.2 Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    EMBEDDING PHASE (One-time)                │
├─────────────────────────────────────────────────────────────┤
│  PDF File                                                    │
│     ↓                                                        │
│  Docling (DOC_CHUNKS export) ──→ Text chunks with page #s   │
│     ↓                                                        │
│  PyMuPDF/pdf2image ──→ Page images (1 per page)            │
│     ↓                                                        │
│  Store in PostgreSQL:                                        │
│    • documents table (text chunks + embeddings)              │
│    • pdf_pages table (page images)                          │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                    RETRIEVAL PHASE (Per query)               │
├─────────────────────────────────────────────────────────────┤
│  User Question                                               │
│     ↓                                                        │
│  Vector Search (pgvector) ──→ 50 candidates                 │
│     ↓                                                        │
│  Reranking (Flashrank) ──→ Top 8 chunks                     │
│     ↓                                                        │
│  Context Selection ──→ 3-5 final chunks                     │
│     ↓                                                        │
│  Extract page numbers: [12, 12, 15, 20, 22]                │
│     ↓                                                        │
│  Deduplicate: [12, 15, 20, 22]                             │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                   GENERATION PHASE (Per query)               │
├─────────────────────────────────────────────────────────────┤
│  Unique page numbers: [12, 15, 20, 22]                     │
│     ↓                                                        │
│  Query pdf_pages table ──→ Fetch 4 page images             │
│     ↓                                                        │
│  Send to Gemini Vision LLM:                                 │
│    • User question (text)                                    │
│    • Page images (base64 encoded)                           │
│     ↓                                                        │
│  Generate answer with full visual context                    │
└─────────────────────────────────────────────────────────────┘
```

## 2. Database Schema Design

### 2.1 New Table: pdf_pages

```sql
CREATE TABLE pdf_pages (
    id SERIAL PRIMARY KEY,
    document_source TEXT NOT NULL,           -- Filename (e.g., "user_manual.pdf")
    page_number INTEGER NOT NULL,            -- Page number (1-indexed)
    image_data BYTEA NOT NULL,               -- PNG image bytes
    collection_name TEXT NOT NULL,           -- Collection (e.g., "plcnext")
    created_at TIMESTAMP DEFAULT NOW(),
    
    -- Composite unique constraint
    UNIQUE(document_source, page_number, collection_name)
);

-- Index for fast lookups
CREATE INDEX idx_pdf_pages_lookup 
ON pdf_pages(document_source, page_number, collection_name);

-- Index for collection-based queries
CREATE INDEX idx_pdf_pages_collection 
ON pdf_pages(collection_name);
```

### 2.2 Modified Table: documents (metadata enhancement)

No schema changes needed. The existing `metadata` JSONB field will store:
```json
{
  "source": "user_manual.pdf",
  "page": 42,                    // Real page number from DOC_CHUNKS
  "chunk_type": "prose",
  "char_count": 850,
  "word_count": 142
}
```

### 2.3 Migration Script

Location: `backend/migrations/001_create_pdf_pages.sql`

```sql
-- Migration: Create pdf_pages table
-- Version: 001
-- Description: Add table for storing PDF page images

BEGIN;

-- Create table
CREATE TABLE IF NOT EXISTS pdf_pages (
    id SERIAL PRIMARY KEY,
    document_source TEXT NOT NULL,
    page_number INTEGER NOT NULL,
    image_data BYTEA NOT NULL,
    collection_name TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(document_source, page_number, collection_name)
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_pdf_pages_lookup 
ON pdf_pages(document_source, page_number, collection_name);

CREATE INDEX IF NOT EXISTS idx_pdf_pages_collection 
ON pdf_pages(collection_name);

COMMIT;

-- Rollback script (for reference)
-- DROP TABLE IF EXISTS pdf_pages CASCADE;
```

## 3. Component Design

### 3.1 Embedding Pipeline Enhancement

**File:** `backend/embed.py`

#### 3.1.1 Page Image Extraction

```python
import fitz  # PyMuPDF
from PIL import Image
import io

def extract_pdf_page_images(pdf_path: str, dpi: int = 150) -> List[bytes]:
    """
    Extract each page of PDF as PNG image.
    
    Args:
        pdf_path: Path to PDF file
        dpi: Resolution for rendering (default 150)
    
    Returns:
        List of PNG image bytes (one per page)
    """
    images = []
    doc = fitz.open(pdf_path)
    
    for page_num in range(len(doc)):
        page = doc[page_num]
        
        # Render page to pixmap at specified DPI
        zoom = dpi / 72  # 72 DPI is default
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)
        
        # Convert to PNG bytes with compression
        img_bytes = pix.tobytes("png")
        
        # Optional: Further compress with PIL
        img = Image.open(io.BytesIO(img_bytes))
        output = io.BytesIO()
        img.save(output, format='PNG', optimize=True, compress_level=6)
        compressed_bytes = output.getvalue()
        
        images.append(compressed_bytes)
        
        logging.info(f"  Page {page_num + 1}: {len(compressed_bytes) / 1024:.1f} KB")
    
    doc.close()
    return images
```

#### 3.1.2 Page Image Storage

```python
def store_page_images(
    conn,
    images: List[bytes],
    document_source: str,
    collection: str
):
    """
    Store PDF page images in database.
    
    Args:
        conn: Database connection
        images: List of PNG image bytes
        document_source: Filename (basename only)
        collection: Collection name
    """
    cur = conn.cursor()
    
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
        except Exception as e:
            logging.error(f"Failed to store page {page_num}: {e}")
    
    conn.commit()
    cur.close()
    logging.info(f"✅ Stored {len(images)} page images for {document_source}")
```

#### 3.1.3 Docling Export Type Change

```python
# OLD (current):
loader = DoclingLoader(file_path=file_path, export_type=ExportType.MARKDOWN)

# NEW (with page metadata):
loader = DoclingLoader(file_path=file_path, export_type=ExportType.DOC_CHUNKS)
```

**Impact:** DOC_CHUNKS provides per-chunk page numbers in metadata.

#### 3.1.4 Modified embed.py Main Flow

```python
def main():
    # ... existing setup ...
    
    for file_idx, file_path in enumerate(tqdm(all_files)):
        if file_path.lower().endswith('.pdf'):
            try:
                # 1. Extract page images FIRST
                logging.info(f"📸 Extracting page images from {filename}...")
                page_images = extract_pdf_page_images(file_path, dpi=150)
                
                # 2. Store page images
                if not args.dry_run:
                    store_page_images(conn, page_images, filename, args.collection)
                
                # 3. Extract text chunks with DOC_CHUNKS export
                loader = DoclingLoader(
                    file_path=file_path, 
                    export_type=ExportType.DOC_CHUNKS  # Changed from MARKDOWN
                )
                pages = loader.load()
                
                # 4. Create and embed text chunks (existing logic)
                chunks = create_pdf_chunks(pages, chunk_size, chunk_overlap)
                pending_chunks.extend(chunks)
                
            except Exception as e:
                logging.error(f"❌ Failed to process PDF {file_path}: {e}")
                continue
```

### 3.2 Context Preparation Module

**New File:** `backend/app/context_prep.py`

```python
import logging
from typing import List, Dict, Any, Optional
from langchain_core.documents import Document
import psycopg2

logger = logging.getLogger(__name__)


def extract_unique_pages(selected_docs: List[Document]) -> List[Dict[str, Any]]:
    """
    Extract unique pages from selected chunks with deduplication.
    
    Args:
        selected_docs: List of Document objects with metadata
    
    Returns:
        List of dicts with {source, page, score} sorted by score
    """
    page_map = {}  # Key: (source, page), Value: max_score
    
    for doc in selected_docs:
        source = doc.metadata.get('source')
        page = doc.metadata.get('page')
        score = doc.metadata.get('score', 0.0)
        
        if not source or not page or page == 0:
            logger.warning(f"Skipping chunk with invalid metadata: {doc.metadata}")
            continue
        
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
    return unique_pages


def fetch_page_images(
    conn_pool,
    pages: List[Dict[str, Any]],
    collection: str
) -> List[Dict[str, Any]]:
    """
    Fetch PDF page images from database.
    
    Args:
        conn_pool: Database connection pool
        pages: List of {source, page, score} dicts
        collection: Collection name
    
    Returns:
        List of dicts with {source, page, score, image_data}
    """
    if not pages:
        return []
    
    conn = conn_pool.getconn()
    try:
        cur = conn.cursor()
        
        # Build query for batch fetch
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
                logger.warning(f"⚠️ Page image not found: {p['source']} page {p['page']}")
        
        logger.info(f"✅ Fetched {len(results)}/{len(pages)} page images")
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
    
    Args:
        selected_docs: Selected chunks from retrieval
        conn_pool: Database connection pool
        collection: Collection name
    
    Returns:
        List of page dicts with image_data, or None if no pages found
    """
    # 1. Extract unique pages with deduplication
    unique_pages = extract_unique_pages(selected_docs)
    
    if not unique_pages:
        logger.warning("No valid pages found in selected chunks")
        return None
    
    # 2. Fetch page images from database
    page_images = fetch_page_images(conn_pool, unique_pages, collection)
    
    if not page_images:
        logger.error("Failed to fetch any page images")
        return None
    
    return page_images
```

### 3.3 Vision LLM Integration

**File:** `backend/app/chatbot.py` (modifications)

#### 3.3.1 Configuration

```python
# Add to configuration section
USE_PAGE_IMAGES = os.getenv("USE_PAGE_IMAGES", "false").lower() in ("true", "1", "yes")
```

#### 3.3.2 Vision Prompt Template

```python
def build_vision_prompt() -> PromptTemplate:
    """Prompt template for vision LLM with page images"""
    template = """You are Panya, an Industrial Automation and PLC expert assistant.

{history_section}CONTEXT:
You are viewing {page_count} PDF pages from technical documentation. 
These pages contain the most relevant information for answering the question.

CRITICAL RULES:
- Analyze the PDF pages carefully, including text, tables, diagrams, and layout
- Answer using information from the pages shown
- If the answer is NOT found in the pages, say: "I couldn't find specific information about this."
- DO NOT make up facts or specifications
- DO NOT mention "Document", "Source", "Page", or reference numbers - just provide the information naturally
- Answer ONLY the CURRENT QUESTION below

FORMATTING:
- For step-by-step procedures: Use NUMBERED LISTS (1. 2. 3.)
- For specifications or options: Use bullet points (•)
- Use **bold** for important terms and specifications
- Keep responses clear, concise and scannable

CURRENT QUESTION:
{question}

ANSWER:"""
    return PromptTemplate(
        input_variables=["history_section", "page_count", "question"], 
        template=template
    )
```

#### 3.3.3 Image Encoding Helper

```python
import base64

def encode_images_for_gemini(page_images: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """
    Encode page images for Gemini vision API.
    
    Args:
        page_images: List of dicts with image_data (bytes)
    
    Returns:
        List of dicts with {mime_type, data} for Gemini
    """
    encoded_images = []
    for page in page_images:
        image_bytes = page['image_data']
        base64_image = base64.b64encode(image_bytes).decode('utf-8')
        encoded_images.append({
            'mime_type': 'image/png',
            'data': base64_image
        })
    return encoded_images
```

#### 3.3.4 Modified answer_question Function

```python
def answer_question(
    question: str,
    db_pool,
    llm,
    embedder,
    collection: str,
    retriever_class,
    reranker_class,
    chat_history: List[dict] = None,
) -> dict:
    # ... existing retrieval logic ...
    
    selected_docs = select_context_docs(retrieved_docs)
    
    # ============ CONTEXT PREPARATION ============
    if USE_PAGE_IMAGES:
        # NEW: Image-based context
        from app.context_prep import prepare_page_context
        
        page_images = prepare_page_context(selected_docs, db_pool, collection)
        
        if page_images:
            # Encode images for Gemini
            encoded_images = encode_images_for_gemini(page_images)
            
            # Build vision chain
            prompt = build_vision_prompt()
            
            # Create multimodal content for Gemini
            content_parts = [
                {"type": "text", "text": prompt.format(
                    history_section=history_section,
                    page_count=len(page_images),
                    question=processed_msg
                )}
            ]
            
            # Add images
            for img in encoded_images:
                content_parts.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": img['mime_type'],
                        "data": img['data']
                    }
                })
            
            # Call vision LLM
            reply = llm.invoke(content_parts)
            
            logger.info(f"📸 Sent {len(page_images)} page images to vision LLM")
        else:
            # Fallback to text if no images found
            logger.warning("No page images found, falling back to text context")
            USE_PAGE_IMAGES = False
    
    if not USE_PAGE_IMAGES:
        # EXISTING: Text-based context (unchanged)
        context_texts = [d.page_content for d in selected_docs]
        # ... existing text-based logic ...
    
    # ... rest of function unchanged ...
```

## 4. Configuration

### 4.1 Environment Variables

Add to `.env`:
```bash
# PDF Page Context RAG
USE_PAGE_IMAGES=true              # Enable image-based context (default: false)
PAGE_IMAGE_DPI=150                # Image resolution for PDF rendering
PAGE_IMAGE_FORMAT=PNG             # Image format (PNG recommended)
```

### 4.2 Dependencies

Add to `backend/requirements.txt`:
```
PyMuPDF>=1.23.0                   # PDF rendering (fitz)
Pillow>=10.0.0                    # Image processing
```

## 5. Error Handling & Logging

### 5.1 Error Scenarios

| Scenario | Handling | Fallback |
|----------|----------|----------|
| Page image not found in DB | Log warning, skip page | Continue with available pages |
| All page images missing | Log error | Fall back to text-based context |
| Vision LLM API failure | Log error, retry 3× | Return error message to user |
| Image encoding failure | Log error | Skip that page |
| Invalid page metadata (page=0) | Log warning | Skip chunk |

### 5.2 Logging Strategy

```python
# Embedding phase
logger.info(f"📸 Extracting {num_pages} page images from {filename}")
logger.info(f"✅ Stored {num_pages} page images ({total_size_mb:.1f} MB)")

# Retrieval phase
logger.info(f"📄 Extracted {len(unique_pages)} unique pages from {len(chunks)} chunks")
logger.info(f"✅ Fetched {len(page_images)}/{len(unique_pages)} page images")

# Generation phase
logger.info(f"📸 Sent {len(page_images)} page images to vision LLM ({total_tokens} tokens)")
logger.warning(f"⚠️ Page image not found: {source} page {page_num}")
logger.error(f"❌ Vision LLM call failed: {error}")
```

## 6. Performance Considerations

### 6.1 Storage Estimates

- Average PDF page at 150 DPI: ~200-400 KB (PNG compressed)
- 100-page document: ~20-40 MB
- 10 documents (1000 pages): ~200-400 MB

### 6.2 Query Performance

- Page image fetch: <100ms for 5 pages (indexed lookup)
- Image encoding (base64): <50ms for 5 pages
- Vision LLM latency: 2-5 seconds (similar to text-only)

### 6.3 Token Consumption

- Text-based: ~750 tokens/query
- Image-based: ~3,000-6,000 tokens/query (4-8× increase)
- Natural cap: 5 pages maximum (from MAX_CANDIDATES=5)

## 7. Testing Strategy

### 7.1 Unit Tests

```python
# test_context_prep.py
def test_extract_unique_pages():
    """Test page deduplication logic"""
    
def test_fetch_page_images():
    """Test database image retrieval"""

# test_embed.py
def test_extract_pdf_page_images():
    """Test PDF to image conversion"""
    
def test_store_page_images():
    """Test image storage in database"""
```

### 7.2 Integration Tests

1. **End-to-end embedding**: PDF → images + chunks → database
2. **End-to-end retrieval**: Query → chunks → pages → images → LLM
3. **Backward compatibility**: Toggle USE_PAGE_IMAGES on/off

### 7.3 Manual Testing

1. Embed a test PDF with known content
2. Query for specific information
3. Verify correct pages are retrieved
4. Compare answers: text-based vs image-based
5. Check token consumption in logs

## 8. Migration Path

### 8.1 Phase 1: Database Setup
1. Run migration script to create `pdf_pages` table
2. Verify indexes are created

### 8.2 Phase 2: Re-embed Existing Documents
1. Set `USE_PAGE_IMAGES=false` (keep text-based mode)
2. Re-run embed.py with DOC_CHUNKS export
3. Verify page numbers in metadata
4. Verify page images in database

### 8.3 Phase 3: Enable Image Mode
1. Set `USE_PAGE_IMAGES=true`
2. Test with sample queries
3. Monitor token consumption
4. Compare answer quality

### 8.4 Rollback Plan
1. Set `USE_PAGE_IMAGES=false` (instant rollback)
2. If needed, drop `pdf_pages` table
3. Re-embed with MARKDOWN export (restore old behavior)

## 9. Future Enhancements

### 9.1 Optional Page Overlap (Post-MVP)
- Add `PAGE_OVERLAP=1` config
- Include ±n adjacent pages for each selected page
- Useful for context that spans multiple pages

### 9.2 Adaptive Page Selection (Post-MVP)
- Dynamically adjust page count based on query complexity
- Simple queries: 2-3 pages
- Complex queries: 5+ pages

### 9.3 Page Caching (Post-MVP)
- Cache frequently accessed page images in Redis
- Reduce database load for popular documents

### 9.4 Multi-Document Support (Post-MVP)
- Handle queries spanning multiple documents
- Group pages by document for better organization

## 10. Success Metrics

### 10.1 Quality Metrics
- Answer accuracy: Compare with ground truth QA pairs
- RAGAS scores: Monitor faithfulness and relevance
- User feedback: Track thumbs up/down

### 10.2 Performance Metrics
- Query latency: Target <5 seconds end-to-end
- Token consumption: Monitor daily usage
- Storage growth: Track database size

### 10.3 System Health
- Error rate: <1% for page image retrieval
- Fallback rate: Track text-based fallbacks
- API quota usage: Stay within limits
