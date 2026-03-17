# Requirements Document

## Introduction

This document specifies requirements for enhancing the existing RAG (Retrieval-Augmented Generation) system to use full PDF page images as context instead of text chunks. The system currently retrieves text chunks from documents and sends them to an LLM. This enhancement will extract PDF pages as images during embedding, store them in a database, and send the corresponding page images to a vision-capable LLM after text-based retrieval identifies relevant pages.

## Glossary

- **RAG_System**: The Retrieval-Augmented Generation system that retrieves relevant document chunks and generates answers using an LLM
- **Embedding_Pipeline**: The process that extracts content from PDFs, creates text chunks, generates embeddings, and stores them in the database
- **Retrieval_Pipeline**: The process that finds relevant text chunks using vector similarity search and reranking
- **PDF_Page_Image**: A rasterized image representation of a single PDF page stored in PNG or JPEG format
- **Page_Image_Store**: A PostgreSQL table that stores PDF page images with metadata linking to source documents
- **Vision_LLM**: A large language model with vision capabilities (e.g., Gemini 1.5/2.0) that can process both text and images
- **Text_Chunk**: A segment of extracted text from a document with metadata including source and page number
- **Page_Metadata**: Information about a text chunk including document source, page number, chunk type, and position
- **Docling**: The PDF extraction library currently used to convert PDFs to markdown or structured chunks
- **DOC_CHUNKS**: A Docling export format that preserves page-level metadata for each extracted chunk
- **Context_Preparation**: The process of mapping selected text chunks to their source PDF page images before LLM generation

## Requirements

### Requirement 1: PDF Page Image Storage

**User Story:** As a system administrator, I want PDF pages stored as images in the database, so that the system can retrieve and send full page context to the vision LLM.

#### Acceptance Criteria

1. THE Embedding_Pipeline SHALL extract each PDF page as a separate image during document processing
2. THE Embedding_Pipeline SHALL store each PDF_Page_Image in the Page_Image_Store table with a unique identifier
3. THE Page_Image_Store SHALL store images in PNG format with 150 DPI resolution
4. THE Page_Image_Store SHALL include metadata fields: document_source, page_number, image_data, collection_name, created_at
5. WHEN a PDF has N pages, THE Embedding_Pipeline SHALL create exactly N entries in the Page_Image_Store
6. THE Embedding_Pipeline SHALL compress images to reduce storage size while maintaining readability for vision models

### Requirement 2: Page Number Metadata Tracking

**User Story:** As a developer, I want accurate page numbers in text chunk metadata, so that the system can correctly map chunks to their source PDF pages.

#### Acceptance Criteria

1. THE Embedding_Pipeline SHALL use Docling DOC_CHUNKS export format to preserve page numbers during extraction
2. WHEN creating a Text_Chunk, THE Embedding_Pipeline SHALL record the source page number in the Page_Metadata
3. THE Page_Metadata SHALL include fields: source (document filename), page (integer page number starting from 1), chunk_type
4. THE Embedding_Pipeline SHALL reject chunks with page number 0 or null values
5. WHEN re-embedding existing documents, THE Embedding_Pipeline SHALL delete old chunks and page images before creating new ones

### Requirement 3: Page Image Retrieval

**User Story:** As the RAG system, I want to retrieve PDF page images corresponding to selected text chunks, so that I can provide visual context to the vision LLM.

#### Acceptance Criteria

1. WHEN the Retrieval_Pipeline selects text chunks, THE Context_Preparation SHALL extract page numbers from each chunk's Page_Metadata
2. THE Context_Preparation SHALL query the Page_Image_Store using document source and page number to retrieve corresponding PDF_Page_Image entries
3. THE Context_Preparation SHALL return a list of PDF_Page_Image objects with their metadata
4. IF a page image is not found for a chunk, THE Context_Preparation SHALL log a warning and continue with available images
5. THE Context_Preparation SHALL complete page image retrieval within 500ms for up to 10 pages

### Requirement 4: Page Deduplication

**User Story:** As the RAG system, I want to send each PDF page only once to the LLM, so that I avoid redundant context when multiple chunks come from the same page.

#### Acceptance Criteria

1. WHEN multiple Text_Chunk entries reference the same page number and document source, THE Context_Preparation SHALL include that page image only once in the final context
2. THE Context_Preparation SHALL deduplicate pages based on the combination of document_source and page_number
3. THE Context_Preparation SHALL preserve the order of pages based on the highest-scoring chunk from each page
4. THE Context_Preparation SHALL return a deduplicated list of PDF_Page_Image objects sorted by relevance score

