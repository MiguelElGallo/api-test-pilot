"""Command-line interface for project scaffolding, generation, and execution."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
import yaml

from api_test_pilot.ai import AIAnalysisError, CopilotClient
from api_test_pilot.configuration import (
    ArtifactConfiguration,
    ProjectConfiguration,
    TargetConfiguration,
    load_project_configuration,
    parse_variable_assignments,
    write_project_configuration,
)
from api_test_pilot.contracts import Contract, normalize_contract
from api_test_pilot.generation import generate_suite
from api_test_pilot.loaders import load_contract
from api_test_pilot.models import SAFE_HTTP_METHODS, ExecutionPolicy, RunSummary, ScenarioSuite
from api_test_pilot.notifications import notify_configured, settings_from_environment
from api_test_pilot.reporting import write_all
from api_test_pilot.runner import run_suite
from api_test_pilot.workflow import write_workflow

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


def _contract_from_target(target: TargetConfiguration) -> Contract:
    """Load and normalize the contract described by a project target."""
    document = load_contract(target.specification)
    variables = dict(target.variables)
    if target.base_url and "baseUrl" not in variables:
        variables["baseUrl"] = target.base_url
    return normalize_contract(document, variables=variables)


def _suite_from_configuration(
    configuration: ProjectConfiguration, *, contract: Contract | None = None
) -> ScenarioSuite:
    """Generate a suite using every policy and auth binding from project configuration."""
    selected_contract = contract or _contract_from_target(configuration.target)
    return generate_suite(
        selected_contract,
        source=configuration.target.specification,
        base_url=configuration.target.base_url,
        allowed_methods=configuration.execution.allowed_methods,
        authentication_environment=configuration.authentication,
    )


def _print_ai_advice(contract: Contract, suite: ScenarioSuite) -> None:
    """Print optional Copilot advice using only a secret-free contract summary."""
    client = CopilotClient.discover()
    if client is None:
        typer.echo("AI advice skipped: GitHub Copilot CLI is not installed.", err=True)
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


def _ensure_initialization_outputs_available(paths: list[Path], *, force: bool) -> None:
    """Preflight every scaffold destination so initialization is all-or-nothing."""
    existing = [path for path in paths if path.exists()]
    if existing and not force:
        joined = ", ".join(str(path) for path in existing)
        raise typer.BadParameter(f"Generated project files already exist: {joined}; use --force")


@app.command("init")
def initialize(  # noqa: PLR0917 - Typer exposes each project setting as an option.
    spec: Annotated[str, typer.Option(help="OpenAPI/Postman path or HTTPS URL.")],
    base_url: Annotated[str | None, typer.Option(help="Override the contract server URL.")] = None,
    allow_method: Annotated[
        list[str] | None,
        typer.Option("--allow-method", help="Allowed HTTP method; repeat to opt into mutations."),
    ] = None,
    variable: Annotated[
        list[str] | None,
        typer.Option("--variable", help="Non-secret Postman NAME=VALUE; repeat as needed."),
    ] = None,
    config_path: Annotated[
        Path, typer.Option("--config", help="Project configuration destination.")
    ] = Path(".api-test-pilot/config.yaml"),
    suite_path: Annotated[
        Path, typer.Option("--suite", help="Generated scenario suite destination.")
    ] = Path("generated-scenarios.yaml"),
    workflow_path: Annotated[
        Path, typer.Option("--workflow", help="Generated GitHub Actions workflow destination.")
    ] = Path(".github/workflows/api-regression.yml"),
    force: Annotated[bool, typer.Option(help="Replace existing generated project files.")] = False,
) -> None:
    """Initialize a generic local and GitHub Actions API regression project."""
    _ensure_initialization_outputs_available([config_path, suite_path, workflow_path], force=force)
    variables = parse_variable_assignments(variable or [])
    target = TargetConfiguration(specification=spec, base_url=base_url, variables=variables)
    provisional = ProjectConfiguration(
        target=target,
        execution=ExecutionPolicy(allowed_methods=allow_method or list(SAFE_HTTP_METHODS)),
        artifacts=ArtifactConfiguration(suite=str(suite_path), reports="reports"),
    )
    suite = _suite_from_configuration(provisional)
    configuration = provisional.model_copy(
        update={
            "authentication": {
                name: scheme.environment_variable for name, scheme in suite.authentication.items()
            }
        }
    )
    write_project_configuration(configuration, config_path, overwrite=True)
    _write_suite(suite, suite_path)
    write_workflow(
        configuration,
        workflow_path,
        config_path=config_path,
        overwrite=True,
    )
    typer.echo(
        f"Initialized {config_path}, {suite_path}, and {workflow_path} "
        f"with {len(suite.scenarios)} safe scenarios"
    )


@app.command()
def generate(  # noqa: PLR0917 - Typer exposes direct and configured generation options.
    spec: Annotated[str | None, typer.Option(help="OpenAPI/Postman path or HTTPS URL.")] = None,
    config_path: Annotated[
        Path | None, typer.Option("--config", help="Use a generated project configuration.")
    ] = None,
    output: Annotated[Path | None, typer.Option(help="Generated YAML scenario suite.")] = None,
    base_url: Annotated[str | None, typer.Option(help="Override the contract server URL.")] = None,
    allow_method: Annotated[
        list[str] | None,
        typer.Option("--allow-method", help="Allowed HTTP method; repeat to opt into mutations."),
    ] = None,
    variable: Annotated[
        list[str] | None,
        typer.Option("--variable", help="Non-secret Postman NAME=VALUE; repeat as needed."),
    ] = None,
    ai: Annotated[bool, typer.Option(help="Print optional GitHub Copilot test advice.")] = False,
) -> None:
    """Generate deterministic functional, negative, and edge scenarios."""
    if config_path is not None:
        if spec is not None or base_url is not None or allow_method or variable:
            raise typer.BadParameter("--config cannot be combined with target override options")
        configuration = load_project_configuration(config_path)
        contract = _contract_from_target(configuration.target)
        suite = _suite_from_configuration(configuration, contract=contract)
        destination = output or Path(configuration.artifacts.suite)
    else:
        if spec is None:
            raise typer.BadParameter("Provide --spec or --config")
        variables = parse_variable_assignments(variable or [])
        if base_url and "baseUrl" not in variables:
            variables["baseUrl"] = base_url
        document = load_contract(spec)
        contract = normalize_contract(document, variables=variables)
        suite = generate_suite(
            contract,
            source=spec,
            base_url=base_url,
            allowed_methods=allow_method,
        )
        destination = output or Path("generated-scenarios.yaml")
    _write_suite(suite, destination)
    typer.echo(f"Generated {len(suite.scenarios)} scenarios in {destination}")
    if ai:
        _print_ai_advice(contract, suite)


@app.command()
def run(
    suite_path: Annotated[
        Path | None,
        typer.Option("--suite", help="Generated YAML or JSON scenario suite."),
    ] = None,
    config_path: Annotated[
        Path | None, typer.Option("--config", help="Use a generated project configuration.")
    ] = None,
    report_dir: Annotated[
        Path | None, typer.Option(help="Directory for JSON/JUnit/HTML reports.")
    ] = None,
    ai_analysis: Annotated[
        bool,
        typer.Option(help="Ask GitHub Copilot CLI to analyze failed scenarios."),
    ] = False,
) -> None:
    """Run a suite, write reports, and fail when any scenario fails."""
    if config_path is not None:
        configuration = load_project_configuration(config_path)
        selected_suite = suite_path or Path(configuration.artifacts.suite)
        selected_reports = report_dir or Path(configuration.artifacts.reports)
    else:
        selected_suite = suite_path or Path("generated-scenarios.yaml")
        selected_reports = report_dir or Path("reports")
    summary = run_suite(_read_suite(selected_suite))
    if ai_analysis and summary.failed:
        client = CopilotClient.discover()
        if client is not None:
            try:
                summary.ai_analysis = client.analyze_failures(summary)
            except AIAnalysisError as exc:
                summary.ai_analysis = str(exc)
        else:
            summary.ai_analysis = "AI analysis skipped: GitHub Copilot CLI is not installed."
    outputs = write_all(summary, selected_reports)
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


@app.command()
def analyze(
    report: Annotated[Path, typer.Option(help="Canonical JSON report path.")] = Path(
        "reports/report.json"
    ),
) -> None:
    """Add GitHub Copilot failure analysis to an existing report set."""
    summary = RunSummary.model_validate(json.loads(report.read_text(encoding="utf-8")))
    if not summary.failed:
        typer.echo("No failed scenarios require AI analysis.")
        return
    client = CopilotClient.discover()
    if client is None:
        typer.echo("AI analysis skipped: GitHub Copilot CLI is not installed.", err=True)
        raise typer.Exit(2)
    try:
        summary.ai_analysis = client.analyze_failures(summary)
    except AIAnalysisError as exc:
        summary.ai_analysis = str(exc)
    write_all(summary, report.parent)
    typer.echo(f"Updated {report} with GitHub Copilot failure analysis")


if __name__ == "__main__":
    app()
