"""
Controlled manual evaluation runner.

This script:
1. Clears only embedding storage tables (`documents`, `pdf_pages`).
2. Re-embeds a curated set of technician-relevant pages from two manuals.
3. Runs A/B question variants in both text and vision mode.
4. Evaluates all RAGAS metrics using page-grounded reference answers.
5. Writes raw JSON results and a Markdown report for manual review.
"""

from __future__ import annotations

import json
import os
import statistics
import sys
import time
import argparse
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

# Force synchronous, full RAGAS before importing pipeline modules.
os.environ["EVAL_WITH_RAGAS"] = "true"
os.environ["ENABLE_BACKGROUND_RAGAS"] = "false"
os.environ["RAGAS_TIMEOUT"] = os.getenv("RAGAS_TIMEOUT", "240")
os.environ["RAGAS_MAX_WORKERS"] = "1"
os.environ["RAGAS_USE_GROUND_TRUTH_LOOKUP"] = "false"
os.environ["RAGAS_SOURCE_TEXT_MAX_PAGES"] = os.getenv("RAGAS_SOURCE_TEXT_MAX_PAGES", "3")
os.environ["RAGAS_SOURCE_TEXT_MAX_CHARS"] = os.getenv("RAGAS_SOURCE_TEXT_MAX_CHARS", "3200")

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

import fitz
import psycopg2

from app.db import init_db_pool
from app.embed_logic import get_embedder
from app.llm_factory import create_intent_llm, create_main_llm
from app.retriever import EnhancedFlashrankRerankRetriever, PostgresVectorRetriever
from app.chat.pipeline import answer_question
from embed import (
    PAGE_IMAGE_DPI,
    build_pdf_page_summary_chunk,
    create_summary_llm,
    ensure_storage_schema,
    flush_chunks,
    get_display_source_name,
    normalize_document_source,
)
from app.pdf_image_utils import _render_pdf_page_asset, store_page_images


COLLECTION = os.getenv("DEFAULT_COLLECTION", "plcnext")
BRAND = "Mitsubishi"
SUMMARY_MODEL = os.getenv("EMBED_SUMMARY_MODEL", "gemma3:4b")


@dataclass(frozen=True)
class ManualConfig:
    key: str
    pdf_path: str
    model_subbrand: str
    pages: list[int]


@dataclass(frozen=True)
class EvalCase:
    case_id: str
    manual_key: str
    target_pages: list[int]
    title: str
    ground_truth: str
    variant_a: str
    variant_b: str


MANUALS: list[ManualConfig] = [
    ManualConfig(
        key="fx5_hw",
        pdf_path="/app/data/Knowledge/MELSEC iQ-F FX5SFX5UJFX5UFX5UC User's Manual (Hardware).pdf",
        model_subbrand="MELSEC iQ-F FX5S/FX5UJ/FX5U/FX5UC User's Manual (Hardware)",
        pages=[47, 168, 200, 283],
    ),
    ManualConfig(
        key="iqr_c_app",
        pdf_path="/app/data/Knowledge/MELSEC iQ-R C Intelligent Function Module User's Manual (Application).pdf",
        model_subbrand="MELSEC iQ-R C Intelligent Function Module User's Manual (Application)",
        pages=[67, 70, 72, 76, 94],
    ),
]


