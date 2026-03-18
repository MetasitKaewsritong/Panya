# Text vs Vision Benchmark (FX/FX0N-485ADP)

- Generated: 2026-03-18 13:52:16
- Benchmark user: `benchmark_20260318_135216@example.com`
- Total completed runs: 2
- Prefix used: `For FX/FX0N-485ADP manual: `
- RAGAS ground-truth mode: `injected_expected_answer`

## Ground Truth Used

- Weight (`Q1A`, `Q1B`): `Approximately 0.3 kg (0.66 lbs)`
- Resistance (`Q2A`, `Q2B`): `330 Ω`
- Device Symbols (`Q3A`, `Q3B`): `X, Y, M, S, T, and C`

## Overall Mode Comparison

| Mode | Runs | Faithfulness Avg | Answer Relevancy Avg | Context Precision Avg | Context Recall Avg | Manual Match Avg | Fallback Count | Faith N/A | Rel N/A | CP N/A | CR N/A |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| text | 2 | 1.000 | 0.817 | 1.000 | 1.000 | 1.000 | 0 | 0 | 0 | 0 | 0 |
| vision | 0 | N/A | N/A | N/A | N/A | N/A | 0 | 0 | 0 | 0 | 0 |

## Per-Question Averages (Text vs Vision)

| QID | Mode | Runs | Faithfulness Avg | Answer Relevancy Avg | Context Precision Avg | Context Recall Avg | Manual Match Avg | CP N/A | CR N/A |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Q1A | text | 2 | 1.000 | 0.817 | 1.000 | 1.000 | 1.000 | 0 | 0 |
| Q1A | vision | 0 | N/A | N/A | N/A | N/A | N/A | 0 | 0 |
| Q1B | text | 0 | N/A | N/A | N/A | N/A | N/A | 0 | 0 |
| Q1B | vision | 0 | N/A | N/A | N/A | N/A | N/A | 0 | 0 |
| Q2A | text | 0 | N/A | N/A | N/A | N/A | N/A | 0 | 0 |
| Q2A | vision | 0 | N/A | N/A | N/A | N/A | N/A | 0 | 0 |
| Q2B | text | 0 | N/A | N/A | N/A | N/A | N/A | 0 | 0 |
| Q2B | vision | 0 | N/A | N/A | N/A | N/A | N/A | 0 | 0 |
| Q3A | text | 0 | N/A | N/A | N/A | N/A | N/A | 0 | 0 |
| Q3A | vision | 0 | N/A | N/A | N/A | N/A | N/A | 0 | 0 |
| Q3B | text | 0 | N/A | N/A | N/A | N/A | N/A | 0 | 0 |
| Q3B | vision | 0 | N/A | N/A | N/A | N/A | N/A | 0 | 0 |

## Detailed Runs

| # | QID | Mode Req | Mode Resp | Repeat | Faith | Rel | Ctx Prec | Ctx Rec | RAGAS Status | Fallback | Manual Match |
|---:|---|---|---|---:|---:|---:|---:|---:|---|---|---:|
| 1 | Q1A | text | text | 1 | 1.000 | 0.817 | 1.000 | 1.000 | complete | - | 1.000 |
| 2 | Q1A | text | text | 2 | 1.000 | 0.817 | 1.000 | 1.000 | complete | - | 1.000 |

## Answer Snapshots

- `#1 Q1A text rep1`: The weight for the **FX-485ADP** is approximately **0.3 kg (0.66 lbs)**.
- `#2 Q1A text rep2`: The weight for the **FX-485ADP** is approximately **0.3 kg (0.66 lbs)**.

## Notes

- `ragas_status=error` count: 0
- `ragas_status=pending` count: 0
- runs with all 4 metrics present: 2/2
- Manual-match score is a simple heuristic against expected answers.
- For fairness, benchmark injects exact `expected_answer` as `ragas_ground_truth` on each request.


## Run Status

- This run ended early.
- Reason: `KeyboardInterrupt`
