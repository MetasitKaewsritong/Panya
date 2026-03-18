# Text vs Vision Benchmark (FX/FX0N-485ADP)

- Generated: 2026-03-18 11:27:42
- Benchmark user: `benchmark_20260318_112742@example.com`
- Total completed runs: 36
- Prefix used: `For FX/FX0N-485ADP manual: `

## Ground Truth Used

- Weight (`Q1A`, `Q1B`): `Approximately 0.3 kg (0.66 lbs)`
- Resistance (`Q2A`, `Q2B`): `330 Ω`
- Device Symbols (`Q3A`, `Q3B`): `X, Y, M, S, T, and C`

## Overall Mode Comparison

| Mode | Runs | Faithfulness Avg | Answer Relevancy Avg | Context Precision Avg | Context Recall Avg | Manual Match Avg | Fallback Count | Faith N/A | Rel N/A | CP N/A | CR N/A |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| text | 18 | 0.767 | 0.551 | 1.000 | 1.000 | 0.667 | 0 | 0 | 0 | 15 | 15 |
| vision | 18 | 0.733 | 0.752 | 1.000 | 1.000 | 1.000 | 0 | 0 | 0 | 15 | 15 |

## Per-Question Averages (Text vs Vision)

| QID | Mode | Runs | Faithfulness Avg | Answer Relevancy Avg | Context Precision Avg | Context Recall Avg | Manual Match Avg | CP N/A | CR N/A |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Q1A | text | 3 | 1.000 | 0.817 | 1.000 | 1.000 | 1.000 | 0 | 0 |
| Q1A | vision | 3 | 1.000 | 0.852 | 1.000 | 1.000 | 1.000 | 0 | 0 |
| Q1B | text | 3 | 1.000 | 0.000 | N/A | N/A | 0.000 | 3 | 3 |
| Q1B | vision | 3 | 1.000 | 0.902 | N/A | N/A | 1.000 | 3 | 3 |
| Q2A | text | 3 | 1.000 | 0.699 | N/A | N/A | 1.000 | 3 | 3 |
| Q2A | vision | 3 | 0.000 | 0.561 | N/A | N/A | 1.000 | 3 | 3 |
| Q2B | text | 3 | 1.000 | 0.000 | N/A | N/A | 0.000 | 3 | 3 |
| Q2B | vision | 3 | 1.000 | 0.779 | N/A | N/A | 1.000 | 3 | 3 |
| Q3A | text | 3 | 0.300 | 0.907 | N/A | N/A | 1.000 | 3 | 3 |
| Q3A | vision | 3 | 1.000 | 0.869 | N/A | N/A | 1.000 | 3 | 3 |
| Q3B | text | 3 | 0.300 | 0.884 | N/A | N/A | 1.000 | 3 | 3 |
| Q3B | vision | 3 | 0.400 | 0.551 | N/A | N/A | 1.000 | 3 | 3 |

## Detailed Runs

