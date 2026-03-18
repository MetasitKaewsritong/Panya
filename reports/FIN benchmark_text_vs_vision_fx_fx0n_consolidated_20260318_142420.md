# Text vs Vision Benchmark (FX/FX0N-485ADP)

- Generated: 2026-03-18 14:24:20
- Benchmark user: `benchmark_20260318_142420@example.com`
- Total completed runs: 12
- Prefix used: `For FX/FX0N-485ADP manual: `
- RAGAS ground-truth mode: `injected_expected_answer`

## Ground Truth Used

- Weight (`Q1A`, `Q1B`): `Approximately 0.3 kg (0.66 lbs)`
- Resistance (`Q2A`, `Q2B`): `330 Ω`
- Device Symbols (`Q3A`, `Q3B`): `X, Y, M, S, T, and C`

## Overall Mode Comparison

| Mode | Runs | Faithfulness Avg | Answer Relevancy Avg | Context Precision Avg | Context Recall Avg | Manual Match Avg | Fallback Count | Faith N/A | Rel N/A | CP N/A | CR N/A |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| text | 6 | 0.767 | 0.551 | 0.542 | 0.833 | 0.667 | 0 | 0 | 0 | 0 | 0 |
| vision | 6 | 0.733 | 0.752 | 0.750 | 0.833 | 1.000 | 0 | 0 | 0 | 0 | 0 |

## Per-Question Averages (Text vs Vision)

| QID | Mode | Runs | Faithfulness Avg | Answer Relevancy Avg | Context Precision Avg | Context Recall Avg | Manual Match Avg | CP N/A | CR N/A |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Q1A | text | 1 | 1.000 | 0.817 | 1.000 | 1.000 | 1.000 | 0 | 0 |
| Q1A | vision | 1 | 1.000 | 0.852 | 1.000 | 1.000 | 1.000 | 0 | 0 |
| Q1B | text | 1 | 1.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0 | 0 |
| Q1B | vision | 1 | 1.000 | 0.902 | 1.000 | 1.000 | 1.000 | 0 | 0 |
| Q2A | text | 1 | 1.000 | 0.699 | 0.250 | 1.000 | 1.000 | 0 | 0 |
| Q2A | vision | 1 | 0.000 | 0.561 | 0.000 | 0.000 | 1.000 | 0 | 0 |
| Q2B | text | 1 | 1.000 | 0.000 | 0.500 | 1.000 | 0.000 | 0 | 0 |
| Q2B | vision | 1 | 1.000 | 0.779 | 1.000 | 1.000 | 1.000 | 0 | 0 |
| Q3A | text | 1 | 0.300 | 0.907 | 1.000 | 1.000 | 1.000 | 0 | 0 |
| Q3A | vision | 1 | 1.000 | 0.869 | 1.000 | 1.000 | 1.000 | 0 | 0 |
| Q3B | text | 1 | 0.300 | 0.884 | 0.500 | 1.000 | 1.000 | 0 | 0 |
| Q3B | vision | 1 | 0.400 | 0.551 | 0.500 | 1.000 | 1.000 | 0 | 0 |

## Detailed Runs

| # | QID | Mode Req | Mode Resp | Repeat | Faith | Rel | Ctx Prec | Ctx Rec | RAGAS Status | Fallback | Manual Match |
|---:|---|---|---|---:|---:|---:|---:|---:|---|---|---:|
| 1 | Q1A | text | text | 1 | 1.000 | 0.817 | 1.000 | 1.000 | complete | - | 1.000 |
| 2 | Q1A | vision | vision | 1 | 1.000 | 0.852 | 1.000 | 1.000 | complete | - | 1.000 |
| 3 | Q1B | text | text | 1 | 1.000 | 0.000 | 0.000 | 0.000 | complete | - | 0.000 |
| 4 | Q1B | vision | vision | 1 | 1.000 | 0.902 | 1.000 | 1.000 | complete | - | 1.000 |
| 5 | Q2A | text | text | 1 | 1.000 | 0.699 | 0.250 | 1.000 | complete | - | 1.000 |
| 6 | Q2A | vision | vision | 1 | 0.000 | 0.561 | 0.000 | 0.000 | complete | - | 1.000 |
| 7 | Q2B | text | text | 1 | 1.000 | -0.000 | 0.500 | 1.000 | complete | - | 0.000 |
| 8 | Q2B | vision | vision | 1 | 1.000 | 0.779 | 1.000 | 1.000 | complete | - | 1.000 |
| 9 | Q3A | text | text | 1 | 0.300 | 0.907 | 1.000 | 1.000 | complete | - | 1.000 |
| 10 | Q3A | vision | vision | 1 | 1.000 | 0.869 | 1.000 | 1.000 | complete | - | 1.000 |
| 11 | Q3B | text | text | 1 | 0.300 | 0.884 | 0.500 | 1.000 | complete | - | 1.000 |
| 12 | Q3B | vision | vision | 1 | 0.400 | 0.551 | 0.500 | 1.000 | complete | - | 1.000 |

## Answer Snapshots

- `#1 Q1A text rep1`: The weight for the **FX-485ADP** is approximately **0.3 kg (0.66 lbs)**.
- `#2 Q1A vision rep1`: According to the external dimensions diagram for the **FX-485ADP**, the weight of the unit is approximately **0.3 kg (0.66 lbs)**.
- `#3 Q1B text rep1`: I couldn't find specific information about this.
- `#4 Q1B vision rep1`: The approximate mass of the **FX0N-485ADP** is **0.3 kg (0.66 lbs)**.
- `#5 Q2A text rep1`: For the **two-pair wiring** (RS-422 circuit) configuration, the terminating resistance (**R**) that must be connected between terminals `SDA` and `SDB` is **330 Ω**.
- `#6 Q2A vision rep1`: According to the notes regarding two-pair wiring, the specific resistance value (R) for the terminating resistance is **330 Ω**. This must be connected between terminals `SDA` and `SDB`, as well as between terminals `RDA...
- `#7 Q2B text rep1`: I couldn't find specific information about this.
- `#8 Q2B vision rep1`: When using an **RS-422** circuit, the required value for the 1/4W terminating resistor is **330 Ω**.
- `#9 Q3A text rep1`: Hello, I am Panya. Regarding the **BR** (Bit Read) command for the **FX/FX0N-485ADP**, the objective device symbols are as follows:  • **Objective Device Symbols for BR Command**     - `X` (Input)     - `Y` (Output)...
- `#10 Q3A vision rep1`: According to the Computer Commands table, the objective device symbols listed for the **BR** (Bit Read) function are:  • **X, Y, M, S, T, C**
- `#11 Q3B text rep1`: Hello, I am Panya. Regarding the **BW** command for the **FX-485ADP** and **FX0N-485ADP** communication adapters, the specific devices that can be written in batch as one-point units are:  • **Bit Devices**     - `X` (In...
- `#12 Q3B vision rep1`: Based on the command table, the **BW** command is used to write on/off states into bit devices in batch in the unit of 1 point. The specific devices that can be written are:  • **Bit devices**     - `X` (Input relay)...

## Notes

- `ragas_status=error` count: 0
- `ragas_status=pending` count: 0
- runs with all 4 metrics present: 12/12
- Manual-match score is a simple heuristic against expected answers.
- For fairness, benchmark injects exact `expected_answer` as `ragas_ground_truth` on each request.