### Requirement 5: Top-N Page Selection with Overlap

**User Story:** As a system administrator, I want to limit the number of pages sent to the LLM, so that I control token usage and processing costs while maintaining context quality.

#### Acceptance Criteria

1. THE Context_Preparation SHALL accept a configurable parameter top_n_pages with a default value of 3
2. WHEN more than top_n_pages unique pages are identified, THE Context_Preparation SHALL select the top_n_pages pages with the highest relevance scores
3. WHERE a configuration enables page_overlap, THE Context_Preparation SHALL include adjacent pages (page_number ± 1) for selected pages
4. THE Context_Preparation SHALL respect a maximum limit of 10 pages regardless of overlap settings
5. THE Context_Preparation SHALL calculate relevance scores based on the maximum score of all chunks from each page

### Requirement 6: Vision LLM Integration

**User Story:** As the RAG system, I want to send PDF page images to a vision-capable LLM instead of text chunks, so that the LLM can understand context from the original document layout and visual elements.

#### Acceptance Criteria

1. THE RAG_System SHALL support Gemini 1.5 and Gemini 2.0 models with vision capabilities
2. WHEN generating an answer, THE RAG_System SHALL send PDF_Page_Image data to the Vision_LLM instead of text chunks
3. THE RAG_System SHALL format images according to the Vision_LLM's API requirements (base64 encoding or multipart format)
4. THE RAG_System SHALL include the user question as text input alongside the page images
5. THE Vision_LLM SHALL receive images in the order determined by the Context_Preparation relevance ranking
6. IF the Vision_LLM call fails, THE RAG_System SHALL log the error and return an appropriate error message to the user

### Requirement 7: Backward Compatibility Mode

**User Story:** As a system administrator, I want to toggle between text-based and image-based context modes, so that I can compare performance and fall back if needed.

#### Acceptance Criteria

1. THE RAG_System SHALL support a configuration parameter use_page_images with boolean values (true/false)
2. WHEN use_page_images is false, THE RAG_System SHALL use the existing text chunk context method
3. WHEN use_page_images is true, THE RAG_System SHALL use the PDF page image context method
4. THE RAG_System SHALL read the use_page_images setting from environment variables or configuration files
5. THE RAG_System SHALL log which context mode is active at startup

### Requirement 8: Database Schema Migration

**User Story:** As a database administrator, I want a migration script to create the page image storage table, so that the system can store and retrieve page images without manual schema changes.

#### Acceptance Criteria

1. THE Embedding_Pipeline SHALL provide a database migration script that creates the Page_Image_Store table
2. THE migration script SHALL create the table with columns: id (primary key), document_source (text), page_number (integer), image_data (bytea), collection_name (text), created_at (timestamp)
3. THE migration script SHALL create an index on (document_source, page_number, collection_name) for fast lookups
4. THE migration script SHALL be idempotent (safe to run multiple times)
5. THE migration script SHALL include a rollback function to drop the table if needed

### Requirement 9: Image Format Conversion

**User Story:** As the embedding pipeline, I want to convert PDF pages to optimized images, so that they are compatible with vision LLMs while minimizing storage and bandwidth.

#### Acceptance Criteria

1. THE Embedding_Pipeline SHALL use a PDF rendering library (PyMuPDF or pdf2image) to convert PDF pages to images
2. THE Embedding_Pipeline SHALL render pages at 150 DPI resolution
3. THE Embedding_Pipeline SHALL save images in PNG format with compression level 6
4. THE Embedding_Pipeline SHALL validate that each generated image is readable and non-corrupt before storage
5. IF image conversion fails for a page, THE Embedding_Pipeline SHALL log the error and continue processing remaining pages

### Requirement 10: Error Handling and Logging

**User Story:** As a developer, I want comprehensive error handling and logging for the page image pipeline, so that I can diagnose issues and monitor system health.

#### Acceptance Criteria

1. WHEN PDF page extraction fails, THE Embedding_Pipeline SHALL log the document name, page number, and error message
2. WHEN page image retrieval fails, THE Context_Preparation SHALL log the missing page details and continue with available images
3. WHEN the Vision_LLM API call fails, THE RAG_System SHALL log the error details and return a user-friendly error message
4. THE RAG_System SHALL log the number of pages sent to the Vision_LLM for each query
5. THE RAG_System SHALL include page image retrieval time in performance metrics logging
