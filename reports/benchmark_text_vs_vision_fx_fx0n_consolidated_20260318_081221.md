# Text vs Vision Benchmark (FX/FX0N-485ADP)

- Generated: 2026-03-18 08:12:21
- Benchmark user: `benchmark_20260318_071415@example.com`
- Total completed runs: 36
- Prefix used: `For FX/FX0N-485ADP manual: `

## Ground Truth Used

- Weight (`Q1A`, `Q1B`): `Approximately 0.3 kg (0.66 lbs)`
- Resistance (`Q2A`, `Q2B`): `330 Ω`
- Device Symbols (`Q3A`, `Q3B`): `X, Y, M, S, T, and C`

## Overall Mode Comparison

| Mode | Runs | Faithfulness Avg | Answer Relevancy Avg | Context Precision Avg | Context Recall Avg | Manual Match Avg | Fallback Count | Faith N/A | Rel N/A | CP N/A | CR N/A |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| text | 18 | N/A | N/A | N/A | N/A | 0.167 | 0 | 18 | 18 | 18 | 18 |
| vision | 18 | N/A | N/A | N/A | N/A | 0.500 | 9 | 18 | 18 | 18 | 18 |

## Per-Question Averages (Text vs Vision)

| QID | Mode | Runs | Faithfulness Avg | Answer Relevancy Avg | Context Precision Avg | Context Recall Avg | Manual Match Avg | CP N/A | CR N/A |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Q1A | text | 3 | N/A | N/A | N/A | N/A | 1.000 | 3 | 3 |
| Q1A | vision | 3 | N/A | N/A | N/A | N/A | 1.000 | 3 | 3 |
| Q1B | text | 3 | N/A | N/A | N/A | N/A | 0.000 | 3 | 3 |
| Q1B | vision | 3 | N/A | N/A | N/A | N/A | 1.000 | 3 | 3 |
| Q2A | text | 3 | N/A | N/A | N/A | N/A | 0.000 | 3 | 3 |
| Q2A | vision | 3 | N/A | N/A | N/A | N/A | 0.000 | 3 | 3 |
| Q2B | text | 3 | N/A | N/A | N/A | N/A | 0.000 | 3 | 3 |
| Q2B | vision | 3 | N/A | N/A | N/A | N/A | 1.000 | 3 | 3 |
| Q3A | text | 3 | N/A | N/A | N/A | N/A | 0.000 | 3 | 3 |
| Q3A | vision | 3 | N/A | N/A | N/A | N/A | 0.000 | 3 | 3 |
| Q3B | text | 3 | N/A | N/A | N/A | N/A | 0.000 | 3 | 3 |
| Q3B | vision | 3 | N/A | N/A | N/A | N/A | 0.000 | 3 | 3 |

## Detailed Runs

| # | QID | Mode Req | Mode Resp | Repeat | Faith | Rel | Ctx Prec | Ctx Rec | RAGAS Status | Fallback | Manual Match |
|---:|---|---|---|---:|---:|---:|---:|---:|---|---|---:|
| 1 | Q1A | text | text | 1 | N/A | N/A | N/A | N/A | error | - | 1.000 |
| 2 | Q1A | text | text | 2 | N/A | N/A | N/A | N/A | error | - | 1.000 |
| 3 | Q1A | text | text | 3 | N/A | N/A | N/A | N/A | error | - | 1.000 |
| 4 | Q1A | vision | vision | 1 | N/A | N/A | N/A | N/A | error | - | 1.000 |
| 5 | Q1A | vision | vision | 2 | N/A | N/A | N/A | N/A | error | - | 1.000 |
| 6 | Q1A | vision | vision | 3 | N/A | N/A | N/A | N/A | error | - | 1.000 |
| 7 | Q1B | text | text | 1 | N/A | N/A | N/A | N/A | error | - | 0.000 |
| 8 | Q1B | text | text | 2 | N/A | N/A | N/A | N/A | error | - | 0.000 |
| 9 | Q1B | text | text | 3 | N/A | N/A | N/A | N/A | error | - | 0.000 |
| 10 | Q1B | vision | vision | 1 | N/A | N/A | N/A | N/A | error | - | 1.000 |
| 11 | Q1B | vision | vision | 2 | N/A | N/A | N/A | N/A | error | - | 1.000 |
| 12 | Q1B | vision | vision | 3 | N/A | N/A | N/A | N/A | error | - | 1.000 |
| 13 | Q2A | text | text | 1 | N/A | N/A | N/A | N/A | error | - | 0.000 |
| 14 | Q2A | text | text | 2 | N/A | N/A | N/A | N/A | error | - | 0.000 |
| 15 | Q2A | text | text | 3 | N/A | N/A | N/A | N/A | error | - | 0.000 |
| 16 | Q2A | vision | text | 1 | N/A | N/A | N/A | N/A | error | vision_not_found | 0.000 |
| 17 | Q2A | vision | text | 2 | N/A | N/A | N/A | N/A | error | vision_not_found | 0.000 |
| 18 | Q2A | vision | text | 3 | N/A | N/A | N/A | N/A | error | vision_not_found | 0.000 |
| 19 | Q2B | text | text | 1 | N/A | N/A | N/A | N/A | error | - | 0.000 |
| 20 | Q2B | text | text | 2 | N/A | N/A | N/A | N/A | error | - | 0.000 |
| 21 | Q2B | text | text | 3 | N/A | N/A | N/A | N/A | error | - | 0.000 |
| 22 | Q2B | vision | vision | 1 | N/A | N/A | N/A | N/A | error | - | 1.000 |
| 23 | Q2B | vision | vision | 2 | N/A | N/A | N/A | N/A | error | - | 1.000 |
| 24 | Q2B | vision | vision | 3 | N/A | N/A | N/A | N/A | error | - | 1.000 |
| 25 | Q3A | text | text | 1 | N/A | N/A | N/A | N/A | error | - | 0.000 |
| 26 | Q3A | text | text | 2 | N/A | N/A | N/A | N/A | error | - | 0.000 |
| 27 | Q3A | text | text | 3 | N/A | N/A | N/A | N/A | error | - | 0.000 |
| 28 | Q3A | vision | text | 1 | N/A | N/A | N/A | N/A | error | vision_not_found | 0.000 |
| 29 | Q3A | vision | text | 2 | N/A | N/A | N/A | N/A | error | vision_not_found | 0.000 |
| 30 | Q3A | vision | text | 3 | N/A | N/A | N/A | N/A | error | vision_not_found | 0.000 |
| 31 | Q3B | text | text | 1 | N/A | N/A | N/A | N/A | error | - | 0.000 |
| 32 | Q3B | text | text | 2 | N/A | N/A | N/A | N/A | error | - | 0.000 |
| 33 | Q3B | text | text | 3 | N/A | N/A | N/A | N/A | error | - | 0.000 |
| 34 | Q3B | vision | text | 1 | N/A | N/A | N/A | N/A | error | vision_not_found | 0.000 |
| 35 | Q3B | vision | text | 2 | N/A | N/A | N/A | N/A | error | vision_not_found | 0.000 |
| 36 | Q3B | vision | text | 3 | N/A | N/A | N/A | N/A | error | vision_not_found | 0.000 |

