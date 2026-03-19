# Manual Evaluation Report

## Workflow

1. Clear only the embedding tables (`documents`, `pdf_pages`).
2. Re-embed a curated set of technician-relevant pages from the two Mitsubishi manuals.
3. Create page-grounded A/B test questions, one scenario per embedded page.
4. Run each variant in both text and vision mode through the real intent + retrieval + answer pipeline.
5. Evaluate all four RAGAS metrics with reference answers derived from the same embedded manual pages.

## Embedded Pages

- `MELSEC iQ-F FX5S/FX5UJ/FX5U/FX5UC User's Manual (Hardware)`
  - Source: `/app/data/Knowledge/MELSEC iQ-F FX5SFX5UJFX5UFX5UC User's Manual (Hardware).pdf`
  - Pages: 47, 168, 200, 283
- `MELSEC iQ-R C Intelligent Function Module User's Manual (Application)`
  - Source: `/app/data/Knowledge/MELSEC iQ-R C Intelligent Function Module User's Manual (Application).pdf`
  - Pages: 67, 70, 72, 76, 94

## Aggregate Results

### All runs

- Runs: 36
- Target-page hit rate: 1/36
- Faithfulness: 0.667 (66.7%)
- Answer relevancy: 0.705 (70.5%)
- Context precision: 1.000 (100.0%)
- Context recall: N/A

### Text mode

- Runs: 18
- Target-page hit rate: 0/18
- Faithfulness: N/A
- Answer relevancy: N/A
- Context precision: N/A
- Context recall: N/A

### Vision mode

- Runs: 18
- Target-page hit rate: 1/18
- Faithfulness: 0.667 (66.7%)
- Answer relevancy: 0.705 (70.5%)
- Context precision: 1.000 (100.0%)
- Context recall: N/A

## Per-run Results

| Case | Variant | Mode | Target Hit | Top Page | Response Mode | Faithfulness | Answer Relevancy | Context Precision | Context Recall |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fx5_p47_connectable_modules | A | text | no | - | text | N/A | N/A | N/A | N/A |
| fx5_p47_connectable_modules | A | vision | no | - | text | N/A | N/A | N/A | N/A |
| fx5_p47_connectable_modules | B | text | no | - | text | N/A | N/A | N/A | N/A |
| fx5_p47_connectable_modules | B | vision | yes | MELSEC iQ-F FX5SFX5UJFX5UFX5UC User's Manual (Hardware).pdf p47 | vision | 0.667 (66.7%) | 0.705 (70.5%) | 1.000 (100.0%) | N/A |
| fx5_p168_din_rail_install | A | text | no | - | text | N/A | N/A | N/A | N/A |
| fx5_p168_din_rail_install | A | vision | no | - | text | N/A | N/A | N/A | N/A |
| fx5_p168_din_rail_install | B | text | no | - | text | N/A | N/A | N/A | N/A |
| fx5_p168_din_rail_install | B | vision | no | - | text | N/A | N/A | N/A | N/A |
| fx5_p200_sink_input_wiring | A | text | no | - | text | N/A | N/A | N/A | N/A |
| fx5_p200_sink_input_wiring | A | vision | no | - | text | N/A | N/A | N/A | N/A |
| fx5_p200_sink_input_wiring | B | text | no | - | text | N/A | N/A | N/A | N/A |
| fx5_p200_sink_input_wiring | B | vision | no | - | text | N/A | N/A | N/A | N/A |
| fx5_p283_output_not_on | A | text | no | - | text | N/A | N/A | N/A | N/A |
| fx5_p283_output_not_on | A | vision | no | - | text | N/A | N/A | N/A | N/A |
| fx5_p283_output_not_on | B | text | no | - | text | N/A | N/A | N/A | N/A |
| fx5_p283_output_not_on | B | vision | no | - | text | N/A | N/A | N/A | N/A |
| iqr_p67_module_status_screen | A | text | no | - | text | N/A | N/A | N/A | N/A |
| iqr_p67_module_status_screen | A | vision | no | - | text | N/A | N/A | N/A | N/A |
| iqr_p67_module_status_screen | B | text | no | - | text | N/A | N/A | N/A | N/A |
| iqr_p67_module_status_screen | B | vision | no | - | text | N/A | N/A | N/A | N/A |
| iqr_p70_led_hardware_test | A | text | no | - | text | N/A | N/A | N/A | N/A |
| iqr_p70_led_hardware_test | A | vision | no | - | text | N/A | N/A | N/A | N/A |
| iqr_p70_led_hardware_test | B | text | no | - | text | N/A | N/A | N/A | N/A |
| iqr_p70_led_hardware_test | B | vision | no | - | text | N/A | N/A | N/A | N/A |
| iqr_p72_ethernet_pc_connection | A | text | no | - | text | N/A | N/A | N/A | N/A |
| iqr_p72_ethernet_pc_connection | A | vision | no | - | text | N/A | N/A | N/A | N/A |
| iqr_p72_ethernet_pc_connection | B | text | no | - | text | N/A | N/A | N/A | N/A |
| iqr_p72_ethernet_pc_connection | B | vision | no | - | text | N/A | N/A | N/A | N/A |
| iqr_p76_error_code_1807h | A | text | no | - | text | N/A | N/A | N/A | N/A |
| iqr_p76_error_code_1807h | A | vision | no | - | text | N/A | N/A | N/A | N/A |
| iqr_p76_error_code_1807h | B | text | no | - | text | N/A | N/A | N/A | N/A |
| iqr_p76_error_code_1807h | B | vision | no | - | text | N/A | N/A | N/A | N/A |
| iqr_p94_buffer_memory_status | A | text | no | - | text | N/A | N/A | N/A | N/A |
| iqr_p94_buffer_memory_status | A | vision | no | - | text | N/A | N/A | N/A | N/A |
| iqr_p94_buffer_memory_status | B | text | no | - | text | N/A | N/A | N/A | N/A |
| iqr_p94_buffer_memory_status | B | vision | no | - | text | N/A | N/A | N/A | N/A |

