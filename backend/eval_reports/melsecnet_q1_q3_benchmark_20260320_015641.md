# MELSECNET/H Benchmark (Q1A-Q3B, Text vs Vision)

- Generated: 2026-03-20 01:56:41
- Benchmark user: `melsecnet_benchmark_20260320_015641@example.com`
- Total runs: 12
- Coverage: `Q1A`, `Q1B`, `Q2A`, `Q2B`, `Q3A`, `Q3B` in both `text` and `vision` modes

## Overall Results

| Mode | Runs | Exact Hits | Hit Rate | Faithfulness Avg | Answer Relevancy Avg | Answer Match Avg | Fallback Count | Response Modes |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| text | 6 | 0 | 0.0% | N/A | N/A | 0.068 | 0 | text |
| vision | 6 | 0 | 0.0% | N/A | N/A | 0.120 | 0 | vision |

## Per-Question Results

| QID | Mode | Expected | Exact Hits | Runs | Faithfulness Avg | Answer Relevancy Avg | Answer Match Avg | Response Modes |
|---|---|---|---:|---:|---:|---:|---:|---|
| Q1A | text | `QJ71LP21-25` | 0 | 1 | N/A | N/A | 0.036 | text |
| Q1A | vision | `QJ71LP21-25` | 0 | 1 | N/A | N/A | 0.022 | vision |
| Q1B | text | `QJ71LP21-25` | 0 | 1 | N/A | N/A | 0.022 | text |
| Q1B | vision | `QJ71LP21-25` | 0 | 1 | N/A | N/A | 0.301 | vision |
| Q2A | text | `QJ72LP25-25` | 0 | 1 | N/A | N/A | 0.320 | text |
| Q2A | vision | `QJ72LP25-25` | 0 | 1 | N/A | N/A | 0.047 | vision |
| Q2B | text | `QJ72LP25-25` | 0 | 1 | N/A | N/A | 0.006 | text |
| Q2B | vision | `QJ72LP25-25` | 0 | 1 | N/A | N/A | 0.142 | vision |
| Q3A | text | `QJ71BR11` | 0 | 1 | N/A | N/A | 0.012 | text |
| Q3A | vision | `QJ71BR11` | 0 | 1 | N/A | N/A | 0.197 | vision |
| Q3B | text | `QJ71BR11` | 0 | 1 | N/A | N/A | 0.010 | text |
| Q3B | vision | `QJ71BR11` | 0 | 1 | N/A | N/A | 0.009 | vision |

## Detailed Runs

| # | QID | Mode Req | Mode Resp | Exact Hit | Faith | Rel | Match | Fallback |
|---:|---|---|---|---|---:|---:|---:|---|
| 1 | Q1A | text | text | no | N/A | N/A | 0.036 | - |
| 2 | Q1A | vision | vision | no | N/A | N/A | 0.022 | - |
| 3 | Q1B | text | text | no | N/A | N/A | 0.022 | - |
| 4 | Q1B | vision | vision | no | N/A | N/A | 0.301 | - |
| 5 | Q2A | text | text | no | N/A | N/A | 0.320 | - |
| 6 | Q2A | vision | vision | no | N/A | N/A | 0.047 | - |
| 7 | Q2B | text | text | no | N/A | N/A | 0.006 | - |
| 8 | Q2B | vision | vision | no | N/A | N/A | 0.142 | - |
| 9 | Q3A | text | text | no | N/A | N/A | 0.012 | - |
| 10 | Q3A | vision | vision | no | N/A | N/A | 0.197 | - |
| 11 | Q3B | text | text | no | N/A | N/A | 0.010 | - |
| 12 | Q3B | vision | vision | no | N/A | N/A | 0.009 | - |

## Answers

- `#1 Q1A text` expected `QJ71LP21-25` -> The **MELSECNET/H** network module used in the exercise is part of the **Q-series** PLC models **10NS2** to **10NS5**.
- `#2 Q1A vision` expected `QJ71LP21-25` -> The model number of the **MELSECNET/H** network module used in the exercise is **SCHOOL-Q.NET10H-E** (Model Code: 13JW52).
- `#3 Q1B text` expected `QJ71LP21-25` -> Here’s a breakdown of the network module models presented in Chapter 3’s component setup demonstration machine system:  *   **Network No.1**     *   Model Name: **Q02H**     *   Station: 1     *   PLC: A *   **Network No.50**     *   Model Name: **Q02H**     *...
- `#4 Q1B vision` expected `QJ71LP21-25` -> The network module model shown in Chapter 3 component setup is **Q71LP21/Q71LP21/Q71LP25/Q71B** (or Q71B/Q71BR11).  This is based on information in Appendix 2.1, which lists the differences between network modules like Q71LP21/Q71LP21/Q71LP25/Q71B/Q71B/Q71BR11...
- `#5 Q2A text` expected `QJ72LP25-25` -> The **MELSECNET/H** remote I/O modules come in several models:  *   **QJ71LP21**, **QJ71LP21-25**, and **QJ71BR21** *   **QJ71QLP21**, **AJ71QLP21**, **A1SJ71QLP21** *   **QJ71BR11**, **AJ71QBR11**, **A1SJ71QBR11**  It’s important to note that the MELSECNET/10...
- `#6 Q2A vision` expected `QJ72LP25-25` -> The **Model/Subbrand** of the remote I/O module in MELSECNET/H is **Q71PLP21/Q71PLP21/Q71PLP21/Q71PLP21/Q71PLP21/Q71PLP21**  Supporting detail: The Q71PLP21/Q71PLP21 models are listed on page 2 and 3.
- `#7 Q2B text` expected `QJ72LP25-25` -> The **QCPU** is selected when a **PLC** is selected for the **MELSECNET/H** remote I/O network.  Remote I/O stations utilize the following:  *   **Capacity:**     *   Link relay (LB): 16384 points     *   Link register (LW): 16384 points     *   Input (LX): 81...
- `#8 Q2B vision` expected `QJ72LP25-25` -> The **Remote I/O station** is a module used as a remote I/O station.  Here’s supporting detail:  *   The Remote I/O station module is identified as **QJ72** and **QJ71**. *   It can be configured using the **GX Configurator** and automatic refresh settings. *...
- `#9 Q3A text` expected `QJ71BR11` -> The **MELSECNET/H** network system supports both the **MELSECNET/H mode** and the **MELSECNET/10 mode**.  When using the **MELSECNET/10 mode**, the coaxial bus type network module utilizes the following specifications:  *   **Transmission type:** Coaxial bus t...
- `#10 Q3A vision` expected `QJ71BR11` -> The **Q-series** coaxial bus type network module uses the **Q71LP21** model.
- `#11 Q3B text` expected `QJ71BR11` -> The **MELSECNET/H** network system supports both the **MELSECNET/H mode** and the **MELSECNET/10 mode**.  *   **Transmission Type:** Coaxial bus type / optical (SI) loop type *   **I/O (LX, LY):** 8,192 points *   **Link Relay (LB):** 16,383 points *   **Maxim...
- `#12 Q3B vision` expected `QJ71BR11` -> The **MELSECNET/H** module for coaxial communication is identified as a coaxial type/optical SI loop type. It has 16,384 points for the link relay (LB) and 8,192 points for the link register (LW). It supports a maximum of 1,320 bytes/frame. The communication s...