## Answer Snapshots

- `#1 Q1A text rep1`: The weight of the **FX-485ADP** is approximately **0.3 kg (0.66 lbs)**.
- `#2 Q1A text rep2`: The weight for the **FX-485ADP** is approximately 0.3 kg (0.66 lbs).
- `#3 Q1A text rep3`: The weight for the **FX-485ADP** is approximately 0.3 kg (0.66 lbs).
- `#4 Q1A vision rep1`: The weight listed for the **FX-485ADP** unit is approximately **0.3 kg (0.66 lbs)**.
- `#5 Q1A vision rep2`: According to the external dimensions diagram for the **FX-485ADP**, the weight is listed as approximately **0.3 kg (0.66 lbs)**.
- `#6 Q1A vision rep3`: According to the external dimensions diagram for the **FX-485ADP**, the weight is approximately **0.3 kg (0.66 lbs)**.
- `#7 Q1B text rep1`: I couldn't find specific information about this.
- `#8 Q1B text rep2`: I couldn't find specific information about this.
- `#9 Q1B text rep3`: I couldn't find specific information about this.
- `#10 Q1B vision rep1`: The approximate mass of the **FX0N-485ADP** device is **0.3 kg (0.66 lbs)**.
- `#11 Q1B vision rep2`: The approximate mass of the **FX0N-485ADP** is **0.3 kg** (0.66 lbs).
- `#12 Q1B vision rep3`: Based on the technical drawing for the **FX0N-485ADP**, the approximate mass of the device is **0.3 kg (0.66 lbs)**.
- `#13 Q2A text rep1`: I couldn't find specific information about this.
- `#14 Q2A text rep2`: I couldn't find specific information about this.
- `#15 Q2A text rep3`: I couldn't find specific information about this.
- `#16 Q2A vision rep1`: I couldn't find specific information about this.
- `#17 Q2A vision rep2`: I couldn't find specific information about this.
- `#18 Q2A vision rep3`: I couldn't find specific information about this.
- `#19 Q2B text rep1`: I couldn't find specific information about this.
- `#20 Q2B text rep2`: I couldn't find specific information about this.
- `#21 Q2B text rep3`: I couldn't find specific information about this.
- `#22 Q2B vision rep1`: When using an **RS-422** circuit, the required value for the 1/4W terminating resistor is **330 Ω**.
- `#23 Q2B vision rep2`: When communicating with an **RS-422** circuit, the required value for the terminating resistor is **330 Ω**.
- `#24 Q2B vision rep3`: When using an **RS-422** circuit, the required value for the 1/4W terminating resistor is **330 Ω**.
- `#25 Q3A text rep1`: I couldn't find specific information about this.
- `#26 Q3A text rep2`: I couldn't find specific information about this.
- `#27 Q3A text rep3`: I couldn't find specific information about this.
- `#28 Q3A vision rep1`: I couldn't find specific information about this.
- `#29 Q3A vision rep2`: I couldn't find specific information about this.
- `#30 Q3A vision rep3`: I couldn't find specific information about this.
- `#31 Q3B text rep1`: I couldn't find specific information about this.
- `#32 Q3B text rep2`: I couldn't find specific information about this.
- `#33 Q3B text rep3`: I couldn't find specific information about this.
- `#34 Q3B vision rep1`: I couldn't find specific information about this.
- `#35 Q3B vision rep2`: I couldn't find specific information about this.
- `#36 Q3B vision rep3`: I couldn't find specific information about this.

## Notes

- Because every question was prefixed, ground-truth lookup did not always match exactly; this can drive `context_precision/context_recall` to `N/A`.
- Metric-level timeouts can also cause `N/A` even when answer text looks correct.
- Manual-match score is a simple heuristic against your provided expected answers.
