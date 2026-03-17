import os
import re
import json
import logging
import threading
from typing import List, Optional
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sentence_transformers import SentenceTransformer

# Singleton embedder instance with thread-safe initialization
_embedder = None
_embedder_lock = threading.Lock()

def get_embedder():
    """
    Returns a thread-safe singleton SentenceTransformer embedder.
    Uses BAAI/bge-m3 model (matching embed.py and .env configuration).
    """
    global _embedder
    if _embedder is None:
        with _embedder_lock:
            # Double-check locking pattern
            if _embedder is None:
                model_name = os.getenv("EMBED_MODEL", "BAAI/bge-m3")
                cache_folder = os.getenv("MODEL_CACHE", "/app/models")
                logging.info(f"[get_embedder] Loading embedder: {model_name}")
                _embedder = SentenceTransformer(model_name, cache_folder=cache_folder)
                logging.info("[get_embedder] Embedder loaded successfully")
    return _embedder


def clean_text(text: str) -> str:
    """
    Clean extracted PDF text before chunking.
    Preserves paragraph structure (single newlines) for better semantic chunking.
    """
    # Normalize horizontal whitespace (spaces/tabs -> single space)
    text = re.sub(r'[ \t]+', ' ', text)
    
    # Collapse excessive newlines (3+ -> 2)
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    # Remove page headers/footers (common patterns)
    text = re.sub(r'(Page\s*\d+|\d+\s*of\s*\d+)', '', text, flags=re.IGNORECASE)
    
    # Remove Docling/Phoenix-specific patterns
    text = re.sub(r'--- PAGE \d+ ---', '', text)
    text = re.sub(r'\d{6}_en_\d{2,}', '', text)
    text = re.sub(r'PHOENIX CONTACT \d+/\d+', '', text)
    
    # Remove garbage characters (keep ASCII printable + Thai + newlines)
    text = re.sub(r'[^\x20-\x7E\n\u0E00-\u0E7F]', '', text)
    
    # Remove TOC fillers (5+ consecutive dots/dashes/underscores)
    text = re.sub(r'[.\-_]{5,}', ' ', text)
    
    # Clean up spaces around newlines
    text = re.sub(r' *\n *', '\n', text)
    
    # Final horizontal whitespace cleanup
    text = re.sub(r'[ \t]+', ' ', text)
    

    return text.strip()


def is_valid_chunk(chunk: Document) -> tuple[bool, str]:
    """
    Check if chunk is worth keeping.
    Returns (is_valid: bool, reason: str)
    
    Filters:
    1. Too short (<50 chars with low alpha)
    2. Table of Contents entries (page references)
    3. Low alphabetic ratio (<15% after removing fillers)
    4. Excessive whitespace (>50%)
    5. Repetitive characters (10+ same char)
    6. High special characters (>40% punctuation)
    7. Header/page number only
    """
    content = chunk.page_content.strip()
    
    # 1. Too short (<50 chars) - but allow high-alpha short content
    if len(content) < 50:
        alpha_ratio = sum(1 for c in content if c.isalpha()) / len(content) if content else 0
        if alpha_ratio > 0.70:  # Short but meaningful
            return True, "ok"
        return False, f"too_short ({len(content)} chars)"
    
    # 2. TABLE OF CONTENTS detection - REJECT these!
    # Pattern: "3.4.1 Something........... 45" or "Chapter 3....... 15"
    if _TOC_PATTERN.search(content):
        return False, "toc_entry"
    
    # TOC in markdown table format: "| Something ... | 15 |" or "| 3.1.6 [G] Expansion boards...48 |"
    if _TOC_TABLE_PATTERN.search(content):
        return False, "toc_table_entry"
    
    # Simple page reference patterns in tables: "| Standards | 15 |" with mostly numbers + short text
    if '|' in content:
        # Extract cell contents
        cells = [c.strip() for c in content.split('|') if c.strip()]
        # If most cells are just numbers or very short text, it's likely TOC
        page_number_cells = sum(1 for c in cells if re.match(r'^\d{1,4}$', c))
        if len(cells) > 0 and page_number_cells >= len(cells) // 2:
            # Check if content is suspiciously short on actual text
            total_text = ' '.join(cells)
            if len(total_text) < 100:
                return False, "toc_page_reference"
    
    # 3. Low alphabetic ratio (<15% letters, excluding fillers)
    content_no_fillers = re.sub(r'[.\-_=]{2,}', '', content)
    if len(content_no_fillers) > 10:
        alpha_count = sum(1 for c in content_no_fillers if c.isalpha())
        alpha_ratio = alpha_count / len(content_no_fillers)
        
        # Check if this looks like technical notation (device addresses, register names, etc.)
        # Pattern: X0000, M8126, D0255, TN063, etc.
        has_technical_pattern = bool(_TECHNICAL_DEVICE_PATTERN.search(content))
        
        # Allow low alpha ratio if it contains technical patterns
        if alpha_ratio < 0.15 and not has_technical_pattern:
            return False, f"low_alpha ({alpha_ratio:.1%})"
    
    # 4. Excessive whitespace (>50%)
    whitespace_ratio = sum(1 for c in content if c.isspace()) / len(content) if content else 0
    if whitespace_ratio > 0.50:
        return False, f"excessive_whitespace ({whitespace_ratio:.1%})"
    
    # 5. Repetitive garbage chars (exclude dots/dashes/underscores/spaces)
    if re.search(r'([^.\-_\s])\1{9,}', content):
        return False, "repetitive_chars"
    
    # 6. High special characters (>40%) - excluding common formatting
    non_formatting_special = sum(1 for c in content if not c.isalnum() and not c.isspace() and c not in '.-_=|')
    special_ratio = non_formatting_special / len(content) if content else 0
    if special_ratio > 0.40:
        return False, f"high_special ({special_ratio:.1%})"
    
    # 7. Page headers only
    if re.match(r'^(page\s*\d+|\d+\s*of\s*\d+|chapter\s*\d+)$', content.lower()):
        return False, "header_only"

    return True, "ok"


