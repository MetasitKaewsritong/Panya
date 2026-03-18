# FIN Text vs Vision Summary (Single-Pass 12 Runs)

- Source report: reports/benchmark_text_vs_vision_fx_fx0n_consolidated_20260318_142420.json
- Generated at: 2026-03-18T07:34:10.712286+00:00
- Benchmark user: benchmark_20260318_142420@example.com
- Total runs: 12 (Q1A/Q1B/Q2A/Q2B/Q3A/Q3B x Text+Vision, no repeats)

## Reliability Check

- Missing metric runs: **0**
- Fallback runs: **0**
- Non-complete RAGAS runs: **0**
- Reliability verdict: **GOOD** (all runs complete with 4 metrics)

## Overall Mode Comparison

| Mode | Faithfulness | Answer Relevancy | Context Precision | Context Recall | Manual Match | Verdict |
|---|---:|---:|---:|---:|---:|---|
| Text | 0.7666666666666666 | 0.5510486459588081 | 0.5416666666125 | 0.8333333333333334 | 0.6666666666666666 | MIXED |
| Vision | 0.7333333333333334 | 0.7522668839346438 | 0.7499999999333333 | 0.8333333333333334 | 1.0 | GOOD |

## Quick Interpretation

- **Vision mode** is stronger overall in this run (higher relevancy and perfect manual-match).
- **Text mode** is stable/reliable but answer quality is mixed on some command-table questions.
- This run is valid for comparison because both modes completed with no missing metrics/fallbacks/errors.

## Notes

- Benchmark order used: 
  `Q1A text -> Q1A vision -> Q1B text -> Q1B vision -> ... -> Q3B text -> Q3B vision`
- Ground truth mode: `injected_expected_answer`
