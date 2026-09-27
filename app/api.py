"""FastAPI web app exposing the QA Test Design Agent over HTTP with a minimal
built-in UI. Generation runs in a background thread per job so the browser can
watch live per-stage progress over Server-Sent Events (SSE) instead of
blocking on one long request.
"""
from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.export.excel_exporter import export_excel
from app.export.markdown_exporter import export_markdown
from app.export.traceability_exporter import export_deliverable_json, export_traceability_json
from app.ingestion.file_parser import UnsupportedFileTypeError, extract_text
from app.ingestion.jira_client import JiraNotConfiguredError, JiraRequestError, fetch_jira_hierarchy
from app.llm.llm_client import LLMNotConfiguredError
from app.models.schemas import QADeliverable
from app.pipeline.context import RequirementInput
from app.pipeline.orchestrator import run_pipeline

APP_DIR = Path(__file__).resolve().parent
OUTPUT_ROOT = Path("output") / "jobs"
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="AI QA Test Design Agent")
app.mount("/static", StaticFiles(directory=str(APP_DIR / "web" / "static")), name="static")


@dataclass
class Job:
    id: str
    status: str = "running"  # running | done | error
    messages: List[str] = field(default_factory=list)
    deliverable: Optional[QADeliverable] = None
    error: Optional[str] = None
    lock: threading.Lock = field(default_factory=threading.Lock)


JOBS: Dict[str, Job] = {}
_FILE_MAP = {
    "report.md": "qa_report.md",
    "test_cases.xlsx": "test_cases.xlsx",
    "deliverable.json": "deliverable.json",
    "traceability.json": "traceability.json",
}


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    html_path = APP_DIR / "web" / "static" / "index.html"
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


def _build_requirement(
    text: Optional[str], jira_key: Optional[str], title: Optional[str], file: Optional[UploadFile]
) -> RequirementInput:
    sources_provided = sum(bool(x) for x in (text, jira_key, file))
    if sources_provided == 0:
        raise HTTPException(400, "Provide requirement text, a Jira key, or upload a file.")
    if sources_provided > 1:
        raise HTTPException(400, "Provide only one of: text, jira_key, file.")

    try:
        if jira_key:
            hierarchy = fetch_jira_hierarchy(jira_key)
            return RequirementInput(
                text=hierarchy.to_requirement_text(),
                source_type=f"Jira ({hierarchy.primary.issue_type})",
                title=title or hierarchy.primary.summary,
                related_jira_keys=hierarchy.all_keys,
            )
        if file:
            suffix = Path(file.filename or "upload.txt").suffix
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                shutil.copyfileobj(file.file, tmp)
                tmp_path = Path(tmp.name)
            try:
                extracted = extract_text(tmp_path)
            finally:
                tmp_path.unlink(missing_ok=True)
            return RequirementInput(text=extracted, source_type=f"Document ({file.filename})", title=title)
        return RequirementInput(text=text or "", source_type="Text", title=title)
    except UnsupportedFileTypeError as exc:
        raise HTTPException(400, str(exc)) from exc
    except JiraNotConfiguredError as exc:
        raise HTTPException(400, str(exc)) from exc
    except JiraRequestError as exc:
        raise HTTPException(502, str(exc)) from exc


def _run_job(job: Job, requirement: RequirementInput) -> None:
    def on_stage(message: str) -> None:
        with job.lock:
            job.messages.append(message)

    try:
        deliverable = run_pipeline(requirement, on_stage=on_stage)
        job_dir = OUTPUT_ROOT / job.id
        job_dir.mkdir(parents=True, exist_ok=True)
        (job_dir / "qa_report.md").write_text(export_markdown(deliverable), encoding="utf-8")
        (job_dir / "test_cases.xlsx").write_bytes(export_excel(deliverable))
        (job_dir / "deliverable.json").write_text(export_deliverable_json(deliverable), encoding="utf-8")
        (job_dir / "traceability.json").write_text(export_traceability_json(deliverable), encoding="utf-8")
        with job.lock:
            job.deliverable = deliverable
            job.status = "done"
    except LLMNotConfiguredError as exc:
        with job.lock:
            job.error = str(exc)
            job.status = "error"
    except Exception as exc:  # noqa: BLE001 - surface any failure to the client instead of hanging
        with job.lock:
            job.error = f"{type(exc).__name__}: {exc}"
            job.status = "error"


@app.post("/api/generate/start")
async def start_generate(
    text: Optional[str] = Form(None),
    jira_key: Optional[str] = Form(None),
    title: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
):
    requirement = _build_requirement(text, jira_key, title, file)
    if not requirement.text.strip():
        raise HTTPException(400, "No usable requirement text was extracted.")

    job_id = uuid.uuid4().hex[:12]
    job = Job(id=job_id)
    JOBS[job_id] = job
    threading.Thread(target=_run_job, args=(job, requirement), daemon=True).start()
    return JSONResponse({"job_id": job_id})


def _job_summary(job: Job) -> dict:
    deliverable = job.deliverable
    assert deliverable is not None
    return {
        "job_id": job.id,
        "title": deliverable.title,
        "executive_summary": deliverable.executive_summary,
        "counts": {
            "test_scenarios": len(deliverable.test_scenarios),
            "test_cases": len(deliverable.test_cases),
            "risks": len(deliverable.risks),
            "gaps": len(deliverable.gap_analysis.items),
            "open_questions": len(deliverable.questions_for_product_owner),
            "duplicates_skipped": len(deliverable.duplicate_test_cases_skipped),
        },
        "report_markdown": export_markdown(deliverable),
        "downloads": {
            "report_md": f"/api/jobs/{job.id}/report.md",
            "test_cases_xlsx": f"/api/jobs/{job.id}/test_cases.xlsx",
            "deliverable_json": f"/api/jobs/{job.id}/deliverable.json",
            "traceability_json": f"/api/jobs/{job.id}/traceability.json",
        },
    }


@app.get("/api/jobs/{job_id}/events")
async def job_events(job_id: str):
    job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(404, "Unknown job.")

    async def event_stream():
        sent = 0
        while True:
            with job.lock:
                pending = job.messages[sent:]
                sent = len(job.messages)
                status = job.status
                error = job.error
            for message in pending:
                yield f"event: stage\ndata: {json.dumps({'message': message})}\n\n"
            if status == "done":
                yield f"event: done\ndata: {json.dumps(_job_summary(job))}\n\n"
                return
            if status == "error":
                yield f"event: error\ndata: {json.dumps({'detail': error})}\n\n"
                return
            await asyncio.sleep(0.3)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api/jobs/{job_id}/result")
def job_result(job_id: str):
    job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(404, "Unknown job.")
    if job.status == "running":
        raise HTTPException(409, "Job still running.")
    if job.status == "error":
        raise HTTPException(500, job.error or "Job failed.")
    return JSONResponse(_job_summary(job))


@app.get("/api/jobs/{job_id}/{artifact}")
def download(job_id: str, artifact: str):
    filename = _FILE_MAP.get(artifact)
    if not filename:
        raise HTTPException(404, "Unknown artifact.")
    path = OUTPUT_ROOT / job_id / filename
    if not path.exists():
        raise HTTPException(404, "Job or artifact not found.")
    return FileResponse(path, filename=filename)