def enhance_metadata(metadata: dict, chunk_content: str) -> dict:
    """Add useful metadata to chunk"""
    enhanced_meta = metadata.copy()
    enhanced_meta.update({
        "char_count": len(chunk_content),
        "word_count": len(chunk_content.split()),
    })
    return enhanced_meta


def get_file_label(source: str) -> str:
    """
    Extract clean filename label from source path.
    Examples:
        'MELSEC-F_manual.pdf' -> 'MELSEC-F_manual'
        '/path/to/PLC_guide.pdf' -> 'PLC_guide'
    """
    filename = os.path.basename(source)
    label = os.path.splitext(filename)[0]
    return label


def split_table_by_rows(table_text: str, max_chars: int = 800) -> List[str]:
    """
    Split a markdown table by rows while preserving headers.
    Handles multi-line headers and missing separators.
    
    Args:
        table_text: Markdown table string
        max_chars: Maximum characters per chunk
    
    Returns:
        List of table chunks, each with headers preserved
    """
    lines = [l for l in table_text.strip().split('\n') if l.strip()]
    if len(lines) < 2:
        return [table_text]  # Not a valid table
    
    # Find separator line (contains only |, -, and spaces)
    separator_idx = None
    for i, line in enumerate(lines):
        if re.match(r'^\s*\|[\s\-|]+\|\s*$', line):
            separator_idx = i
            break
    
    if separator_idx is None:
        # No separator found, treat first line as header
        header_lines = [lines[0]]
        data_lines = lines[1:]
    else:
        # Everything up to and including separator is header
        header_lines = lines[:separator_idx + 1]
        data_lines = lines[separator_idx + 1:]
    
    if not data_lines:
        return [table_text]  # No data rows
    
    header_text = '\n'.join(header_lines)
    header_len = len(header_text) + 1  # +1 for newline
    
    # Split data rows into chunks
    chunks = []
    current_chunk_lines = []
    current_len = header_len
    
    for row in data_lines:
        row_len = len(row) + 1  # +1 for newline
        
        # If adding this row exceeds limit, flush current chunk
        if current_len + row_len > max_chars and current_chunk_lines:
            chunk_text = header_text + '\n' + '\n'.join(current_chunk_lines)
            chunks.append(chunk_text)
            current_chunk_lines = []
            current_len = header_len
        
        current_chunk_lines.append(row)
        current_len += row_len
    
    # Flush remaining rows
    if current_chunk_lines:
        chunk_text = header_text + '\n' + '\n'.join(current_chunk_lines)
        chunks.append(chunk_text)
    
    return chunks if chunks else [table_text]


