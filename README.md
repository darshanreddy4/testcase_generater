# AI QA Test Design Agent

An enterprise-grade **AI QA Test Architect** that turns any requirement — Jira issue,
BRD/FRD/PRD document, wireframe, or a plain sentence — into a full, production-quality
QA deliverable set: requirement analysis, impact/gap/risk analysis, test strategy,
test scenarios, detailed test cases, automation recommendations, test data
requirements, defect prevention notes, and a requirement → scenario → test case →
automation → defect traceability matrix.

It embodies a single persona (Senior QA Architect + Principal SDET + Business Analyst +
Test Strategist) across a **12-stage LLM pipeline**, with every stage validated against a
strict Pydantic schema so the output is structured data, not just prose.

**Enterprise-grade reliability features:**

- **Resumable pipeline** — every stage is checkpointed to disk keyed by a content-derived
  run ID. If a run is interrupted (network drop, crash, Ctrl-C), re-running the same
  requirement resumes from the last completed stage instead of starting over.
- **Parallel stage execution** — independent stages (e.g. feature classification, impact
  analysis, and gap analysis; or automation/test-data/defect-prevention/production-checklist)
  run concurrently, cutting wall-clock time.
- **Native structured outputs** — prefers the OpenAI SDK's built-in structured-output
  parsing for schema-guaranteed JSON, with automatic fallback to prompt+regex JSON
  extraction for providers/models that don't support it.
- **Net-new de-duplication** — generated test cases are compared against your existing
  test case suite and near-duplicates are dropped, so only genuinely new coverage is added.
- **Jira write-back** — optionally creates one Jira issue per generated test case,
  linked back to the source story/epic, closing the requirement → test case → Jira loop.
- **Jira hierarchy awareness** — given a task/story/bug key, walks up its full parent chain
  (task → story → epic → initiative) and pulls sibling issues under its immediate parent, so
  the agent understands the existing feature a new task fits into, not just the task in isolation.
- **Live progress** — the web UI streams per-stage progress over Server-Sent Events
  instead of one long blocking request.

## What it produces

Every run generates (as Markdown, Excel, and JSON):

- Executive Summary
- Requirement Understanding (business/user goals, functional/non-functional requirements,
  dependencies, integrations, constraints, assumptions)
- Feature Classification (New Feature / Enhancement / Bug Fix / UI / API / Workflow / Migration)
- Existing Feature Impact Analysis (matrix against Login, Registration, KYC, Fraud, Payments,
  Documents, Profile, Notifications, Reporting, Admin Portal + your own existing test cases/defects)
- Requirement Gap Analysis + Questions for Product Owner
- Risks (Business / Technical / Security / Production, each rated High/Medium/Low)
- Test Strategy (scope, approach, test design techniques applied, entry/exit criteria, tools)
- Test Scenarios & Detailed Test Cases (positive, negative, boundary, edge, security,
  accessibility, performance, regression, integration — never happy-path only)
- Automation Recommendations (Cypress / Playwright / Selenium / Postman / Rest Assured / Karate)
- Test Data Requirements
- Production Validation Checklist
- Defect Prevention Suggestions
- Traceability Matrix (Requirement → Scenario → Test Case → Automation Script → Defect →
  optionally a created Jira issue key)
- Duplicate test cases skipped (already covered by your existing suite)

## Architecture

