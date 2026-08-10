"""Command-line interface for project scaffolding, generation, and execution."""

from __future__ import annotations

import json
import os
import tempfile
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
)
from api_test_pilot.contracts import Contract, normalize_contract
from api_test_pilot.generation import generate_suite
from api_test_pilot.loaders import load_contract
from api_test_pilot.models import SAFE_HTTP_METHODS, ExecutionPolicy, RunSummary, ScenarioSuite
from api_test_pilot.notifications import notify_configured, settings_from_environment
from api_test_pilot.reporting import write_all
from api_test_pilot.runner import run_suite
from api_test_pilot.workflow import render_workflow

app = typer.Typer(no_args_is_help=True, help="Generate and run contract-driven API tests.")


def _write_suite(suite: ScenarioSuite, destination: Path) -> None:
    """Serialize a generated suite as readable YAML."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        yaml.safe_dump(suite.model_dump(mode="json"), sort_keys=False),
        encoding="utf-8",
    )


def _serialized_suite(suite: ScenarioSuite) -> str:
    """Return a generated suite as deterministic, readable YAML."""
    return yaml.safe_dump(suite.model_dump(mode="json"), sort_keys=False)


def _serialized_configuration(configuration: ProjectConfiguration) -> str:
    """Return project configuration as deterministic, readable YAML."""
    return yaml.safe_dump(configuration.model_dump(mode="json"), sort_keys=False)


def _stage_text(destination: Path, content: str) -> Path:
    """Write content to a same-directory temporary file for an atomic replacement."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=destination.parent,
        text=True,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return temporary


def _replace_file(source: Path, destination: Path) -> None:
    """Replace a destination with a staged file through the platform atomic primitive."""
    source.replace(destination)


def _restore_initialization_outputs(
    completed: list[Path], backups: dict[Path, Path]
) -> tuple[list[tuple[Path, Path | None, OSError]], set[Path]]:
    """Restore completed outputs, retaining a backup whenever restoring it fails."""
    rollback_errors: list[tuple[Path, Path | None, OSError]] = []
    preserved_recovery_backups: set[Path] = set()
    for destination in reversed(completed):
        backup = backups.get(destination)
        try:
            if backup is None:
                destination.unlink(missing_ok=True)
            else:
                _replace_file(backup, destination)
                backups.pop(destination)
        except OSError as rollback_error:  # Continue restoring every completed output.
            rollback_errors.append((destination, backup, rollback_error))
            if backup is not None:
                preserved_recovery_backups.add(backup)
    return rollback_errors, preserved_recovery_backups


def _rollback_error_details(rollback_errors: list[tuple[Path, Path | None, OSError]]) -> str:
    """Describe rollback failures, including usable recovery paths for retained backups."""
    return "; ".join(
        (
            "failed to restore overwritten destination "
            f"{destination.resolve(strict=False)} from preserved recovery backup "
            f"{backup.resolve(strict=False)}: {error}"
            if backup is not None
            else "failed to remove newly created destination "
            f"{destination.resolve(strict=False)}: {error}"
        )
        for destination, backup, error in rollback_errors
    )


def _write_initialization_outputs(outputs: dict[Path, str]) -> None:
    """Commit scaffold files together and restore prior outputs when a replacement fails."""
    staged: dict[Path, Path] = {}
    backups: dict[Path, Path] = {}
    completed: list[Path] = []
    preserved_recovery_backups: set[Path] = set()
    try:
        for destination, content in outputs.items():
            staged[destination] = _stage_text(destination, content)
        for destination in outputs:
            if destination.exists():
                backups[destination] = _stage_text(
                    destination,
                    destination.read_text(encoding="utf-8"),
                )
        for destination, temporary in staged.items():
            _replace_file(temporary, destination)
            completed.append(destination)
    except Exception as original_error:
        rollback_errors, preserved_recovery_backups = _restore_initialization_outputs(
            completed, backups
        )
        if rollback_errors:
            original_error.add_note(
                f"Scaffold rollback also encountered: {_rollback_error_details(rollback_errors)}"
            )
        raise
    finally:
        for temporary in [*staged.values(), *backups.values()]:
            if temporary not in preserved_recovery_backups:
                temporary.unlink(missing_ok=True)


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
        return
    try:
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
    except AIAnalysisError as exc:
        typer.echo(f"AI advice skipped: {exc}", err=True)
        return
    typer.echo(advice)


def _ensure_initialization_outputs_available(paths: list[Path], *, force: bool) -> None:
    """Preflight every scaffold destination so initialization is all-or-nothing."""
    resolved_paths = [path.resolve(strict=False) for path in paths]
    if len(set(resolved_paths)) != len(resolved_paths):
        raise typer.BadParameter("Configuration, suite, and workflow destinations must be distinct")
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
    _write_initialization_outputs(
        {
            config_path: _serialized_configuration(configuration),
            suite_path: _serialized_suite(suite),
            workflow_path: render_workflow(configuration, config_path=config_path),
        }
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