## Findings

- Vision mode strictness issues: 0
- Unsupported/no-evidence answers: 35
- Runs missing one or more RAGAS metrics: 36
- Retrieval misses against the intended source page: 35
- Sketchy metric patterns flagged heuristically: 0

### Issue Details

- `unsupported_answers`
  - fx5_p47_connectable_modules A text: support=unsupported
  - fx5_p47_connectable_modules A vision: support=unsupported
  - fx5_p47_connectable_modules B text: support=unsupported
  - fx5_p168_din_rail_install A text: support=unsupported
  - fx5_p168_din_rail_install A vision: support=unsupported
  - fx5_p168_din_rail_install B text: support=unsupported
  - fx5_p168_din_rail_install B vision: support=unsupported
  - fx5_p200_sink_input_wiring A text: support=unsupported
  - fx5_p200_sink_input_wiring A vision: support=unsupported
  - fx5_p200_sink_input_wiring B text: support=unsupported
  - fx5_p200_sink_input_wiring B vision: support=unsupported
  - fx5_p283_output_not_on A text: support=unsupported
  - fx5_p283_output_not_on A vision: support=unsupported
  - fx5_p283_output_not_on B text: support=unsupported
  - fx5_p283_output_not_on B vision: support=unsupported
  - iqr_p67_module_status_screen A text: support=unsupported
  - iqr_p67_module_status_screen A vision: support=unsupported
  - iqr_p67_module_status_screen B text: support=unsupported
  - iqr_p67_module_status_screen B vision: support=unsupported
  - iqr_p70_led_hardware_test A text: support=unsupported
  - iqr_p70_led_hardware_test A vision: support=unsupported
  - iqr_p70_led_hardware_test B text: support=unsupported
  - iqr_p70_led_hardware_test B vision: support=unsupported
  - iqr_p72_ethernet_pc_connection A text: support=unsupported
  - iqr_p72_ethernet_pc_connection A vision: support=unsupported
  - iqr_p72_ethernet_pc_connection B text: support=unsupported
  - iqr_p72_ethernet_pc_connection B vision: support=unsupported
  - iqr_p76_error_code_1807h A text: support=unsupported
  - iqr_p76_error_code_1807h A vision: support=unsupported
  - iqr_p76_error_code_1807h B text: support=unsupported
  - iqr_p76_error_code_1807h B vision: support=unsupported
  - iqr_p94_buffer_memory_status A text: support=unsupported
  - iqr_p94_buffer_memory_status A vision: support=unsupported
  - iqr_p94_buffer_memory_status B text: support=unsupported
  - iqr_p94_buffer_memory_status B vision: support=unsupported