```
app/
  config.py                  Settings loaded from .env
  llm/llm_client.py          OpenAI-compatible client: native structured outputs + JSON-schema
                             fallback, streaming, retries
  prompts/
    system_prompt.py         The QA Architect persona (single source of truth)
    stage_prompts.py         One prompt builder per pipeline stage
  models/schemas.py          Pydantic contract for every deliverable
  ingestion/
    file_parser.py           docx / pdf / xlsx / csv / txt / image(OCR) -> text
    jira_client.py           Jira Cloud REST v3: fetch story/epic/links/comments; write back
                             generated test cases as linked issues
  knowledge/existing_artifacts.py   Loads existing test cases/defects CSVs for impact & regression
  pipeline/
    orchestrator.py          Runs all 12 stages in dependency-ordered parallel waves,
                             assembles the final QADeliverable
    checkpoint.py            On-disk per-stage checkpointing for resumable runs
    dedup.py                 Net-new de-duplication against existing test cases
  export/
    markdown_exporter.py     Full report as Markdown
    excel_exporter.py        Multi-sheet Excel workbook (Zephyr/Xray/TestRail-friendly)
    traceability_exporter.py JSON exports
  cli.py                     Typer CLI (generate, config)
  api.py + web/static/       FastAPI app: SSE live-progress job endpoints + minimal browser UI
data/                        Sample existing test cases & defects CSVs
tests/                       Unit tests for every non-LLM component (parsers, schemas, exporters,
                              checkpointing, dedup, Jira ADF/write-back, SSE job API, and a fully
                              mocked pipeline wiring + resume test)
main.py                      CLI entrypoint
```

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt      # add -r requirements-dev.txt for running tests
cp .env.example .env
```

Edit `.env`:

- `OPENAI_API_KEY` / `OPENAI_BASE_URL` / `OPENAI_MODEL` — any OpenAI-compatible provider
  (OpenAI, Azure OpenAI via base URL, or a compatible gateway).
- `JIRA_BASE_URL` / `JIRA_EMAIL` / `JIRA_API_TOKEN` — optional, needed for `--jira` and Jira write-back.
- `JIRA_MAX_SIBLINGS` — cap on sibling issues (under the same parent/epic) to pull full
  detail for when building hierarchical context (default `20`; override per-run with
  `--jira-max-siblings`).
- `EXISTING_TEST_CASES_CSV` / `EXISTING_DEFECTS_CSV` — point these at your own exported test
  case / defect CSVs to get real impact & regression matching (samples provided in `data/`).
  Add an optional `jira_key` column to precisely correlate existing test cases to a
  story/epic — when the input is `--jira`, this takes priority over module-based matching.
- `USE_NATIVE_STRUCTURED_OUTPUTS` — default `true`; automatically falls back per-run if the
  model/provider doesn't support it.
- `CHECKPOINT_DIR` — where per-stage checkpoints are written (default `output/.checkpoints`).
- `DEDUP_SIMILARITY_THRESHOLD` — similarity ratio (0-1) above which a generated test case is
  treated as a duplicate of an existing one (default `0.88`).

## Usage

### CLI

```bash
# From free text
python main.py generate --text "Users should be able to upload a driver's license and complete identity verification."

# From a requirement document (docx/pdf/xlsx/txt/image)
python main.py generate --file requirements/PROJ-1234.docx

# From a Jira issue (story/epic/task/bug) — pulls description, acceptance criteria, linked issues, comments
python main.py generate --jira PROJ-1234

# Resume an interrupted run (auto-resumes by default if you re-run with the same input;
# --fresh forces a clean restart, ignoring any checkpoints)
python main.py generate --text "..." --fresh

# Write generated test cases back into Jira as linked issues under project QA, attached to PROJ-1234
python main.py generate --jira PROJ-1234 --jira-writeback-project QA --jira-writeback-parent PROJ-1234
```

Writes `qa_report.md`, `test_cases.xlsx`, `deliverable.json`, and `traceability.json` into
`./output` (override with `--output-dir`). Run `python main.py config` to check which
integrations (LLM, Jira) are currently configured.

### Web UI

```bash
uvicorn app.api:app --reload
```

Open http://127.0.0.1:8000 — paste text, upload a document, or enter a Jira key. Progress
streams live stage-by-stage over SSE; once done, download the report/Excel/JSON or read the
rendered report inline.

## Testing

```bash
pip install -r requirements-dev.txt
pytest -q
```

Tests cover file parsing, schema validation/round-tripping, the Markdown and Excel
exporters, existing-artifact CSV loading, Jira ADF-to-text flattening and write-back,
checkpointing/resume, net-new de-duplication, the SSE job API, and full pipeline wiring
(LLM calls mocked — no API key required to run the suite).

## Extending

- **New coverage categories / case types**: extend the enums in
  [app/models/schemas.py](app/models/schemas.py) and the corresponding prompt in
  [app/prompts/stage_prompts.py](app/prompts/stage_prompts.py).
- **Different test management export shape**: add a new function in
  [app/export/](app/export).
- **Live existing-test-case/defect source** (instead of CSV): replace
  [app/knowledge/existing_artifacts.py](app/knowledge/existing_artifacts.py) with calls to
  your test management / defect tracking API — the rest of the pipeline is unchanged.
# testcase_generater
