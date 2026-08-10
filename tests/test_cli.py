"""Command-line workflow tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml
from typer.testing import CliRunner

import api_test_pilot.cli as cli_module
from api_test_pilot.ai import AIAnalysisError
from api_test_pilot.cli import app
from api_test_pilot.models import (
    RunSummary,
    Scenario,
    ScenarioCategory,
    ScenarioResult,
)
from api_test_pilot.reporting import write_all

if TYPE_CHECKING:
    import pytest


def test_generate_command_writes_suite(
    tmp_path: Path,
    openapi_document: dict[str, Any],
) -> None:
    """The CLI should turn a local OpenAPI contract into a YAML suite."""
    spec = tmp_path / "openapi.yaml"
    output = tmp_path / "suite.yaml"
    spec.write_text(yaml.safe_dump(openapi_document), encoding="utf-8")

    result = CliRunner().invoke(
        app,
        [
            "generate",
            "--spec",
            str(spec),
            "--output",
            str(output),
            "--allow-method",
            "GET",
            "--allow-method",
            "POST",
        ],
    )

    assert result.exit_code == 0
    assert "Generated 6 scenarios" in result.stdout
    assert len(yaml.safe_load(output.read_text(encoding="utf-8"))["scenarios"]) == 6


def test_generate_with_missing_copilot_keeps_the_deterministic_suite(
    tmp_path: Path,
    openapi_document: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Optional AI advice must not turn successful deterministic generation into an error."""
    spec = tmp_path / "openapi.yaml"
    output = tmp_path / "suite.yaml"
    spec.write_text(yaml.safe_dump(openapi_document), encoding="utf-8")
    monkeypatch.setattr(cli_module.CopilotClient, "discover", classmethod(lambda _cls: None))

    result = CliRunner().invoke(
        app,
        ["generate", "--spec", str(spec), "--output", str(output), "--ai"],
    )

    assert result.exit_code == 0, result.output
    assert output.exists()
    assert "AI advice skipped: GitHub Copilot CLI is not installed." in result.output


def test_generate_with_failing_copilot_keeps_the_deterministic_suite(
    tmp_path: Path,
    openapi_document: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A Copilot provider error must be diagnostic-only after the suite is written."""
    spec = tmp_path / "openapi.yaml"
    output = tmp_path / "suite.yaml"
    spec.write_text(yaml.safe_dump(openapi_document), encoding="utf-8")

    class FailingCopilot:
        """Simulate a transient external Copilot service failure."""

        def generation_advice(self, _contract: dict[str, object]) -> str:
            """Raise the domain error returned by the optional provider adapter."""
            raise AIAnalysisError("Copilot service unavailable")

    monkeypatch.setattr(
        cli_module.CopilotClient,
        "discover",
        classmethod(lambda _cls: FailingCopilot()),
    )

    result = CliRunner().invoke(
        app,
        ["generate", "--spec", str(spec), "--output", str(output), "--ai"],
    )

    assert result.exit_code == 0, result.output
    assert output.exists()
    assert "AI advice skipped: Copilot service unavailable" in result.output


def test_analyze_command_updates_existing_reports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Failure analysis should be separable from untrusted regression execution."""
    scenario = Scenario(
        identifier="failed",
        name="Failed",
        category=ScenarioCategory.FUNCTIONAL,
        method="GET",
        path="/failed",
        expected_statuses=[200],
        description="Fails for testing.",
    )
    summary = RunSummary.from_results(
        started_at=datetime.now(UTC),
        base_url="https://api.example.test",
        results=[
            ScenarioResult(
                scenario=scenario,
                passed=False,
                status_code=500,
                duration_ms=1,
                error="boom",
            )
        ],
    )
    report = write_all(summary, tmp_path)["json"]

    class FakeCopilot:
        """Return deterministic analysis without invoking an external model."""

        def analyze_failures(self, _summary: RunSummary) -> str:
            """Return a fixture failure classification."""
            return "Likely implementation failure."

    monkeypatch.setattr(
        cli_module.CopilotClient,
        "discover",
        classmethod(lambda _cls: FakeCopilot()),
    )

    result = CliRunner().invoke(app, ["analyze", "--report", str(report)])

    assert result.exit_code == 0, result.output
    updated = json.loads(report.read_text(encoding="utf-8"))
    assert updated["ai_analysis"] == "Likely implementation failure."


def test_analyze_command_skips_successful_report(tmp_path: Path) -> None:
    """Copilot should not be invoked when the existing report has no failures."""
    summary = RunSummary.from_results(
        started_at=datetime.now(UTC),
        base_url="https://api.example.test",
        results=[],
    )
    report = write_all(summary, tmp_path)["json"]

    result = CliRunner().invoke(app, ["analyze", "--report", str(report)])

    assert result.exit_code == 0
    assert "No failed scenarios" in result.output


def test_analyze_command_records_copilot_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Optional AI errors should be retained in reports without hiding test results."""
    scenario = Scenario(
        identifier="failed",
        name="Failed",
        category=ScenarioCategory.FUNCTIONAL,
        method="GET",
        path="/failed",
        expected_statuses=[200],
        description="Fails for testing.",
    )
    summary = RunSummary.from_results(
        started_at=datetime.now(UTC),
        base_url="https://api.example.test",
        results=[
            ScenarioResult(
                scenario=scenario,
                passed=False,
                duration_ms=1,
                error="transport",
            )
        ],
    )
    report = write_all(summary, tmp_path)["json"]

    class FailingCopilot:
        """Raise a deterministic optional-provider error."""

        def analyze_failures(self, _summary: RunSummary) -> str:
            """Simulate a failed external Copilot request."""
            raise AIAnalysisError("Copilot unavailable")

    monkeypatch.setattr(
        cli_module.CopilotClient,
        "discover",
        classmethod(lambda _cls: FailingCopilot()),
    )

    result = CliRunner().invoke(app, ["analyze", "--report", str(report)])

    assert result.exit_code == 0
    assert json.loads(report.read_text(encoding="utf-8"))["ai_analysis"] == "Copilot unavailable"
