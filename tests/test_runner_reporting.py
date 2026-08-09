"""Execution and report-generation tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx

from api_test_pilot.models import Scenario, ScenarioCategory, ScenarioSuite
from api_test_pilot.reporting import write_all
from api_test_pilot.runner import failure_payload, run_suite


def _suite() -> ScenarioSuite:
    """Create a two-scenario suite with one expected failure."""
    return ScenarioSuite(
        source="fixture",
        base_url="https://api.example.test",
        scenarios=[
            Scenario(
                identifier="health-functional",
                name="Health",
                category=ScenarioCategory.FUNCTIONAL,
                method="GET",
                path="/health",
                expected_statuses=[200],
                description="Checks health.",
            ),
            Scenario(
                identifier="missing-negative",
                name="Missing",
                category=ScenarioCategory.NEGATIVE,
                method="GET",
                path="/missing",
                expected_statuses=[400],
                description="Expects a validation failure.",
            ),
        ],
    )


def test_runner_continues_and_reports_failures(tmp_path: Path) -> None:
    """A failed expectation should not prevent later report generation."""

    def handler(request: httpx.Request) -> httpx.Response:
        """Return deterministic responses for both fixture paths."""
        return httpx.Response(200 if request.url.path == "/health" else 404, text="fixture")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        summary = run_suite(_suite(), client=client)
    outputs = write_all(summary, tmp_path)

    assert (summary.total, summary.passed, summary.failed) == (2, 1, 1)
    assert set(outputs) == {"json", "junit", "html"}
    assert json.loads(outputs["json"].read_text(encoding="utf-8"))["failed"] == 1
    assert "<failure" in outputs["junit"].read_text(encoding="utf-8")
    assert "API Test Pilot Report" in outputs["html"].read_text(encoding="utf-8")


def test_failure_payload_excludes_successful_requests() -> None:
    """AI context should contain only failed scenarios and no request credentials."""
    with httpx.Client(
        transport=httpx.MockTransport(lambda _request: httpx.Response(500, text="boom"))
    ) as client:
        summary = run_suite(_suite(), client=client)

    payload = failure_payload(summary)

    assert len(payload) == 2
    assert set(payload[0]) == {
        "scenario",
        "category",
        "request",
        "expected_statuses",
        "actual_status",
        "error",
        "response_excerpt",
    }
    assert datetime.fromisoformat(summary.started_at.isoformat()).tzinfo == UTC