CASES: list[EvalCase] = [
    EvalCase(
        case_id="fx5_p47_connectable_modules",
        manual_key="fx5_hw",
        target_pages=[47],
        title="FX5U connected extension-device limits",
        ground_truth=(
            "For the FX5U CPU module, the page shows a maximum of 6 expansion adapters, "
            "1 expansion board, and 16 extension modules. In the detailed breakdown on the page, "
            "analog adapters are limited to 4, communication adapters to 2, and the communication board to 1."
        ),
        variant_a="For Mitsubishi FX5U, how many extension modules can the CPU module connect?",
        variant_b="On the FX5U hardware manual, what's the max count of expansion adapters, expansion boards, and extension modules?",
    ),
    EvalCase(
        case_id="fx5_p168_din_rail_install",
        manual_key="fx5_hw",
        target_pages=[168],
        title="FX5 DIN rail installation method",
        ground_truth=(
            "To install the module on a 35 mm DIN46277 rail: 1. Push out all DIN rail mounting hooks. "
            "2. Fit the upper edge of the DIN rail mounting groove onto the DIN rail. "
            "3. Lock the DIN rail mounting hooks while pressing the module against the DIN rail."
        ),
        variant_a="How do I install an FX5 module on a DIN rail?",
        variant_b="What are the DIN rail mounting steps for the Mitsubishi FX5 hardware?",
    ),
    EvalCase(
        case_id="fx5_p200_sink_input_wiring",
        manual_key="fx5_hw",
        target_pages=[200],
        title="FX5U sink input wiring example",
        ground_truth=(
            "For the FX5U sink input example, the [S/S] terminal and [24V] terminal are short-circuited. "
            "The 24 VDC service power supply or an external power supply can be used for all inputs, "
            "but only one can be selected per CPU module or I/O module and they cannot be used together in the same module. "
            "The page also notes that a bleeder resistance may be required for a parallel resistance input device or two-wire proximity switch, "
            "and it shows a ground resistance of 100 ohms or less."
        ),
        variant_a="How is sink input wiring done on an FX5U AC power supply type?",
        variant_b="For Mitsubishi FX5U sink input wiring, which terminals should be shorted and what power-supply limitation applies?",
    ),
    EvalCase(
        case_id="fx5_p283_output_not_on",
        manual_key="fx5_hw",
        target_pages=[283],
        title="FX5 output does not turn on troubleshooting",
        ground_truth=(
            "When an output does not turn on, check for external wiring errors and connect the wiring properly. "
            "Stop the programmable controller and forcibly turn the inoperable output on or off with a peripheral or engineering tool. "
            "If the output operates, review the user program for duplicate coils or RST instructions. "
            "If the output still does not operate, check the configuration of connected devices and the extension-cable connections. "
            "If those are acceptable, the page says there may be a hardware issue."
        ),
        variant_a="On Mitsubishi FX5, what should I check if an output does not turn on?",
        variant_b="My FX5 output won't energize. What does the hardware manual tell me to inspect?",
    ),
    EvalCase(
        case_id="iqr_p67_module_status_screen",
        manual_key="iqr_c_app",
        target_pages=[67],
        title="iQ-R C module status and error-information screen",
        ground_truth=(
            "The module status is checked in the Module Diagnostics screen of the engineering tool. "
            "The Error Information tab shows the description of the current error and its corrective action, "
            "and the Event History button shows the history of detected errors and executed operations. "
            "The Module Information List displays the status information for the C intelligent function module."
        ),
        variant_a="Where do I check module status and current error details for a Mitsubishi iQ-R C intelligent function module?",
        variant_b="In the C intelligent function module application manual, which screen shows error information and module status?",
    ),
    EvalCase(
        case_id="iqr_p70_led_hardware_test",
        manual_key="iqr_c_app",
        target_pages=[70],
        title="iQ-R C hardware test for LED check",
        ground_truth=(
            "To run the hardware test for LED check: 1. In the engineering tool, select "
            "\"Hardware test for LED check\" in Basic Settings -> Various Operations Settings -> Mode Settings. "
            "2. Set the CPU module to STOP and write the parameters. 3. Reset the CPU module. "
            "During the test, RUN is green ON, ERR is red ON, CARD RDY is green ON, and USER is green ON. "
            "After a normal test, change the mode back to Online and reset the CPU module. "
            "If the test completes abnormally, reduce noise and run it again; repeated abnormal completion indicates possible hardware failure."
        ),
        variant_a="How do I run the hardware test for LED check on a C intelligent function module?",
        variant_b="What is the procedure for the LED hardware diagnostic in the Mitsubishi iQ-R C intelligent function module?",
    ),
    EvalCase(
        case_id="iqr_p72_ethernet_pc_connection",
        manual_key="iqr_c_app",
        target_pages=[72],
        title="iQ-R C Ethernet communication troubleshooting",
        ground_truth=(
            "When Ethernet communication cannot be established between the PC and the C intelligent function module, "
            "first issue a PING command from the PC and check the response. If it is incorrect, check the Ethernet cable, "
            "whether the PC and module are on the same IP segment, duplicate IP addresses, whether the IP address is in a valid range and format, "
            "network overload, IP filter blocking, and for an RD55UP12-V whether the channel is set to Use with IP address, subnet mask, and default gateway configured. "
            "If the PING response is normal, then troubleshoot the specific symptom such as CW Workbench settings, Telnet credentials or session limit, and FTP credentials or connection count."
        ),
        variant_a="Ethernet communication cannot be established between my PC and the C intelligent function module. What should I check first?",
        variant_b="On an RD55UP12-V, what settings and checks can stop Ethernet communication between a PC and the module?",
    ),
    EvalCase(
        case_id="iqr_p76_error_code_1807h",
        manual_key="iqr_c_app",
        target_pages=[76],
        title="iQ-R C error code 1807H",
        ground_truth=(
            "Error code 1807H is an IP Filter error. The page says the IP filter function is not working properly because the target IP address setting is duplicated. "
            "The corrective action is to set the target IP addresses so they do not overlap."
        ),
        variant_a="What does error code 1807H mean on the C intelligent function module, and what is the corrective action?",
        variant_b="In the iQ-R C intelligent function module error list, what is 1807H and how do I fix it?",
    ),
    EvalCase(
        case_id="iqr_p94_buffer_memory_status",
        manual_key="iqr_c_app",
        target_pages=[94],
        title="iQ-R C buffer memory addresses for LED and CH1 status",
        ground_truth=(
            "The module status area is Un\\G0 to Un\\G20. RUN LED status is at Un\\G0, ERR LED status at Un\\G1, "
            "CARD RDY LED status at Un\\G2, USER LED status at Un\\G3, and module operating status at Un\\G20. "
            "The CH1 network connection status area is Un\\G47 to Un\\G60. Within that area, the IP address string is Un\\G47 to Un\\G54, "
            "the IP address is Un\\G55 to Un\\G56, the subnet mask is Un\\G57 to Un\\G58, and the default gateway is Un\\G59 to Un\\G60. "
            "The common settings status area for Ethernet port CH1 is Un\\G70 to Un\\G76."
        ),
        variant_a="Which buffer memory addresses show the CH1 network connection status and LED status on the C intelligent function module?",
        variant_b="On RD55UP12-V, where can I read LED status and Ethernet port CH1 status in buffer memory?",
    ),
]


