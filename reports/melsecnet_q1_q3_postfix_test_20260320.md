# MELSECNET Q1A-Q3B Post-Fix Benchmark Report (2026-03-20)

## Test Run Info
- **Date:** 2026-03-20 09:00 (local) / 02:00 UTC
- **Benchmark script:** `tools/run_melsecnet_q1_q3_benchmark.py`
- **LLM:** gemma3:4b (Ollama)
- **Intent LLM:** phi4-mini:latest (Ollama)
- **Fixes applied:**
  1. Intent extractor fallback (no more "I don't understand" short-circuit)
  2. Page overlap n±1 (`PAGE_OVERLAP_RADIUS=1`)
- **Source JSON:** `backend/eval_reports/melsecnet_q1_q3_benchmark_20260320_015641.json`

---

## Before vs After Comparison

| Metric | Before (pre-fix) | After (post-fix) | Change |
|--------|:-:|:-:|:-:|
| "I don't understand" replies | 3/12 | **0/12** | ✅ Fixed |
| Vision mode fallback to text | 2/6 | **0/6** | ✅ Fixed |
| Vision `response_mode=vision` | 4/6 | **6/6** | ✅ Fixed |
| Exact model hits | 0/12 | 0/12 | — |
| Text `answer_match` avg | 0.129 | 0.068 | ⚠️ |
| Vision `answer_match` avg | 0.073 | **0.120** | ↑ improved |
| Page overlap (adjacent pages) | N/A | **6 pages/query** | ✅ New |
| RAGAS primary metrics | all null | all null (pending) | — |

---

## Detailed Run Results

### Q1: Network Module Model (expected: `QJ71LP21-25`)

| # | Mode | Hit | Match | Answer (truncated) |
|---|------|-----|-------|---------------------|
| 1 | text | ❌ | 0.036 | Q-series PLC models 10NS2 to 10NS5 |
| 2 | vision | ❌ | 0.022 | SCHOOL-Q.NET10H-E (Model Code: 13JW52) |
| 3 | text | ❌ | 0.023 | Network No.1 - Model Name: Q02H |
| 4 | vision | ❌ | **0.302** | **Q71LP21/Q71LP21/Q71LP25/Q71B** (Q71BR11) — *close!* |

### Q2: Remote I/O Module Model (expected: `QJ72LP25-25`)

| # | Mode | Hit | Match | Answer (truncated) |
|---|------|-----|-------|---------------------|
| 5 | text | ❌ | **0.320** | Lists QJ71LP21, **QJ71LP21-25**, QJ71BR21 — *related models, not exact* |
| 6 | vision | ❌ | 0.047 | Q71PLP21 repeated — *vision hallucination* |
| 7 | text | ❌ | 0.006 | QCPU selected for MELSECNET/H remote I/O |
| 8 | vision | ❌ | **0.142** | Remote I/O station identified as **QJ72** and QJ71 — *partial match!* |

### Q3: Coaxial Network Module (expected: `QJ71BR11`)

| # | Mode | Hit | Match | Answer (truncated) |
|---|------|-----|-------|---------------------|
| 9 | text | ❌ | 0.012 | Describes coaxial bus specs, doesn't name model |
| 10 | vision | ❌ | **0.197** | Coaxial bus uses **Q71LP21** model — *wrong model, close format* |
| 11 | text | ❌ | 0.010 | Describes MELSECNET/H specs — *was "I don't understand" before* ✅ |
| 12 | vision | ❌ | 0.009 | Describes coaxial specs — *was "I don't understand" before* ✅ |

---

## Analysis

### What's Fixed ✅
1. **No more pipeline short-circuits** — All 12 runs now go through full retrieval → rerank → LLM
2. **Vision mode works correctly** — All 6 vision requests are answered in vision mode
3. **Page overlap working** — Each query gets ~6 additional adjacent pages for context

### Remaining Issue: 0/12 Exact Hits ⚠️

The LLM (`gemma3:4b`) **sees the right pages** but doesn't extract the precise model number. Instead, it provides:
- General specifications (transmission speed, point counts)
- Related but wrong model numbers (Q02H, 13JW52, Q71PLP21)
- Close matches that mention partial model numbers (Q71LP21, QJ72)

> [!NOTE]
> **Root cause:** `gemma3:4b` is a 4B parameter model. It struggles with:
> - Extracting exact alphanumeric identifiers from dense PDF tables
> - Distinguishing between similar model numbers (QJ71LP21 vs QJ71LP21-25 vs QJ72LP25-25)
> - The vision model misreads characters (e.g., "Q71PLP21" instead of "QJ71LP21")
>
> **Recommended next steps:**
> 1. **Upgrade LLM** to a larger model (gemma3:12b or qwen3) for better extraction
> 2. **Add golden QA entries** for these specific questions so the reranker can boost exact answers
> 3. **Increase `RAG_FINAL_K`** from 3 to 5 to send more pages to the LLM
