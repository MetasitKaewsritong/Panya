# Manual Evaluation Analysis

## Scope

- Cleared only the embedding storage tables: `documents`, `pdf_pages`
- Re-embedded these technician-relevant pages:
  - `MELSEC iQ-F FX5S/FX5UJ/FX5U/FX5UC User's Manual (Hardware)`: pages `47`, `168`, `200`, `283`
  - `MELSEC iQ-R C Intelligent Function Module User's Manual (Application)`: pages `67`, `70`, `72`, `76`, `94`
- Built page-grounded A/B questions and ran both `text` and `vision` mode
- Evaluated with all four RAGAS metrics using ground-truth answers written from the embedded source pages

## Workflow

1. Clear `documents` and `pdf_pages`
2. Render and embed the curated PDF pages only
3. Store one page image per embedded page with matching metadata
4. Run the real intent -> retrieval -> answer pipeline
5. Evaluate answers with page-grounded RAGAS contexts

## Stored Data

The database is currently in the expected selective-eval state:

- `documents`: `9` rows
- `pdf_pages`: `9` rows

Embedded pages now present:

- `/app/data/Knowledge/MELSEC iQ-F FX5SFX5UJFX5UFX5UC User's Manual (Hardware).pdf`
  - `47`, `168`, `200`, `283`
- `/app/data/Knowledge/MELSEC iQ-R C Intelligent Function Module User's Manual (Application).pdf`
  - `67`, `70`, `72`, `76`, `94`

## Runs

Primary run:

- Raw: [manual_eval_results.json](/c:/67160005/Panya/backend/eval_reports/manual_eval_20260319_141225/manual_eval_results.json)
- Report: [manual_eval_report.md](/c:/67160005/Panya/backend/eval_reports/manual_eval_20260319_141225/manual_eval_report.md)

Retry run:

- Raw: [manual_eval_results.json](/c:/67160005/Panya/backend/eval_reports/manual_eval_20260319_142350/manual_eval_results.json)
- Report: [manual_eval_report.md](/c:/67160005/Panya/backend/eval_reports/manual_eval_20260319_142350/manual_eval_report.md)

## Headline Result

The end-to-end system is **not reliable enough yet for this evaluation target**.

The embedding stage worked.
The answer/evaluation stage did not.

What succeeded:

- selective re-embedding
- page-image storage
- page-grounded RAGAS context extraction
- a small number of FX5 text/vision answers

What failed:

- most intent extraction requests
- most iQ-R test cases never reached retrieval
- most vision requests never actually exercised the vision answer path
- most RAGAS rows never became complete because the upstream answer path failed first

## Coverage Reality

Primary run (`14:12:25`):

- total runs: `36`
- supported answers: `5`
- target-page hits: `5`
- complete 4-metric RAGAS rows: `2`
- intent extractor hard failures: `27`
- clarification replies: `4`

Retry run (`14:23:50`):

- total runs: `36`
- supported answers: `1`
- target-page hits: `1`
- complete 4-metric RAGAS rows: `0`
- intent extractor hard failures: `34`
- clarification replies: `1`

So the retry did **not** recover the matrix. It confirmed a persistent model-service problem rather than a one-off transient.

## What The Successful Rows Showed

Only a few FX5 rows completed far enough to inspect.

### FX5 page 47

Best case:

- `variant B / vision`
- retrieved the correct page
- answer was mostly correct:
  - `6` expansion adapters
  - `1` expansion board
  - `16` extension modules

But the other page-47 rows show quality problems:

- `variant A / text` answered incorrectly:
  - claimed `16 expansion boards`
  - claimed `12 connected expansion modules in total`
- `variant A / vision` contradicted itself:
  - said `16 extension modules`
  - also said `up to 6 extension modules`
- `variant B / text` was also wrong and mixed limits

So even when retrieval hit the intended page, answer quality was inconsistent.

### FX5 page 200

`variant A / text` completed, but the top selected page was `283`, not `200`.
The answer mixed sink-input wiring with troubleshooting-style language and was not cleanly grounded to the intended page.

That means:

- retrieval/reranking is not reliably preferring the intended page
- text mode is vulnerable because it answers from short retrieval notes, not the original page text

## iQ-R Manual Status

I do **not** consider the iQ-R manual evaluation validated yet.

