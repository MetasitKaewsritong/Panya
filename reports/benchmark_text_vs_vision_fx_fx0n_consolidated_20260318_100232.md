# Text vs Vision Benchmark (FX/FX0N-485ADP)

- Generated: 2026-03-18 10:02:32
- Benchmark user: `benchmark_20260318_100232@example.com`
- Total completed runs: 36
- Prefix used: `For FX/FX0N-485ADP manual: `

## Ground Truth Used

- Weight (`Q1A`, `Q1B`): `Approximately 0.3 kg (0.66 lbs)`
- Resistance (`Q2A`, `Q2B`): `330 Ω`
- Device Symbols (`Q3A`, `Q3B`): `X, Y, M, S, T, and C`

## Overall Mode Comparison

| Mode | Runs | Faithfulness Avg | Answer Relevancy Avg | Context Precision Avg | Context Recall Avg | Manual Match Avg | Fallback Count | Faith N/A | Rel N/A | CP N/A | CR N/A |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| text | 18 | 0.688 | 0.153 | 0.292 | 0.385 | 0.222 | 0 | 2 | 2 | 6 | 5 |
| vision | 18 | 0.647 | 0.422 | 0.571 | 0.357 | 0.500 | 10 | 1 | 2 | 4 | 4 |

## Per-Question Averages (Text vs Vision)

| QID | Mode | Runs | Faithfulness Avg | Answer Relevancy Avg | Context Precision Avg | Context Recall Avg | Manual Match Avg | CP N/A | CR N/A |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Q1A | text | 3 | 1.000 | 0.817 | 1.000 | 1.000 | 1.000 | 0 | 0 |
| Q1A | vision | 3 | 1.000 | 0.852 | 1.000 | 1.000 | 0.667 | 1 | 1 |
| Q1B | text | 3 | 1.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0 | 0 |
| Q1B | vision | 3 | 1.000 | 0.902 | 1.000 | 0.000 | 1.000 | 0 | 0 |
| Q2A | text | 3 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 1 | 1 |
| Q2A | vision | 3 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0 | 0 |
| Q2B | text | 3 | 1.000 | 0.000 | 0.500 | 1.000 | 0.000 | 2 | 1 |
| Q2B | vision | 3 | 1.000 | 0.779 | 1.000 | 1.000 | 1.000 | 0 | 0 |
| Q3A | text | 3 | 1.000 | 0.000 | 0.000 | 0.000 | 0.167 | 0 | 0 |
| Q3A | vision | 3 | 1.000 | 0.000 | 0.000 | 0.000 | 0.167 | 0 | 0 |
| Q3B | text | 3 | 0.000 | 0.000 | N/A | N/A | 0.167 | 3 | 3 |
| Q3B | vision | 3 | 0.000 | 0.000 | N/A | N/A | 0.167 | 3 | 3 |

## Detailed Runs