| # | QID | Mode Req | Mode Resp | Repeat | Faith | Rel | Ctx Prec | Ctx Rec | RAGAS Status | Fallback | Manual Match |
|---:|---|---|---|---:|---:|---:|---:|---:|---|---|---:|
| 1 | Q1A | text | text | 1 | 1.000 | 0.817 | 1.000 | 1.000 | complete | - | 1.000 |
| 2 | Q1A | text | text | 2 | 1.000 | 0.817 | 1.000 | 1.000 | complete | - | 1.000 |
| 3 | Q1A | text | text | 3 | 1.000 | 0.817 | 1.000 | 1.000 | complete | - | 1.000 |
| 4 | Q1A | vision | vision | 1 | 1.000 | 0.852 | 1.000 | 1.000 | complete | - | 1.000 |
| 5 | Q1A | vision | vision | 2 | 1.000 | 0.852 | 1.000 | 1.000 | complete | - | 1.000 |
| 6 | Q1A | vision | vision | 3 | 1.000 | 0.852 | 1.000 | 1.000 | complete | - | 1.000 |
| 7 | Q1B | text | text | 1 | 1.000 | 0.000 | N/A | N/A | complete | - | 0.000 |
| 8 | Q1B | text | text | 2 | 1.000 | 0.000 | N/A | N/A | complete | - | 0.000 |
| 9 | Q1B | text | text | 3 | 1.000 | 0.000 | N/A | N/A | complete | - | 0.000 |
| 10 | Q1B | vision | vision | 1 | 1.000 | 0.902 | N/A | N/A | complete | - | 1.000 |
| 11 | Q1B | vision | vision | 2 | 1.000 | 0.902 | N/A | N/A | complete | - | 1.000 |
| 12 | Q1B | vision | vision | 3 | 1.000 | 0.902 | N/A | N/A | complete | - | 1.000 |
| 13 | Q2A | text | text | 1 | 1.000 | 0.699 | N/A | N/A | complete | - | 1.000 |
| 14 | Q2A | text | text | 2 | 1.000 | 0.699 | N/A | N/A | complete | - | 1.000 |
| 15 | Q2A | text | text | 3 | 1.000 | 0.699 | N/A | N/A | complete | - | 1.000 |
| 16 | Q2A | vision | vision | 1 | 0.000 | 0.561 | N/A | N/A | complete | - | 1.000 |
| 17 | Q2A | vision | vision | 2 | 0.000 | 0.561 | N/A | N/A | complete | - | 1.000 |
| 18 | Q2A | vision | vision | 3 | 0.000 | 0.561 | N/A | N/A | complete | - | 1.000 |
| 19 | Q2B | text | text | 1 | 1.000 | -0.000 | N/A | N/A | complete | - | 0.000 |
| 20 | Q2B | text | text | 2 | 1.000 | -0.000 | N/A | N/A | complete | - | 0.000 |
| 21 | Q2B | text | text | 3 | 1.000 | -0.000 | N/A | N/A | complete | - | 0.000 |
| 22 | Q2B | vision | vision | 1 | 1.000 | 0.779 | N/A | N/A | complete | - | 1.000 |
| 23 | Q2B | vision | vision | 2 | 1.000 | 0.779 | N/A | N/A | complete | - | 1.000 |
| 24 | Q2B | vision | vision | 3 | 1.000 | 0.779 | N/A | N/A | complete | - | 1.000 |
| 25 | Q3A | text | text | 1 | 0.300 | 0.907 | N/A | N/A | complete | - | 1.000 |
| 26 | Q3A | text | text | 2 | 0.300 | 0.907 | N/A | N/A | complete | - | 1.000 |
| 27 | Q3A | text | text | 3 | 0.300 | 0.907 | N/A | N/A | complete | - | 1.000 |
| 28 | Q3A | vision | vision | 1 | 1.000 | 0.869 | N/A | N/A | complete | - | 1.000 |
| 29 | Q3A | vision | vision | 2 | 1.000 | 0.869 | N/A | N/A | complete | - | 1.000 |
| 30 | Q3A | vision | vision | 3 | 1.000 | 0.869 | N/A | N/A | complete | - | 1.000 |
| 31 | Q3B | text | text | 1 | 0.300 | 0.884 | N/A | N/A | complete | - | 1.000 |
| 32 | Q3B | text | text | 2 | 0.300 | 0.884 | N/A | N/A | complete | - | 1.000 |
| 33 | Q3B | text | text | 3 | 0.300 | 0.884 | N/A | N/A | complete | - | 1.000 |
| 34 | Q3B | vision | vision | 1 | 0.400 | 0.551 | N/A | N/A | complete | - | 1.000 |
| 35 | Q3B | vision | vision | 2 | 0.400 | 0.551 | N/A | N/A | complete | - | 1.000 |
| 36 | Q3B | vision | vision | 3 | 0.400 | 0.551 | N/A | N/A | complete | - | 1.000 |

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
- `#14 Q2A text rep2`: For the **two-pair wiring** (RS-422 circuit) configuration, the terminating resistance (**R**) that must be connected between terminals `SDA` and `SDB` is **330 Ω**.
- `#15 Q2A text rep3`: For the **two-pair wiring** (RS-422 circuit) configuration, the terminating resistance (**R**) that must be connected between terminals `SDA` and `SDB` is **330 Ω**.
- `#16 Q2A vision rep1`: According to the notes regarding two-pair wiring, the specific resistance value (R) for the terminating resistance is **330 Ω**. This must be connected between terminals `SDA` and `SDB`, as well as between terminals `RDA...
- `#17 Q2A vision rep2`: According to the notes regarding two-pair wiring, the specific resistance value (R) for the terminating resistance is **330 Ω**. This must be connected between terminals `SDA` and `SDB`, as well as between terminals `RDA...
- `#18 Q2A vision rep3`: According to the notes regarding two-pair wiring, the specific resistance value (R) for the terminating resistance is **330 Ω**. This must be connected between terminals `SDA` and `SDB`, as well as between terminals `RDA...
- `#19 Q2B text rep1`: I couldn't find specific information about this.
- `#20 Q2B text rep2`: I couldn't find specific information about this.
- `#21 Q2B text rep3`: I couldn't find specific information about this.
- `#22 Q2B vision rep1`: When using an **RS-422** circuit, the required value for the 1/4W terminating resistor is **330 Ω**.
- `#23 Q2B vision rep2`: When using an **RS-422** circuit, the required value for the 1/4W terminating resistor is **330 Ω**.
- `#24 Q2B vision rep3`: When using an **RS-422** circuit, the required value for the 1/4W terminating resistor is **330 Ω**.
- `#25 Q3A text rep1`: Hello, I am Panya. Regarding the **BR** (Bit Read) command for the **FX/FX0N-485ADP**, the objective device symbols are as follows:  • **Objective Device Symbols for BR Command**     - `X` (Input)     - `Y` (Output)...
- `#26 Q3A text rep2`: Hello, I am Panya. Regarding the **BR** (Bit Read) command for the **FX/FX0N-485ADP**, the objective device symbols are as follows:  • **Objective Device Symbols for BR Command**     - `X` (Input)     - `Y` (Output)...
- `#27 Q3A text rep3`: Hello, I am Panya. Regarding the **BR** (Bit Read) command for the **FX/FX0N-485ADP**, the objective device symbols are as follows:  • **Objective Device Symbols for BR Command**     - `X` (Input)     - `Y` (Output)...
- `#28 Q3A vision rep1`: According to the Computer Commands table, the objective device symbols listed for the **BR** (Bit Read) function are:  • **X, Y, M, S, T, C**
- `#29 Q3A vision rep2`: According to the Computer Commands table, the objective device symbols listed for the **BR** (Bit Read) function are:  • **X, Y, M, S, T, C**
- `#30 Q3A vision rep3`: According to the Computer Commands table, the objective device symbols listed for the **BR** (Bit Read) function are:  • **X, Y, M, S, T, C**
- `#31 Q3B text rep1`: Hello, I am Panya. Regarding the **BW** command for the **FX-485ADP** and **FX0N-485ADP** communication adapters, the specific devices that can be written in batch as one-point units are:  • **Bit Devices**     - `X` (In...
- `#32 Q3B text rep2`: Hello, I am Panya. Regarding the **BW** command for the **FX-485ADP** and **FX0N-485ADP** communication adapters, the specific devices that can be written in batch as one-point units are:  • **Bit Devices**     - `X` (In...
- `#33 Q3B text rep3`: Hello, I am Panya. Regarding the **BW** command for the **FX-485ADP** and **FX0N-485ADP** communication adapters, the specific devices that can be written in batch as one-point units are:  • **Bit Devices**     - `X` (In...
- `#34 Q3B vision rep1`: Based on the command table, the **BW** command is used to write on/off states into bit devices in batch in the unit of 1 point. The specific devices that can be written are:  • **Bit devices**     - `X` (Input relay)...
- `#35 Q3B vision rep2`: Based on the command table, the **BW** command is used to write on/off states into bit devices in batch in the unit of 1 point. The specific devices that can be written are:  • **Bit devices**     - `X` (Input relay)...
- `#36 Q3B vision rep3`: Based on the command table, the **BW** command is used to write on/off states into bit devices in batch in the unit of 1 point. The specific devices that can be written are:  • **Bit devices**     - `X` (Input relay)...

## Notes

- `ragas_status=error` count: 0
- `ragas_status=pending` count: 0
- Manual-match score is a simple heuristic against expected answers.
