"""Command-line interface for the AI QA Test Design Agent.

Examples:
    python main.py generate --text "Users should be able to upload a driver's license..."
    python main.py generate --file requirements/PROJ-1234.docx
    python main.py generate --jira PROJ-1234
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from app.export.excel_exporter import export_excel
from app.export.markdown_exporter import export_markdown
from app.export.traceability_exporter import export_deliverable_json, export_traceability_json
from app.ingestion.file_parser import extract_text
from app.ingestion.jira_client import fetch_jira_context
from app.pipeline.context import RequirementInput
from app.pipeline.orchestrator import run_pipeline
from app.config import settings

app = typer.Typer(help="AI QA Test Design Agent — enterprise test case generation.")
console = Console()


@app.command()
def config():
    """Show which integrations are currently configured."""
    console.print(f"LLM configured: {settings.llm_configured} (model: {settings.openai_model})")
    console.print(f"Jira configured: {settings.jira_configured}")


@app.command()
def generate(
    text: Optional[str] = typer.Option(None, help="Raw requirement text."),
    file: Optional[Path] = typer.Option(None, help="Path to a requirement document (docx/pdf/xlsx/txt/image)."),
    jira: Optional[str] = typer.Option(None, help="Jira issue key, e.g. PROJ-1234."),
    title: Optional[str] = typer.Option(None, help="Optional report title override."),
    output_dir: Path = typer.Option(Path("output"), help="Directory to write report artifacts into."),
):
    """Analyze a requirement and generate the full QA deliverable set."""
    sources_provided = sum(bool(x) for x in (text, file, jira))
    if sources_provided == 0:
        console.print("[red]Provide one of --text, --file, or --jira.[/red]")
        raise typer.Exit(code=1)
    if sources_provided > 1:
        console.print("[red]Provide only one of --text, --file, or --jira.[/red]")
        raise typer.Exit(code=1)

    if jira:
        console.print(f"[cyan]Fetching Jira issue {jira}...[/cyan]")
        ctx = fetch_jira_context(jira)
        requirement = RequirementInput(text=ctx.to_requirement_text(), source_type=f"Jira ({ctx.issue_type})", title=title or ctx.summary)
    elif file:
        console.print(f"[cyan]Extracting text from {file}...[/cyan]")
        requirement = RequirementInput(text=extract_text(file), source_type=f"Document ({file.name})", title=title)
    else:
        requirement = RequirementInput(text=text, source_type="Text", title=title)

    if not requirement.text or not requirement.text.strip():
        console.print("[red]No usable requirement text was extracted.[/red]")
        raise typer.Exit(code=1)

    output_dir.mkdir(parents=True, exist_ok=True)

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
        task = progress.add_task("Starting pipeline...", total=None)

        def on_stage(message: str) -> None:
            progress.update(task, description=message)

        deliverable = run_pipeline(requirement, on_stage=on_stage)

    report_path = output_dir / "qa_report.md"
    excel_path = output_dir / "test_cases.xlsx"
    json_path = output_dir / "deliverable.json"
    traceability_path = output_dir / "traceability.json"

    report_path.write_text(export_markdown(deliverable), encoding="utf-8")
    excel_path.write_bytes(export_excel(deliverable))
    json_path.write_text(export_deliverable_json(deliverable), encoding="utf-8")
    traceability_path.write_text(export_traceability_json(deliverable), encoding="utf-8")

    console.print(f"[green]Done.[/green] {len(deliverable.test_scenarios)} scenarios, {len(deliverable.test_cases)} test cases generated.")
    console.print(f"  Report:        {report_path}")
    console.print(f"  Excel:         {excel_path}")
    console.print(f"  JSON:          {json_path}")
    console.print(f"  Traceability:  {traceability_path}")


if __name__ == "__main__":
    app()