In both the full matrix and follow-up spot checks, the iQ-R questions mostly failed before retrieval because the intent extractor could not reach `phi4-mini`.

So:

- the iQ-R pages were embedded correctly
- but the end-to-end ask/retrieve/answer path for that manual is still unproven

## RAGAS Trustworthiness

### What improved

I changed evaluation so RAGAS uses the exact PDF page text from the selected source pages when available, instead of relying only on OCR or the condensed retrieval note.

That is a real improvement and makes the metric context more defensible.

### What is still sketchy

The automatic aggregate metrics in the script reports are **not trustworthy on their own** for this run, because most rows never became valid supported answers.

Examples:

- page-47 text answers were factually wrong, but still got moderate answer-relevancy scores
- one vision row got `faithfulness = 1.0` and `answer_relevancy = 0.0`, which is not easy to interpret as a user-facing quality signal
- many rows show `N/A` because the answer path failed first or the evaluator timed out

My conclusion:

- the **RAGAS context source** is now better
- the **RAGAS numbers from this evaluation set** are still only partially trustworthy because the upstream system was unstable and several answers were low quality despite nonzero scores

## Bugs Found

1. Intent extraction is a hard single point of failure

- When `phi4-mini` fails, the whole pipeline short-circuits to:
  - `I don't understand the question, could you be more specific?`
- There is no robust fallback for transient intent-model outages

2. Host Ollama service became unhealthy

- `ollama.exe` kept a listener on `127.0.0.1:11434`
- but local HTTP requests and container requests both failed to connect
- even after restarting the process, the port still appeared to be listening while rejecting requests

3. Clarification is too aggressive for broad FX5 wording

- questions like `How do I install an FX5 module on a DIN rail?`
- were blocked with:
  - `Did you mean this version: MELSEC iQ-F FX5S/FX5UJ/FX5U/FX5UC User's Manual (Hardware)?`
- that is too strict for a manual that already clearly covers the FX5 family

4. Retrieval/reranking can select the wrong page even inside a tiny document set

- page-47 queries often pulled page `200` first
- page-200 query pulled page `283` first

5. Text mode is weak when retrieval notes are too compressed

- the answer generator uses selected chunk text, not the original manual page
- when the retrieval note is incomplete, the answer can drift or merge nearby concepts

6. Evaluation reporting hides blocked-before-mode failures

- intent-only failures currently come back as `response_mode = text`
- that makes many failed `vision` requests look like text runs instead of `vision never reached`

## Does The System Need To Be Fixed?

Yes.

At least these fixes are needed before I would trust the result:

1. Add an intent fallback path

- if `phi4-mini` is down, fall back to:
  - heuristic brand/model parsing
  - or direct normalized-question retrieval
- do not hard-stop the whole RAG flow on transient intent-model outages

2. Fix the Ollama host/service stability issue

- right now this is the main blocker
- until `127.0.0.1:11434` is healthy and reachable from both host and container, the evaluation will stay unreliable

3. Relax model clarification for family-level questions

- if the question says `FX5` and only one FX5-family manual is embedded, auto-resolve instead of asking for confirmation

4. Improve page ranking inside small scoped manuals

- boost exact target-page signals
- especially for tables, wiring pages, error-code pages, and procedure pages

5. Distinguish answer-generation evidence better

- text mode currently answers from retrieval notes only
- for higher trust, consider answering from original page text after retrieval, not only from the page-summary note

6. Make evaluation coverage explicit

- reports should show:
  - supported-answer count
  - intent-failure count
  - mode actually exercised count
- not just averages over the rows that happened to get scores

## Are Both Modes Working Properly?

Not end to end.

Text mode:

- partially exercised
- some supported answers were produced
- quality was inconsistent
- retrieval and answer grounding still need work

Vision mode:

- the vision path itself can produce an answer when it gets valid pages
- but in this evaluation it was exercised only a few times before the pipeline collapsed
- so I cannot say vision mode is working properly across the full workflow yet

## Final Verdict

The **embedding workflow is legitimate** for this selective technician-page setup.

The **full question-to-answer system is not yet legitimate enough** for a serious evaluation report, because:

- the intent stage is brittle
- the host LLM service became unhealthy
- page ranking is still inconsistent
- text-mode answers can be wrong even on correct retrieval
- the metric outputs are too sparse and unstable to treat as final quality evidence