def extract_tables_and_prose(text: str) -> tuple[List[str], str]:
    """
    Separate markdown tables from prose text.
    
    Returns:
        (list of table strings, remaining prose text)
    """
    tables = []
    prose = text
    
    for match in _TABLE_PATTERN.finditer(text):
        table_text = match.group(1).strip()
        # Only consider it a table if it has at least 2 rows (header + data)
        if table_text.count('\n') >= 1 and '|' in table_text:
            tables.append(table_text)
            prose = prose.replace(match.group(1), '\n')  # Remove table from prose
    
    return tables, prose


# Centralized chunk defaults (read from env for consistency)
DEFAULT_CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1000"))
DEFAULT_CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "200"))

# Precompiled regex patterns for performance
_KV_PATTERN = re.compile(r'^(?P<key>[A-Za-z0-9\(\)\/\s\.,-]{5,80}?)\s{2,}(?P<value>.+?)$', re.MULTILINE)
_TABLE_PATTERN = re.compile(r'((?:^\|.*\|$\n?)+)', re.MULTILINE)
_TOC_PATTERN = re.compile(r'\d+\.\d+.*\.{3,}\s*\d+')
_TOC_TABLE_PATTERN = re.compile(r'\|.*\.{3,}.*\d+\s*\|')
_TECHNICAL_DEVICE_PATTERN = re.compile(r'\b[A-Z]{1,3}\d{3,5}\b')  # X0000, M8126, etc.
_PAGE_TOKEN_PATTERN = re.compile(r"[a-z0-9\-]{4,}", re.IGNORECASE)
_PAGE_STOPWORDS = {
    "with", "from", "that", "this", "only", "using", "into", "where", "which",
    "unit", "series", "guide", "manual", "command", "data", "computer", "adapter",
}


def _normalize_for_match(text: str) -> str:
    return " ".join((text or "").lower().split())


def _resolve_pdf_path(source: str, pdf_path: Optional[str]) -> Optional[str]:
    """Resolve PDF path from explicit arg or known data directories."""
    if pdf_path and os.path.exists(pdf_path):
        return pdf_path

    filename = os.path.basename(source or "")
    candidate_dirs = ["/app/data/Knowledge", "/app/data/knowledge", "./data/Knowledge", "./data/knowledge", ""]
    for base_dir in candidate_dirs:
        candidate = os.path.join(base_dir, filename) if base_dir else filename
        if os.path.exists(candidate):
            return candidate
    return None


def _build_pdf_page_texts(pdf_path: str) -> List[str]:
    """Load and normalize each PDF page text (1-indexed list represented as 0-indexed array)."""
    import fitz

    pdf_doc = fitz.open(pdf_path)
    try:
        return [_normalize_for_match(pdf_doc[i].get_text()) for i in range(len(pdf_doc))]
    finally:
        pdf_doc.close()


def _resolve_chunk_page(
    chunk_text: str,
    page_texts: List[str],
    current_page: int,
    fallback_page: int = 1
) -> int:
    """
    Pick best-matching physical PDF page for a chunk with confidence guards.

    fallback_page is used for weak/ambiguous matches when current_page is missing.
    This prevents noisy chunks from collapsing to page 1 during full-document remaps.
    """
    if not page_texts:
        return current_page if current_page > 0 else max(1, fallback_page)

    max_page = len(page_texts)
    fallback_page = max(1, min(fallback_page, max_page))

    normalized_chunk = _normalize_for_match(chunk_text)
    if not normalized_chunk:
        return current_page if current_page > 0 else fallback_page

    tokens = []
    for tok in _PAGE_TOKEN_PATTERN.findall(normalized_chunk):
        if tok not in _PAGE_STOPWORDS:
            tokens.append(tok)
    if not tokens:
        return current_page if current_page > 0 else fallback_page
    tokens = tokens[:50]

    scores = [sum(1 for tok in tokens if tok in page_text) for page_text in page_texts]
    best_idx = max(range(len(scores)), key=lambda i: scores[i])
    best_score = scores[best_idx]
    best_page = best_idx + 1
    sorted_scores = sorted(scores, reverse=True)
    second_best = sorted_scores[1] if len(sorted_scores) > 1 else 0

    # Keep current page if confidence is similar to prevent noisy remaps.
    if 1 <= current_page <= len(scores):
        current_score = scores[current_page - 1]
        if current_score >= best_score - 1:
            return current_page

    # If we don't have a trusted current page, keep sequence continuity
    # for weak or ambiguous matches.
    if current_page <= 0:
        if best_score < 6:
            return fallback_page
        if (best_score - second_best) <= 1:
            fallback_score = scores[fallback_page - 1]
            if fallback_score >= best_score - 1:
                return fallback_page
        # Avoid noisy backward jumps unless clearly better than fallback.
        if best_page < fallback_page:
            fallback_score = scores[fallback_page - 1]
            if best_score <= fallback_score + 1:
                return fallback_page

    # Guard against weak matches.
    if best_score < 6:
        return current_page if current_page > 0 else fallback_page
    return best_page


