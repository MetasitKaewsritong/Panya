# PLC Assistant

An AI-powered chatbot for **industrial automation** and **PLCnext** technical support. Uses **RAG (Retrieval-Augmented Generation)** to answer questions from your PLC documentation.

## Key Features

- **RAG-Powered Answers** - Retrieves information from embedded documents for accurate responses
- **Multi-Input Support** - Text, and voice (Whisper)
- **Local Ollama LLM Backend** - Uses Qwen3-VL GGUF models through Ollama's OpenAI-compatible API
- **Intent Extraction Stage** - Uses `phi4-mini` to extract `brand`, `model/subbrand`, `intent`, and a normalized retrieval query before retrieval
- **GPU Accelerated** - NVIDIA GPU support for 5-10x faster responses

## Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend | React + Vite + TailwindCSS |
| Backend | FastAPI (Python) |
| Database | PostgreSQL + pgvector |
| LLM | Ollama + Qwen3-VL-4B-Thinking-GGUF |
| Embeddings | BAAI/bge-m3 |
| Deployment | Docker Compose |

## Quick Start

### Prerequisites

- Ollama installed and running
- Docker Desktop (with GPU support for NVIDIA)
- 8GB+ RAM recommended

### Installation

Pull the Ollama models first, then start the Docker services.

```bash
# 1. Clone the repository
git clone <your-repo-url>
cd new-chat-bot

# 2. Create environment file
cp .env.example .env

# 3. Pull the local Ollama models
ollama pull hf.co/Qwen/Qwen3-VL-4B-Thinking-GGUF:Q4_K_M
ollama pull phi4-mini

# 4. Start all services
docker compose up -d

```

### Access

- **Frontend:** http://localhost:5173
- **Backend API:** http://localhost:5000
- **pgAdmin:** http://localhost:5050 (admin@admin.com / admin)

## Embedding Documents

To add your own documents to the knowledge base:

### 1. Map your folder in `docker-compose.yml`

```yaml
services:
  backend:
    volumes:
      - ./backend:/app
      - "D:/YourDocs:/app/data/custom"  # Add your path
```

### 2. Restart and run embed command

```bash
# Restart to apply volume changes
docker compose restart backend

# Embed all PDFs in folder
docker compose exec backend python embed.py //app/data/custom \
  --brand Mitsubishi \
  --model FX3U

# Embed specific file
docker compose exec backend python embed.py //app/data/custom/manual.pdf \
  --brand Mitsubishi \
  --model FX3U

# Dry-run (preview only)
docker compose exec backend python embed.py //app/data/custom \
  --brand Mitsubishi \
  --model FX3U \
  --dry-run

# Custom options
docker compose exec backend python embed.py //app/data/custom \
  --brand Mitsubishi \
  --model FX3U \
  --collection plcnext \
  --batch-size 500
```

Each PDF page is now rendered once, sent to `gemma3:4b` for a single page summary, then that summary text is embedded into pgvector. The rendered page image is stored separately in `pdf_pages` with the same `source`, `page`, `brand`, and `model_subbrand` metadata.

### Embed Options

| Option | Default | Description |
|--------|---------|-------------|
| `--brand` | required | Brand metadata stored on every row |
| `--model-subbrand` / `--model` | required | Model or subbrand metadata stored on every row |
| `--collection` | `plcnext` | Vector store collection name |
| `--batch-size` | `1000` | Embeddings per batch |
| `--summary-model` | `gemma3:4b` | Model used to summarize each PDF page |
| `--replace-existing` | `false` | Rebuild existing records for the same source |
| `--dry-run` | `false` | Preview without saving |

## Common Commands

```bash
# Start all services
docker compose up -d

# View backend logs
docker compose logs -f backend

# Restart backend after code changes
docker compose restart backend

# Stop all services (keeps data)
docker compose down

# Stop and delete all data (caution!)
docker compose down -v
```

## Optional RAGAS Check

If you want `context_precision` and `context_recall` (ground-truth evaluation):

```bash
docker compose exec backend pip install -r requirements-ragas.txt
docker compose exec backend python -m app.ragas_ground_truth_eval \
  --question "Your question here" \
  --ground-truth "Reference answer here"
```

## Environment Variables

Key settings in `.env`:

```env
# LLM
LLM_PROVIDER=ollama
LLM_API_KEY=ollama-local-key
LLM_MODEL=hf.co/Qwen/Qwen3-VL-4B-Thinking-GGUF:Q4_K_M
LLM_BASE_URL=http://host.docker.internal:11434/v1
LLM_TEMPERATURE=0.7

# Intent extraction before rerank
INTENT_LLM_ENABLED=true
INTENT_LLM_MODEL=phi4-mini:latest
INTENT_LLM_TEMPERATURE=0.0

# Embeddings
EMBED_MODEL=BAAI/bge-m3

# RAG Settings
RETRIEVE_LIMIT=50
RERANK_TOPN=8
```

## Provider Setup

The default setup uses local Ollama. If you run the backend in Docker, keep `LLM_BASE_URL=http://host.docker.internal:11434/v1` so the container can reach Ollama on your Windows host. If you run the backend directly on Windows instead of Docker, use `http://localhost:11434/v1`.

## License

MIT License
