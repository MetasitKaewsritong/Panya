# MELSECNET Q1A-Q3B Text vs Vision Test Report (2026-03-20)

## Scope
- Ran chatbot tests for: Q1A, Q1B, Q2A, Q2B, Q3A, Q3B.
- Each question was tested in both modes: text and vision.
- Expected answers used:
  - Q1A/Q1B: `QJ71LP21-25`
  - Q2A/Q2B: `QJ72LP25-25`
  - Q3A/Q3B: `QJ71BR11`

## Execution
- Command:
  - `docker compose exec -T backend python tools/run_melsecnet_q1_q3_benchmark.py`
- Runtime output indicated 12 completed runs (6 questions x 2 modes).

## Raw Output Files
- JSON (full run-by-run data): `backend/eval_reports/melsecnet_q1_q3_benchmark_20260320_011022.json`
- Markdown (auto-generated benchmark report): `backend/eval_reports/melsecnet_q1_q3_benchmark_20260320_011022.md`

## Result Summary
- Total runs: 12
- Exact expected-model hits: 0/12
- Text mode exact hit rate: 0/6
- Vision mode exact hit rate: 0/6
- Vision mode response mismatch (requested vision but response mode text): 2/6
  - Q2A vision
  - Q3B vision
- "I don't understand" replies: 3/12
  - Q2A vision
  - Q3B text
  - Q3B vision

## Metric Availability
- `faithfulness`: unavailable for all runs
- `answer_relevancy`: unavailable for all runs
- `context_precision`: unavailable for all runs
- `context_recall`: unavailable for all runs
- `answer_match` (available in some runs):
  - text average: 0.12896
  - vision average: 0.073225

## Key Findings
- The current system did not return the expected model IDs for any Q1A-Q3B test prompt.
- Vision mode was not consistently honored (some vision requests answered in text mode).
- RAGAS metrics needed for deeper quality analysis were mostly pending/disabled in this run, so final quality conclusions rely mainly on exact-hit and answer text inspection.