def create_pdf_chunks(
    docs: List[Document],
    chunk_size: int = None,
    chunk_overlap: int = None,
    pdf_path: str = None
) -> List[Document]:
    """
    Create chunks from Docling-extracted documents with filtering.
    Extracts key-value pairs separately and labels chunks with document title.
    
    Args:
        docs: List of Document objects from Docling
        chunk_size: Maximum characters per chunk (default from CHUNK_SIZE env var)
        chunk_overlap: Overlap between chunks (default from CHUNK_OVERLAP env var)
        pdf_path: Path to source PDF file (for page assignment if needed)
    """
    chunk_size = chunk_size if chunk_size is not None else DEFAULT_CHUNK_SIZE
    chunk_overlap = chunk_overlap if chunk_overlap is not None else DEFAULT_CHUNK_OVERLAP
    all_chunks = []
    filtered_count = 0
    
    # Configurable chunk settings
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", ", ", " "]
    )

    for doc in docs:
        page_content = doc.page_content
        page_metadata = doc.metadata or {}
        source = page_metadata.get('source', 'unknown')
        # Get page number from metadata (may be 0 if not available)
        page_number = page_metadata.get('page', 0)
        file_label = get_file_label(source)
        
        # Log warning for page=0 but continue processing
        if page_number == 0:
            logging.debug(f"⚠️ Chunk from {source} has page=0 (will assign after chunking)")
        
        # Key-Value Extraction Logic
        kv_matches = _KV_PATTERN.findall(page_content)
        for key, value in kv_matches:
            key_clean = key.strip()
            value_clean = value.strip()
            
            # Stronger validation: require meaningful content
            # 1. Combined length > 25 chars (filters short garbage)
            # 2. Value must have real content (not just a label word)
            # 3. Reject section headers and step instructions
            combined_len = len(key_clean) + len(value_clean)
            value_has_content = len(value_clean) > 8 or any(c.isdigit() for c in value_clean)
            
            # Filter out garbage patterns
            is_section_header = value_clean.startswith('##') or value_clean.startswith('#')
            is_step_instruction = re.match(r'^-\s*\d+\s+', key_clean)  # "- 4 Fit the..."
            is_garbage = is_section_header or bool(is_step_instruction)
            
            if combined_len > 25 and value_has_content and not is_garbage:
                kv_content = f"{key_clean}: {value_clean}"
                kv_chunk = Document(
                    page_content=kv_content,
                    metadata=enhance_metadata(
                        {"source": os.path.basename(source), "page": page_number, "chunk_type": "spec_pair"},
                        kv_content
                    )
                )
                # Apply filtering
                is_valid, _ = is_valid_chunk(kv_chunk)
                if is_valid:
                    all_chunks.append(kv_chunk)
                else:
                    filtered_count += 1
        
        # Remove extracted key-value pairs from content using precompiled regex
        remaining_content = _KV_PATTERN.sub('', page_content)
        
        # === TABLE-AWARE SPLITTING ===
        # Extract tables and process them separately with row-based splitting
        tables, prose_content = extract_tables_and_prose(remaining_content)
        
        # Process tables with header-preserving splits
        for table in tables:
            table_chunks = split_table_by_rows(table, max_chars=chunk_size)
            for table_chunk_text in table_chunks:
                table_chunk = Document(
                    page_content=table_chunk_text,
                    metadata=enhance_metadata(
                        {"source": os.path.basename(source), "page": page_number, "chunk_type": "table"},
                        table_chunk_text
                    )
                )
                is_valid, _ = is_valid_chunk(table_chunk)
                if is_valid:
                    all_chunks.append(table_chunk)
                else:
                    filtered_count += 1
        
        # Process remaining prose content
        prose_content = clean_text(prose_content)
        
        # Create prose chunks
        if prose_content and len(prose_content.strip()) > 50:
            prose_chunks = text_splitter.create_documents([prose_content])
            for chunk in prose_chunks:
                chunk.metadata = enhance_metadata(
                    {"source": os.path.basename(source), "page": page_number, "chunk_type": "prose"},
                    chunk.page_content
                )
                # Apply filtering
                is_valid, _ = is_valid_chunk(chunk)
                if is_valid:
                    all_chunks.append(chunk)
                else:
                    filtered_count += 1

    # Always validate/remap pages against physical PDF text to prevent metadata drift.
    if all_chunks:
        first_source = all_chunks[0].metadata.get('source', 'unknown')
        resolved_pdf_path = _resolve_pdf_path(first_source, pdf_path)
        if resolved_pdf_path:
            try:
                page_texts = _build_pdf_page_texts(resolved_pdf_path)
                remapped_count = 0
                inferred_count = 0
                last_resolved_by_type = {}
                for chunk in all_chunks:
                    old_page = int(chunk.metadata.get("page", 0) or 0)
                    chunk_type = chunk.metadata.get("chunk_type", "unknown")
                    fallback_page = last_resolved_by_type.get(chunk_type, 1)
                    new_page = _resolve_chunk_page(
                        chunk.page_content,
                        page_texts,
                        old_page,
                        fallback_page=fallback_page
                    )
                    if old_page <= 0:
                        inferred_count += 1
                    if new_page != old_page:
                        remapped_count += 1
                    chunk.metadata["page"] = new_page
                    last_resolved_by_type[chunk_type] = new_page

                page_counts = {}
                for chunk in all_chunks:
                    p = int(chunk.metadata.get("page", 1) or 1)
                    page_counts[p] = page_counts.get(p, 0) + 1

                logging.info(
                    f"📊 Page validation complete: remapped={remapped_count}/{len(all_chunks)} "
                    f"(inferred_from_missing={inferred_count})"
                )
                logging.info(f"   Distribution across {len(page_texts)} pages: {dict(sorted(page_counts.items()))}")
            except Exception as e:
                logging.warning(f"⚠️ Failed page validation/remap for {first_source}: {e}")
        else:
            logging.warning(f"⚠️ Could not locate PDF for page validation: {first_source}")

    logging.info(f"✅ Created {len(all_chunks)} chunks (filtered out {filtered_count} trash chunks)")
    
    # Log chunk type distribution
    chunk_types = {}
    for chunk in all_chunks:
        ctype = chunk.metadata.get('chunk_type', 'unknown')
        chunk_types[ctype] = chunk_types.get(ctype, 0) + 1
    
    if chunk_types:
        logging.info(f"   Chunk types: {dict(sorted(chunk_types.items()))}")
    
    return all_chunks


