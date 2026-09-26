"""FastAPI web app exposing the QA Test Design Agent over HTTP with a minimal
built-in UI (paste text, upload a document, or point at a Jira issue key).
"""
from __future__ import annotations

import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.export.excel_exporter import export_excel
from app.export.markdown_exporter import export_markdown
from app.export.traceability_exporter import export_deliverable_json, export_traceability_json
from app.ingestion.file_parser import UnsupportedFileTypeError, extract_text
from app.ingestion.jira_client import JiraNotConfiguredError, JiraRequestError, fetch_jira_context
from app.llm.llm_client import LLMNotConfiguredError
from app.pipeline.context import RequirementInput
from app.pipeline.orchestrator import run_pipeline

APP_DIR = Path(__file__).resolve().parent
OUTPUT_ROOT = Path("output") / "jobs"
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="AI QA Test Design Agent")
app.mount("/static", StaticFiles(directory=str(APP_DIR / "web" / "static")), name="static")


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    html_path = APP_DIR / "web" / "static" / "index.html"
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


@app.post("/api/generate")
async def generate(
    text: Optional[str] = Form(None),
    jira_key: Optional[str] = Form(None),
    title: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
):
    sources_provided = sum(bool(x) for x in (text, jira_key, file))
    if sources_provided == 0:
        raise HTTPException(400, "Provide requirement text, a Jira key, or upload a file.")
    if sources_provided > 1:
        raise HTTPException(400, "Provide only one of: text, jira_key, file.")

    try:
        if jira_key:
            ctx = fetch_jira_context(jira_key)
            requirement = RequirementInput(
                text=ctx.to_requirement_text(),
                source_type=f"Jira ({ctx.issue_type})",
                title=title or ctx.summary,
            )
        elif file:
            suffix = Path(file.filename or "upload.txt").suffix
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                shutil.copyfileobj(file.file, tmp)
                tmp_path = Path(tmp.name)
            try:
                extracted = extract_text(tmp_path)
            finally:
                tmp_path.unlink(missing_ok=True)
            requirement = RequirementInput(text=extracted, source_type=f"Document ({file.filename})", title=title)
        else:
            requirement = RequirementInput(text=text or "", source_type="Text", title=title)
    except UnsupportedFileTypeError as exc:
        raise HTTPException(400, str(exc)) from exc
    except JiraNotConfiguredError as exc:
        raise HTTPException(400, str(exc)) from exc
    except JiraRequestError as exc:
        raise HTTPException(502, str(exc)) from exc

    if not requirement.text.strip():
        raise HTTPException(400, "No usable requirement text was extracted.")

    try:
        deliverable = run_pipeline(requirement)
    except LLMNotConfiguredError as exc:
        raise HTTPException(400, str(exc)) from exc

    job_id = uuid.uuid4().hex[:12]
    job_dir = OUTPUT_ROOT / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "qa_report.md").write_text(export_markdown(deliverable), encoding="utf-8")
    (job_dir / "test_cases.xlsx").write_bytes(export_excel(deliverable))
    (job_dir / "deliverable.json").write_text(export_deliverable_json(deliverable), encoding="utf-8")
    (job_dir / "traceability.json").write_text(export_traceability_json(deliverable), encoding="utf-8")

    return JSONResponse(
        {
            "job_id": job_id,
            "title": deliverable.title,
            "executive_summary": deliverable.executive_summary,
            "counts": {
                "test_scenarios": len(deliverable.test_scenarios),
                "test_cases": len(deliverable.test_cases),
                "risks": len(deliverable.risks),
                "gaps": len(deliverable.gap_analysis.items),
                "open_questions": len(deliverable.questions_for_product_owner),
            },
            "report_markdown": export_markdown(deliverable),
            "downloads": {
                "report_md": f"/api/jobs/{job_id}/report.md",
                "test_cases_xlsx": f"/api/jobs/{job_id}/test_cases.xlsx",
                "deliverable_json": f"/api/jobs/{job_id}/deliverable.json",
                "traceability_json": f"/api/jobs/{job_id}/traceability.json",
            },
        }
    )


_FILE_MAP = {
    "report.md": "qa_report.md",
    "test_cases.xlsx": "test_cases.xlsx",
    "deliverable.json": "deliverable.json",
    "traceability.json": "traceability.json",
}


@app.get("/api/jobs/{job_id}/{artifact}")
def download(job_id: str, artifact: str):
    filename = _FILE_MAP.get(artifact)
    if not filename:
        raise HTTPException(404, "Unknown artifact.")
    path = OUTPUT_ROOT / job_id / filename
    if not path.exists():
        raise HTTPException(404, "Job or artifact not found.")
    return FileResponse(path, filename=filename)
