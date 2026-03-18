# Text vs Vision Benchmark (FX/FX0N-485ADP)

- Generated: 2026-03-18 13:55:02
- Benchmark user: `benchmark_20260318_135502@example.com`
- Total completed runs: 13
- Prefix used: `For FX/FX0N-485ADP manual: `
- RAGAS ground-truth mode: `injected_expected_answer`

## Ground Truth Used

- Weight (`Q1A`, `Q1B`): `Approximately 0.3 kg (0.66 lbs)`
- Resistance (`Q2A`, `Q2B`): `330 Ω`
- Device Symbols (`Q3A`, `Q3B`): `X, Y, M, S, T, and C`

## Overall Mode Comparison

| Mode | Runs | Faithfulness Avg | Answer Relevancy Avg | Context Precision Avg | Context Recall Avg | Manual Match Avg | Fallback Count | Faith N/A | Rel N/A | CP N/A | CR N/A |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| text | 7 | 1.000 | 0.450 | 0.464 | 0.571 | 0.571 | 0 | 0 | 0 | 0 | 0 |
| vision | 6 | 1.000 | 0.877 | 1.000 | 1.000 | 1.000 | 0 | 0 | 0 | 0 | 0 |

## Per-Question Averages (Text vs Vision)

| QID | Mode | Runs | Faithfulness Avg | Answer Relevancy Avg | Context Precision Avg | Context Recall Avg | Manual Match Avg | CP N/A | CR N/A |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Q1A | text | 3 | 1.000 | 0.817 | 1.000 | 1.000 | 1.000 | 0 | 0 |
| Q1A | vision | 3 | 1.000 | 0.852 | 1.000 | 1.000 | 1.000 | 0 | 0 |
| Q1B | text | 3 | 1.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0 | 0 |
| Q1B | vision | 3 | 1.000 | 0.902 | 1.000 | 1.000 | 1.000 | 0 | 0 |
| Q2A | text | 1 | 1.000 | 0.699 | 0.250 | 1.000 | 1.000 | 0 | 0 |
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
| 3 | Q1A | text | text | 3 | 1.000 | 0.817 | 1.000 | 1.000 | complete | - | 1.000 |
| 4 | Q1A | vision | vision | 1 | 1.000 | 0.852 | 1.000 | 1.000 | complete | - | 1.000 |
| 5 | Q1A | vision | vision | 2 | 1.000 | 0.852 | 1.000 | 1.000 | complete | - | 1.000 |
| 6 | Q1A | vision | vision | 3 | 1.000 | 0.852 | 1.000 | 1.000 | complete | - | 1.000 |
| 7 | Q1B | text | text | 1 | 1.000 | 0.000 | 0.000 | 0.000 | complete | - | 0.000 |
| 8 | Q1B | text | text | 2 | 1.000 | 0.000 | 0.000 | 0.000 | complete | - | 0.000 |
| 9 | Q1B | text | text | 3 | 1.000 | 0.000 | 0.000 | 0.000 | complete | - | 0.000 |
| 10 | Q1B | vision | vision | 1 | 1.000 | 0.902 | 1.000 | 1.000 | complete | - | 1.000 |
| 11 | Q1B | vision | vision | 2 | 1.000 | 0.902 | 1.000 | 1.000 | complete | - | 1.000 |
| 12 | Q1B | vision | vision | 3 | 1.000 | 0.902 | 1.000 | 1.000 | complete | - | 1.000 |
| 13 | Q2A | text | text | 1 | 1.000 | 0.699 | 0.250 | 1.000 | complete | - | 1.000 |

## Answer Snapshots

- `#1 Q1A text rep1`: The weight for the **FX-485ADP** is approximately **0.3 kg (0.66 lbs)**.
- `#2 Q1A text rep2`: The weight for the **FX-485ADP** is approximately **0.3 kg (0.66 lbs)**.
- `#3 Q1A text rep3`: The weight for the **FX-485ADP** is approximately **0.3 kg (0.66 lbs)**.
- `#4 Q1A vision rep1`: According to the external dimensions diagram for the **FX-485ADP**, the weight of the unit is approximately **0.3 kg (0.66 lbs)**.
- `#5 Q1A vision rep2`: According to the external dimensions diagram for the **FX-485ADP**, the weight of the unit is approximately **0.3 kg (0.66 lbs)**.
- `#6 Q1A vision rep3`: According to the external dimensions diagram for the **FX-485ADP**, the weight of the unit is approximately **0.3 kg (0.66 lbs)**.
- `#7 Q1B text rep1`: I couldn't find specific information about this.
- `#8 Q1B text rep2`: I couldn't find specific information about this.
- `#9 Q1B text rep3`: I couldn't find specific information about this.
- `#10 Q1B vision rep1`: The approximate mass of the **FX0N-485ADP** is **0.3 kg (0.66 lbs)**.
- `#11 Q1B vision rep2`: The approximate mass of the **FX0N-485ADP** is **0.3 kg (0.66 lbs)**.
- `#12 Q1B vision rep3`: The approximate mass of the **FX0N-485ADP** is **0.3 kg (0.66 lbs)**.
- `#13 Q2A text rep1`: For the **two-pair wiring** (RS-422 circuit) configuration, the terminating resistance (**R**) that must be connected between terminals `SDA` and `SDB` is **330 Ω**.

## Notes

- `ragas_status=error` count: 0
- `ragas_status=pending` count: 0
- runs with all 4 metrics present: 13/13
- Manual-match score is a simple heuristic against expected answers.
- For fairness, benchmark injects exact `expected_answer` as `ragas_ground_truth` on each request.


## Run Status

- This run ended early.
- Reason: `KeyboardInterrupt`
