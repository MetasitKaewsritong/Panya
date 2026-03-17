# Implementation Tasks: PDF Page Context RAG Enhancement

## Task 1: Database Schema Setup

Create database migration for pdf_pages table and verify schema.

### Sub-tasks:
- [ ] 1.1 Create migration script `backend/migrations/001_create_pdf_pages.sql`
- [ ] 1.2 Create migration runner script `backend/run_migration.py`
- [ ] 1.3 Run migration to create pdf_pages table
- [ ] 1.4 Verify table and indexes are created correctly

## Task 2: Page Image Extraction Module

Implement PDF page rendering and image extraction functionality.

### Sub-tasks:
- [ ] 2.1 Add PyMuPDF and Pillow to `backend/requirements.txt`
- [ ] 2.2 Create `backend/app/pdf_image_utils.py` with page extraction functions
- [ ] 2.3 Implement `extract_pdf_page_images()` function
- [ ] 2.4 Implement `store_page_images()` function
- [ ] 2.5 Add unit tests for image extraction

## Task 3: Update Embedding Pipeline

Modify embed.py to use DOC_CHUNKS export and store page images.

### Sub-tasks:
- [ ] 3.1 Change Docling export type from MARKDOWN to DOC_CHUNKS in `backend/embed.py`
- [ ] 3.2 Integrate page image extraction into main embedding flow
- [ ] 3.3 Add page image storage after PDF processing
- [ ] 3.4 Update logging to show page image extraction progress
- [ ] 3.5 Test embedding with a sample PDF

## Task 4: Context Preparation Module

Create module for extracting unique pages and fetching images from database.

### Sub-tasks:
- [ ] 4.1 Create `backend/app/context_prep.py`
- [ ] 4.2 Implement `extract_unique_pages()` function
- [ ] 4.3 Implement `fetch_page_images()` function
- [ ] 4.4 Implement `prepare_page_context()` main function
- [ ] 4.5 Add unit tests for context preparation

## Task 5: Vision LLM Integration

Integrate Gemini vision API for image-based context generation.

### Sub-tasks:
- [ ] 5.1 Add `USE_PAGE_IMAGES` configuration to `.env`
- [ ] 5.2 Create vision prompt template in `backend/app/chatbot.py`
- [ ] 5.3 Implement image encoding helper function
- [ ] 5.4 Modify `answer_question()` to support image-based context
- [ ] 5.5 Add fallback logic to text-based context if images unavailable
- [ ] 5.6 Update logging for vision LLM calls

## Task 6: Backward Compatibility & Configuration

Ensure system can toggle between text and image modes.

### Sub-tasks:
- [ ] 6.1 Add configuration variables to `.env.example`
- [ ] 6.2 Add startup logging to show which mode is active
- [ ] 6.3 Test text-based mode (USE_PAGE_IMAGES=false)
- [ ] 6.4 Test image-based mode (USE_PAGE_IMAGES=true)
- [ ] 6.5 Verify fallback behavior when images are missing

## Task 7: Re-embed Existing Documents

Re-process existing PDFs with new pipeline to populate page images.

### Sub-tasks:
- [ ] 7.1 Backup existing documents table
- [ ] 7.2 Clear old chunks for documents to be re-embedded
- [ ] 7.3 Re-run embed.py on existing PDFs with DOC_CHUNKS export
- [ ] 7.4 Verify page numbers in metadata are correct (not 0)
- [ ] 7.5 Verify page images are stored in pdf_pages table

## Task 8: Integration Testing

Test end-to-end workflow with real queries.

### Sub-tasks:
- [ ] 8.1 Test query with image-based context enabled
- [ ] 8.2 Verify correct pages are retrieved and sent to LLM
- [ ] 8.3 Compare answers: text-based vs image-based
- [ ] 8.4 Monitor token consumption in logs
- [ ] 8.5 Test error scenarios (missing images, API failures)

## Task 9: Documentation & Cleanup

Update documentation and clean up code.

### Sub-tasks:
- [ ] 9.1 Update README.md with new feature description
- [ ] 9.2 Add inline code comments for new functions
- [ ] 9.3 Update .env.example with new configuration options
- [ ] 9.4 Create troubleshooting guide for common issues
- [ ] 9.5 Remove any debug logging or temporary code