| # | QID | Mode Req | Mode Resp | Repeat | Faith | Rel | Ctx Prec | Ctx Rec | RAGAS Status | Fallback | Manual Match |
|---:|---|---|---|---:|---:|---:|---:|---:|---|---|---:|
| 1 | Q1A | text | text | 1 | 1.000 | 0.817 | 1.000 | 1.000 | complete | - | 1.000 |
| 2 | Q1A | text | text | 2 | 1.000 | 0.817 | 1.000 | 1.000 | complete | - | 1.000 |
| 3 | Q1A | text | text | 3 | 1.000 | 0.817 | 1.000 | 1.000 | complete | - | 1.000 |
| 4 | Q1A | vision | vision | 1 | 1.000 | 0.852 | 1.000 | 1.000 | complete | - | 1.000 |
| 5 | Q1A | vision | vision | 2 | 1.000 | 0.852 | 1.000 | 1.000 | complete | - | 1.000 |
| 6 | Q1A | vision | text | 3 | N/A | N/A | N/A | N/A | error | vision_invoke_error | 0.000 |
| 7 | Q1B | text | text | 1 | 1.000 | 0.000 | 0.000 | 0.000 | complete | - | 0.000 |
| 8 | Q1B | text | text | 2 | 1.000 | 0.000 | 0.000 | 0.000 | complete | - | 0.000 |
| 9 | Q1B | text | text | 3 | 1.000 | 0.000 | 0.000 | 0.000 | complete | - | 0.000 |
| 10 | Q1B | vision | vision | 1 | 1.000 | 0.902 | 1.000 | 0.000 | complete | - | 1.000 |
| 11 | Q1B | vision | vision | 2 | 1.000 | 0.902 | 1.000 | 0.000 | complete | - | 1.000 |
| 12 | Q1B | vision | vision | 3 | 1.000 | 0.902 | 1.000 | 0.000 | complete | - | 1.000 |
| 13 | Q2A | text | text | 1 | 0.000 | 0.000 | 0.000 | 0.000 | complete | - | 0.000 |
| 14 | Q2A | text | text | 2 | 0.000 | 0.000 | 0.000 | 0.000 | complete | - | 0.000 |
| 15 | Q2A | text | text | 3 | N/A | N/A | N/A | N/A | error | - | 0.000 |
| 16 | Q2A | vision | text | 1 | 0.000 | 0.000 | 0.000 | 0.000 | complete | vision_not_found | 0.000 |
| 17 | Q2A | vision | text | 2 | 0.000 | N/A | 0.000 | 0.000 | complete | vision_not_found | 0.000 |
| 18 | Q2A | vision | text | 3 | 0.000 | 0.000 | 0.000 | 0.000 | complete | vision_not_found | 0.000 |
| 19 | Q2B | text | text | 1 | N/A | N/A | N/A | N/A | error | - | 0.000 |
| 20 | Q2B | text | text | 2 | 1.000 | -0.000 | 0.500 | 1.000 | complete | - | 0.000 |
| 21 | Q2B | text | text | 3 | 1.000 | -0.000 | N/A | 1.000 | complete | - | 0.000 |
| 22 | Q2B | vision | vision | 1 | 1.000 | 0.779 | 1.000 | 1.000 | complete | - | 1.000 |
| 23 | Q2B | vision | vision | 2 | 1.000 | 0.779 | 1.000 | 1.000 | complete | - | 1.000 |
| 24 | Q2B | vision | vision | 3 | 1.000 | 0.779 | 1.000 | 1.000 | complete | - | 1.000 |
| 25 | Q3A | text | text | 1 | 1.000 | -0.000 | 0.000 | 0.000 | complete | - | 0.167 |
| 26 | Q3A | text | text | 2 | 1.000 | -0.000 | 0.000 | 0.000 | complete | - | 0.167 |
| 27 | Q3A | text | text | 3 | 1.000 | -0.000 | 0.000 | 0.000 | complete | - | 0.167 |
| 28 | Q3A | vision | text | 1 | 1.000 | -0.000 | 0.000 | 0.000 | complete | vision_not_found | 0.167 |
| 29 | Q3A | vision | text | 2 | 1.000 | -0.000 | 0.000 | 0.000 | complete | vision_not_found | 0.167 |
| 30 | Q3A | vision | text | 3 | 1.000 | -0.000 | 0.000 | 0.000 | complete | vision_not_found | 0.167 |
| 31 | Q3B | text | text | 1 | 0.000 | -0.000 | N/A | N/A | complete | - | 0.167 |
| 32 | Q3B | text | text | 2 | 0.000 | -0.000 | N/A | N/A | complete | - | 0.167 |
| 33 | Q3B | text | text | 3 | 0.000 | -0.000 | N/A | N/A | complete | - | 0.167 |
| 34 | Q3B | vision | text | 1 | 0.000 | -0.000 | N/A | N/A | complete | vision_not_found | 0.167 |
| 35 | Q3B | vision | text | 2 | 0.000 | -0.000 | N/A | N/A | complete | vision_not_found | 0.167 |
| 36 | Q3B | vision | text | 3 | 0.000 | -0.000 | N/A | N/A | complete | vision_not_found | 0.167 |

## Answer Snapshots

- `#1 Q1A text rep1`: The weight for the **FX-485ADP** is approximately **0.3 kg (0.66 lbs)**.
- `#2 Q1A text rep2`: The weight for the **FX-485ADP** is approximately **0.3 kg (0.66 lbs)**.
- `#3 Q1A text rep3`: The weight for the **FX-485ADP** is approximately **0.3 kg (0.66 lbs)**.
- `#4 Q1A vision rep1`: According to the external dimensions diagram for the **FX-485ADP**, the weight of the unit is approximately **0.3 kg (0.66 lbs)**.
- `#5 Q1A vision rep2`: According to the external dimensions diagram for the **FX-485ADP**, the weight of the unit is approximately **0.3 kg (0.66 lbs)**.
- `#6 Q1A vision rep3`: \n[Error generating response: 429 You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To monitor yo...
- `#7 Q1B text rep1`: I couldn't find specific information about this.
- `#8 Q1B text rep2`: I couldn't find specific information about this.
- `#9 Q1B text rep3`: I couldn't find specific information about this.
- `#10 Q1B vision rep1`: The approximate mass of the **FX0N-485ADP** is **0.3 kg (0.66 lbs)**.
- `#11 Q1B vision rep2`: The approximate mass of the **FX0N-485ADP** is **0.3 kg (0.66 lbs)**.
- `#12 Q1B vision rep3`: The approximate mass of the **FX0N-485ADP** is **0.3 kg (0.66 lbs)**.
- `#13 Q2A text rep1`: I couldn't find specific information about this.
- `#14 Q2A text rep2`: I couldn't find specific information about this.
- `#15 Q2A text rep3`: \n[Error generating response: 429 You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To monitor yo...
- `#16 Q2A vision rep1`: I couldn't find specific information about this.
- `#17 Q2A vision rep2`: I couldn't find specific information about this.
- `#18 Q2A vision rep3`: I couldn't find specific information about this.
- `#19 Q2B text rep1`: \n[Error generating response: 429 You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. To monitor yo...
- `#20 Q2B text rep2`: I couldn't find specific information about this.
- `#21 Q2B text rep3`: I couldn't find specific information about this.
- `#22 Q2B vision rep1`: When using an **RS-422** circuit, the required value for the 1/4W terminating resistor is **330 Ω**.
- `#23 Q2B vision rep2`: When using an **RS-422** circuit, the required value for the 1/4W terminating resistor is **330 Ω**.
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

- `ragas_status=error` count: 3
- `ragas_status=pending` count: 0
- Manual-match score is a simple heuristic against expected answers.