- `missing_metrics`
  - fx5_p47_connectable_modules A text: missing faithfulness, answer_relevancy, context_precision, context_recall
  - fx5_p47_connectable_modules A vision: missing faithfulness, answer_relevancy, context_precision, context_recall
  - fx5_p47_connectable_modules B text: missing faithfulness, answer_relevancy, context_precision, context_recall
  - fx5_p47_connectable_modules B vision: missing context_recall
  - fx5_p168_din_rail_install A text: missing faithfulness, answer_relevancy, context_precision, context_recall
  - fx5_p168_din_rail_install A vision: missing faithfulness, answer_relevancy, context_precision, context_recall
  - fx5_p168_din_rail_install B text: missing faithfulness, answer_relevancy, context_precision, context_recall
  - fx5_p168_din_rail_install B vision: missing faithfulness, answer_relevancy, context_precision, context_recall
  - fx5_p200_sink_input_wiring A text: missing faithfulness, answer_relevancy, context_precision, context_recall
  - fx5_p200_sink_input_wiring A vision: missing faithfulness, answer_relevancy, context_precision, context_recall
  - fx5_p200_sink_input_wiring B text: missing faithfulness, answer_relevancy, context_precision, context_recall
  - fx5_p200_sink_input_wiring B vision: missing faithfulness, answer_relevancy, context_precision, context_recall
  - fx5_p283_output_not_on A text: missing faithfulness, answer_relevancy, context_precision, context_recall
  - fx5_p283_output_not_on A vision: missing faithfulness, answer_relevancy, context_precision, context_recall
  - fx5_p283_output_not_on B text: missing faithfulness, answer_relevancy, context_precision, context_recall
  - fx5_p283_output_not_on B vision: missing faithfulness, answer_relevancy, context_precision, context_recall
  - iqr_p67_module_status_screen A text: missing faithfulness, answer_relevancy, context_precision, context_recall
  - iqr_p67_module_status_screen A vision: missing faithfulness, answer_relevancy, context_precision, context_recall
  - iqr_p67_module_status_screen B text: missing faithfulness, answer_relevancy, context_precision, context_recall
  - iqr_p67_module_status_screen B vision: missing faithfulness, answer_relevancy, context_precision, context_recall
  - iqr_p70_led_hardware_test A text: missing faithfulness, answer_relevancy, context_precision, context_recall
  - iqr_p70_led_hardware_test A vision: missing faithfulness, answer_relevancy, context_precision, context_recall
  - iqr_p70_led_hardware_test B text: missing faithfulness, answer_relevancy, context_precision, context_recall
  - iqr_p70_led_hardware_test B vision: missing faithfulness, answer_relevancy, context_precision, context_recall
  - iqr_p72_ethernet_pc_connection A text: missing faithfulness, answer_relevancy, context_precision, context_recall
  - iqr_p72_ethernet_pc_connection A vision: missing faithfulness, answer_relevancy, context_precision, context_recall
  - iqr_p72_ethernet_pc_connection B text: missing faithfulness, answer_relevancy, context_precision, context_recall
  - iqr_p72_ethernet_pc_connection B vision: missing faithfulness, answer_relevancy, context_precision, context_recall
  - iqr_p76_error_code_1807h A text: missing faithfulness, answer_relevancy, context_precision, context_recall
  - iqr_p76_error_code_1807h A vision: missing faithfulness, answer_relevancy, context_precision, context_recall
  - iqr_p76_error_code_1807h B text: missing faithfulness, answer_relevancy, context_precision, context_recall
  - iqr_p76_error_code_1807h B vision: missing faithfulness, answer_relevancy, context_precision, context_recall
  - iqr_p94_buffer_memory_status A text: missing faithfulness, answer_relevancy, context_precision, context_recall
  - iqr_p94_buffer_memory_status A vision: missing faithfulness, answer_relevancy, context_precision, context_recall
  - iqr_p94_buffer_memory_status B text: missing faithfulness, answer_relevancy, context_precision, context_recall
  - iqr_p94_buffer_memory_status B vision: missing faithfulness, answer_relevancy, context_precision, context_recall
- `retrieval_misses`
  - fx5_p47_connectable_modules A text: top=-
  - fx5_p47_connectable_modules A vision: top=-
  - fx5_p47_connectable_modules B text: top=-
  - fx5_p168_din_rail_install A text: top=-
  - fx5_p168_din_rail_install A vision: top=-
  - fx5_p168_din_rail_install B text: top=-
  - fx5_p168_din_rail_install B vision: top=-
  - fx5_p200_sink_input_wiring A text: top=-
  - fx5_p200_sink_input_wiring A vision: top=-
  - fx5_p200_sink_input_wiring B text: top=-
  - fx5_p200_sink_input_wiring B vision: top=-
  - fx5_p283_output_not_on A text: top=-
  - fx5_p283_output_not_on A vision: top=-
  - fx5_p283_output_not_on B text: top=-
  - fx5_p283_output_not_on B vision: top=-
  - iqr_p67_module_status_screen A text: top=-
  - iqr_p67_module_status_screen A vision: top=-
  - iqr_p67_module_status_screen B text: top=-
  - iqr_p67_module_status_screen B vision: top=-
  - iqr_p70_led_hardware_test A text: top=-
  - iqr_p70_led_hardware_test A vision: top=-
  - iqr_p70_led_hardware_test B text: top=-
  - iqr_p70_led_hardware_test B vision: top=-
  - iqr_p72_ethernet_pc_connection A text: top=-
  - iqr_p72_ethernet_pc_connection A vision: top=-
  - iqr_p72_ethernet_pc_connection B text: top=-
  - iqr_p72_ethernet_pc_connection B vision: top=-
  - iqr_p76_error_code_1807h A text: top=-
  - iqr_p76_error_code_1807h A vision: top=-
  - iqr_p76_error_code_1807h B text: top=-
  - iqr_p76_error_code_1807h B vision: top=-
  - iqr_p94_buffer_memory_status A text: top=-
  - iqr_p94_buffer_memory_status A vision: top=-
  - iqr_p94_buffer_memory_status B text: top=-
  - iqr_p94_buffer_memory_status B vision: top=-

## Trustworthiness Notes

- The evaluation uses reference answers written from the exact embedded manual pages, not external sources.
- RAGAS contexts are taken from the exact source PDF page text when available, which is more trustworthy than OCR-only evaluation for these manuals.
- Text-mode answers are still generated from stored retrieval notes, not full-page text, so high metrics do not guarantee perfect document-level completeness.
- Vision-mode metrics remain dependent on how well the selected pages matched the intended page, even though the answer itself is generated from page images.
