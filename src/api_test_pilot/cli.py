"""Command-line interface for scenario generation, execution, and notifications."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
import yaml

from api_test_pilot.ai import AIAnalysisError, GitHubModelsClient
from api_test_pilot.contracts import normalize_contract
from api_test_pilot.generation import generate_suite
from api_test_pilot.loaders import load_contract
from api_test_pilot.models import RunSummary, ScenarioSuite
from api_test_pilot.notifications import notify_configured, settings_from_environment
from api_test_pilot.reporting import write_all
from api_test_pilot.runner import run_suite

app = typer.Typer(no_args_is_help=True, help="Generate and run contract-driven API tests.")


def _write_suite(suite: ScenarioSuite, destination: Path) -> None:
    """Serialize a generated suite as readable YAML."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        yaml.safe_dump(suite.model_dump(mode="json"), sort_keys=False),
        encoding="utf-8",
    )


def _read_suite(source: Path) -> ScenarioSuite:
    """Load a generated YAML or JSON suite."""
    return ScenarioSuite.model_validate(yaml.safe_load(source.read_text(encoding="utf-8")))


@app.command()
def generate(
    spec: Annotated[str, typer.Option(help="OpenAPI/Postman path or HTTPS URL.")],
    output: Annotated[Path, typer.Option(help="Generated YAML scenario suite.")] = Path(
        "generated-scenarios.yaml"
    ),
    base_url: Annotated[str | None, typer.Option(help="Override the contract server URL.")] = None,
    ai: Annotated[bool, typer.Option(help="Print optional GitHub Models test advice.")] = False,
) -> None:
    """Generate deterministic functional, negative, and edge scenarios."""
    document = load_contract(spec)
    contract = normalize_contract(document)
    suite = generate_suite(contract, source=spec, base_url=base_url)
    _write_suite(suite, output)
    typer.echo(f"Generated {len(suite.scenarios)} scenarios in {output}")
    if ai:
        client = GitHubModelsClient.from_environment()
        if client is None:
            typer.echo("AI advice skipped: GITHUB_TOKEN is not configured.", err=True)
            raise typer.Exit(2)
        advice = client.generation_advice(
            {
                "format": contract.source_format,
                "base_url": suite.base_url,
                "operations": [
                    {"id": operation.identifier, "method": operation.method, "path": operation.path}
                    for operation in contract.operations
                ],
            }
        )
        typer.echo(advice)


@app.command()
def run(
    suite_path: Annotated[
        Path,
        typer.Option("--suite", help="Generated YAML or JSON scenario suite."),
    ] = Path("generated-scenarios.yaml"),
    report_dir: Annotated[Path, typer.Option(help="Directory for JSON/JUnit/HTML reports.")] = Path(
        "reports"
    ),
    ai_analysis: Annotated[
        bool,
        typer.Option(help="Ask GitHub Models to analyze failed scenarios."),
    ] = False,
) -> None:
    """Run a suite, write reports, and fail when any scenario fails."""
    summary = run_suite(_read_suite(suite_path))
    if ai_analysis and summary.failed:
        client = GitHubModelsClient.from_environment()
        if client is not None:
            try:
                summary.ai_analysis = client.analyze_failures(summary)
            except AIAnalysisError as exc:
                summary.ai_analysis = str(exc)
        else:
            summary.ai_analysis = "AI analysis skipped: GITHUB_TOKEN is not configured."
    outputs = write_all(summary, report_dir)
    typer.echo(
        f"Regression result: {summary.passed}/{summary.total} passed; reports: "
        f"{', '.join(str(path) for path in outputs.values())}"
    )
    if summary.failed:
        raise typer.Exit(1)


@app.command()
def notify(
    report: Annotated[Path, typer.Option(help="Canonical JSON report path.")] = Path(
        "reports/report.json"
    ),
) -> None:
    """Send Slack and/or email notifications for a completed report."""
    summary = RunSummary.model_validate(json.loads(report.read_text(encoding="utf-8")))
    channels = notify_configured(summary, settings_from_environment())
    typer.echo(f"Notified: {', '.join(channels) if channels else 'no configured channels'}")


if __name__ == "__main__":
    app()