def create_json_qa_chunks(file_path: str) -> List[Document]:
    """
    Create chunks from JSON QA file.

    Supports both schemas:
    - {"question": "...", "answer": "..."}
    - {"reference_question": "...", "reference_answer": "..."}
    """
    chunks = []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            qa_pairs = json.load(f)

        skipped = 0
        for pair in qa_pairs:
            question = (pair.get("question") or pair.get("reference_question") or "").strip()
            answer = (pair.get("answer") or pair.get("reference_answer") or "").strip()

            if not question or not answer:
                skipped += 1
                continue

            content = f"Question: {question}\nAnswer: {answer}"
            metadata = enhance_metadata(
                {"source": os.path.basename(file_path), "chunk_type": "golden_qa"},
                content
            )
            chunks.append(Document(page_content=content, metadata=metadata))
        logging.info("✅ Created %d chunks from Golden QA Set (skipped %d invalid rows).", len(chunks), skipped)
    except Exception as e:
        logging.error(f"🔥 Failed to process JSON file {file_path}: {e}")
    return chunks


def get_embedding_instruction(chunk_type: str) -> str:
    """Customize instruction based on chunk type for better embedding quality"""
    instructions = {
        "golden_qa": "Represent this authoritative question-answer pair for search: ",
        "spec_pair": "Represent this technical specification value for search: ",
        "table": "Represent this technical data table for search: ",
        "prose": "Represent this technical documentation paragraph for search: "
    }
    return instructions.get(chunk_type, "Represent this sentence for searching relevant passages: ")