def _mean_metric(rows: list[dict[str, Any]], key: str) -> float | None:
    values = [row["ragas"].get(key) for row in rows if row["ragas"].get(key) is not None]
    if not values:
        return None
    return float(statistics.mean(values))


def _format_score(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:.3f} ({value * 100:.1f}%)"


def _source_id_for_manual(manual: ManualConfig) -> str:
    return normalize_document_source(manual.pdf_path)


def _manual_map() -> dict[str, ManualConfig]:
    return {manual.key: manual for manual in MANUALS}


def _clear_embedding_tables(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("TRUNCATE TABLE pdf_pages RESTART IDENTITY;")
        cur.execute("TRUNCATE TABLE documents RESTART IDENTITY;")
    conn.commit()


def _embed_selected_pages(conn, embedder, summary_llm, manual: ManualConfig) -> list[dict[str, Any]]:
    source_id = _source_id_for_manual(manual)
    display_source = get_display_source_name(source_id)
    embedded_pages: list[dict[str, Any]] = []

    with fitz.open(manual.pdf_path) as pdf_doc:
        for page_number in manual.pages:
            page_asset = _render_pdf_page_asset(pdf_doc[page_number - 1], page_number, PAGE_IMAGE_DPI)
            chunk = build_pdf_page_summary_chunk(
                summary_llm,
                page_asset,
                document_source=source_id,
                display_source=display_source,
                brand=BRAND,
                model_subbrand=manual.model_subbrand,
            )
            try:
                flush_chunks([chunk], embedder, conn, COLLECTION, commit=False)
                store_page_images(
                    conn,
                    [page_asset["image_data"]],
                    source_id,
                    COLLECTION,
                    brand=BRAND,
                    model_subbrand=manual.model_subbrand,
                    page_metadata=[chunk.metadata],
                    commit=False,
                )
                conn.commit()
                embedded_pages.append(
                    {
                        "page": page_number,
                        "chunk_type": chunk.metadata.get("chunk_type"),
                        "page_type_hint": chunk.metadata.get("page_type_hint"),
                        "content": chunk.page_content,
                    }
                )
            except Exception:
                conn.rollback()
                raise

    return embedded_pages


def _build_question_runs() -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    for case in CASES:
        for variant_name, question in (("A", case.variant_a), ("B", case.variant_b)):
            for mode in ("text", "vision"):
                runs.append(
                    {
                        "case_id": case.case_id,
                        "manual_key": case.manual_key,
                        "target_pages": case.target_pages,
                        "variant": variant_name,
                        "mode": mode,
                        "question": question,
                        "ground_truth": case.ground_truth,
                        "title": case.title,
                    }
                )
    return runs


def _expected_page_hit(source_details: list[dict[str, Any]], manual: ManualConfig, target_pages: list[int]) -> bool:
    source_id = _source_id_for_manual(manual)
    target_set = set(target_pages)
    for detail in source_details or []:
        if detail.get("source_id") == source_id and int(detail.get("page", 0) or 0) in target_set:
            return True
    return False


def _top_page(source_details: list[dict[str, Any]]) -> str:
    if not source_details:
        return "-"
    top = source_details[0]
    return f"{top.get('source', 'Unknown')} p{top.get('page', 'N/A')}"


def _run_evaluations(db_pool, llm, intent_llm, embedder) -> list[dict[str, Any]]:
    return _run_evaluations_with_retry(
        db_pool=db_pool,
        llm=llm,
        intent_llm=intent_llm,
        embedder=embedder,
        max_retries=0,
        retry_wait=0.0,
    )


def _should_retry_result(result: dict[str, Any]) -> bool:
    intent_source = str(result.get("intent_source") or "").strip().lower()
    if intent_source == "intent_llm_error":
        return True
    reply = str(result.get("reply") or "").lower()
    if "temporarily unavailable" in reply or "please retry" in reply:
        return True
    return False


def _run_evaluations_with_retry(db_pool, llm, intent_llm, embedder, *, max_retries: int, retry_wait: float) -> list[dict[str, Any]]:
    manual_lookup = _manual_map()
    results: list[dict[str, Any]] = []

    for run in _build_question_runs():
        manual = manual_lookup[run["manual_key"]]
        attempt = 0
        result: dict[str, Any] | None = None

        while True:
            started = time.perf_counter()
            result = answer_question(
                question=run["question"],
                db_pool=db_pool,
                llm=llm,
                intent_llm=intent_llm,
                embedder=embedder,
                collection=COLLECTION,
                retriever_class=PostgresVectorRetriever,
                reranker_class=EnhancedFlashrankRerankRetriever,
                chat_history=[],
                use_page_images_override=(run["mode"] == "vision"),
                ragas_ground_truth=run["ground_truth"],
            )
            elapsed = round(time.perf_counter() - started, 2)
            if attempt >= max_retries or not _should_retry_result(result):
                break
            attempt += 1
            time.sleep(max(retry_wait, 0.0))

        results.append(
            {
                **run,
                "elapsed_seconds": elapsed,
                "attempts": attempt + 1,
                "reply": result.get("reply", ""),
                "ragas": result.get("ragas", {}),
                "ragas_status": result.get("ragas_status"),
                "response_mode": result.get("response_mode"),
                "requested_mode": result.get("requested_mode"),
                "mode_fallback_reason": result.get("mode_fallback_reason"),
                "answer_support_status": result.get("answer_support_status"),
                "intent_query": result.get("intent_query"),
                "intent_source": result.get("intent_source"),
                "intent_details": result.get("intent_details", {}),
                "sources": result.get("sources", []),
                "source_details": result.get("source_details", []),
                "page_hit": _expected_page_hit(result.get("source_details", []), manual, run["target_pages"]),
                "top_page": _top_page(result.get("source_details", [])),
            }
        )
    return results


def _collect_issues(results: list[dict[str, Any]]) -> dict[str, list[str]]:
    issues: dict[str, list[str]] = {
        "mode_failures": [],
        "unsupported_answers": [],
        "missing_metrics": [],
        "retrieval_misses": [],
        "sketchy_metrics": [],
    }

    for row in results:
        label = f"{row['case_id']} {row['variant']} {row['mode']}"
        ragas = row.get("ragas", {}) or {}

        if row.get("response_mode") != row.get("requested_mode"):
            issues["mode_failures"].append(f"{label}: requested {row.get('requested_mode')} but got {row.get('response_mode')}")
        if row.get("answer_support_status") != "supported":
            issues["unsupported_answers"].append(f"{label}: support={row.get('answer_support_status')}")
        missing = [key for key in ("faithfulness", "answer_relevancy", "context_precision", "context_recall") if ragas.get(key) is None]
        if missing:
            issues["missing_metrics"].append(f"{label}: missing {', '.join(missing)}")
        if not row.get("page_hit"):
            issues["retrieval_misses"].append(f"{label}: top={row.get('top_page')}")
        if row.get("page_hit") is False and (ragas.get("answer_relevancy") or 0) >= 0.85:
            issues["sketchy_metrics"].append(f"{label}: high answer relevancy despite missing target page")
        if row.get("answer_support_status") != "supported" and (ragas.get("faithfulness") or 0) >= 0.75:
            issues["sketchy_metrics"].append(f"{label}: high faithfulness despite unsupported answer")
    return issues


def _write_outputs(output_dir: Path, embedded: dict[str, Any], results: list[dict[str, Any]], issues: dict[str, list[str]]) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_path = output_dir / "manual_eval_results.json"
    report_path = output_dir / "manual_eval_report.md"

    summary = {
        "collection": COLLECTION,
        "page_image_dpi": PAGE_IMAGE_DPI,
        "summary_model": SUMMARY_MODEL,
        "embedded": embedded,
        "cases": [asdict(case) for case in CASES],
        "results": results,
        "issues": issues,
    }
    raw_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    text_rows = [row for row in results if row["mode"] == "text"]
    vision_rows = [row for row in results if row["mode"] == "vision"]
    all_rows = results

    lines: list[str] = []
    lines.append("# Manual Evaluation Report")
    lines.append("")
    lines.append("## Workflow")
    lines.append("")
    lines.append("1. Clear only the embedding tables (`documents`, `pdf_pages`).")
    lines.append("2. Re-embed a curated set of technician-relevant pages from the two Mitsubishi manuals.")
    lines.append("3. Create page-grounded A/B test questions, one scenario per embedded page.")
    lines.append("4. Run each variant in both text and vision mode through the real intent + retrieval + answer pipeline.")
    lines.append("5. Evaluate all four RAGAS metrics with reference answers derived from the same embedded manual pages.")
    lines.append("")
    lines.append("## Embedded Pages")
    lines.append("")
    for manual in MANUALS:
        embedded_pages = embedded[manual.key]["pages"]
        lines.append(f"- `{manual.model_subbrand}`")
        lines.append(f"  - Source: `{manual.pdf_path}`")
        lines.append(f"  - Pages: {', '.join(str(p['page']) for p in embedded_pages)}")
    lines.append("")
    lines.append("## Aggregate Results")
    lines.append("")
    for label, rows in (("All runs", all_rows), ("Text mode", text_rows), ("Vision mode", vision_rows)):
        lines.append(f"### {label}")
        lines.append("")
        lines.append(f"- Runs: {len(rows)}")
        lines.append(f"- Target-page hit rate: {sum(1 for row in rows if row['page_hit'])}/{len(rows)}")
        lines.append(f"- Faithfulness: {_format_score(_mean_metric(rows, 'faithfulness'))}")
        lines.append(f"- Answer relevancy: {_format_score(_mean_metric(rows, 'answer_relevancy'))}")
        lines.append(f"- Context precision: {_format_score(_mean_metric(rows, 'context_precision'))}")
        lines.append(f"- Context recall: {_format_score(_mean_metric(rows, 'context_recall'))}")
        lines.append("")
    lines.append("## Per-run Results")
    lines.append("")
    lines.append("| Case | Variant | Mode | Target Hit | Top Page | Response Mode | Faithfulness | Answer Relevancy | Context Precision | Context Recall |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for row in results:
        ragas = row["ragas"]
        lines.append(
            "| "
            + " | ".join(
                [
                    row["case_id"],
                    row["variant"],
                    row["mode"],
                    "yes" if row["page_hit"] else "no",
                    row["top_page"].replace("|", "/"),
                    str(row.get("response_mode")),
                    _format_score(ragas.get("faithfulness")),
                    _format_score(ragas.get("answer_relevancy")),
                    _format_score(ragas.get("context_precision")),
                    _format_score(ragas.get("context_recall")),
                ]
            )
            + " |"
        )
    lines.append("")
    lines.append("## Findings")
    lines.append("")
    lines.append(f"- Vision mode strictness issues: {len(issues['mode_failures'])}")
    lines.append(f"- Unsupported/no-evidence answers: {len(issues['unsupported_answers'])}")
    lines.append(f"- Runs missing one or more RAGAS metrics: {len(issues['missing_metrics'])}")
    lines.append(f"- Retrieval misses against the intended source page: {len(issues['retrieval_misses'])}")
    lines.append(f"- Sketchy metric patterns flagged heuristically: {len(issues['sketchy_metrics'])}")
    lines.append("")
    if any(issues.values()):
        lines.append("### Issue Details")
        lines.append("")
        for label, entries in issues.items():
            if not entries:
                continue
            lines.append(f"- `{label}`")
            for entry in entries:
                lines.append(f"  - {entry}")
        lines.append("")
    lines.append("## Trustworthiness Notes")
    lines.append("")
    lines.append("- The evaluation uses reference answers written from the exact embedded manual pages, not external sources.")
    lines.append("- RAGAS contexts are taken from the exact source PDF page text when available, which is more trustworthy than OCR-only evaluation for these manuals.")
    lines.append("- Text-mode answers are still generated from stored retrieval notes, not full-page text, so high metrics do not guarantee perfect document-level completeness.")
    lines.append("- Vision-mode metrics remain dependent on how well the selected pages matched the intended page, even though the answer itself is generated from page images.")
    lines.append("")
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return raw_path, report_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the controlled manual evaluation.")
    parser.add_argument("--skip-embed", action="store_true", help="Reuse the current embedded pages instead of clearing and re-embedding.")
    parser.add_argument("--max-retries", type=int, default=2, help="Retries for transient intent/model failures during evaluation.")
    parser.add_argument("--retry-wait", type=float, default=3.0, help="Seconds to wait before retrying a transient evaluation failure.")
    args = parser.parse_args()

    run_id = time.strftime("%Y%m%d_%H%M%S")
    output_dir = Path("/app/eval_reports") / f"manual_eval_{run_id}"

    db_pool = init_db_pool()
    embedder = get_embedder()
    summary_llm = create_summary_llm(SUMMARY_MODEL)
    llm = create_main_llm(
        temperature=float(os.getenv("LLM_TEMPERATURE", "0.0")),
        timeout=int(os.getenv("LLM_TIMEOUT", "60")),
        max_tokens=int(os.getenv("LLM_NUM_PREDICT", "1024")),
    )
    intent_llm = create_intent_llm(
        temperature=float(os.getenv("INTENT_LLM_TEMPERATURE", "0.0")),
        timeout=int(os.getenv("INTENT_LLM_TIMEOUT", "30")),
        max_tokens=int(os.getenv("INTENT_LLM_NUM_PREDICT", "160")),
    )

    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    try:
        ensure_storage_schema(conn)
        embedded: dict[str, Any] = {}
        if args.skip_embed:
            for manual in MANUALS:
                embedded[manual.key] = {
                    "manual": manual.model_subbrand,
                    "source_id": _source_id_for_manual(manual),
                    "pages": [{"page": page} for page in manual.pages],
                }
        else:
            _clear_embedding_tables(conn)
            for manual in MANUALS:
                pages = _embed_selected_pages(conn, embedder, summary_llm, manual)
                embedded[manual.key] = {
                    "manual": manual.model_subbrand,
                    "source_id": _source_id_for_manual(manual),
                    "pages": pages,
                }

        results = _run_evaluations_with_retry(
            db_pool,
            llm,
            intent_llm,
            embedder,
            max_retries=max(args.max_retries, 0),
            retry_wait=max(args.retry_wait, 0.0),
        )
        issues = _collect_issues(results)
        raw_path, report_path = _write_outputs(output_dir, embedded, results, issues)

        print(json.dumps(
            {
                "status": "ok",
                "collection": COLLECTION,
                "embedded_pages": {
                    key: [page["page"] for page in value["pages"]]
                    for key, value in embedded.items()
                },
                "result_count": len(results),
                "raw_results": str(raw_path),
                "report": str(report_path),
                "issues": {key: len(value) for key, value in issues.items()},
            },
            indent=2,
        ))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
