"""Execution and report-generation tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx

from api_test_pilot.models import (
    ExecutionPolicy,
    ExpectedResponse,
    Scenario,
    ScenarioCategory,
    ScenarioSuite,
)
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


def test_runner_fails_on_response_schema_mismatch() -> None:
    """A successful status must not hide an invalid response body."""
    suite = ScenarioSuite(
        source="fixture",
        base_url="https://api.example.test",
        scenarios=[
            Scenario(
                identifier="schema",
                name="Schema",
                category=ScenarioCategory.FUNCTIONAL,
                method="GET",
                path="/schema",
                expected_statuses=[200],
                expected_responses=[
                    ExpectedResponse(
                        status_code=200,
                        media_type="application/json",
                        response_schema={
                            "type": "object",
                            "required": ["name"],
                            "properties": {"name": {"type": "string"}},
                        },
                    )
                ],
                description="Checks schema.",
            )
        ],
    )
    with httpx.Client(
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json={"name": 7}))
    ) as client:
        summary = run_suite(suite, client=client)

    assert summary.failed == 1
    assert "schema mismatch" in (summary.results[0].error or "")


def test_runner_blocks_method_outside_execution_policy() -> None:
    """Hand-edited suites should not bypass the generated method allowlist."""
    suite = ScenarioSuite(
        source="fixture",
        base_url="https://api.example.test",
        execution=ExecutionPolicy(allowed_methods=["GET"]),
        scenarios=[
            Scenario(
                identifier="delete",
                name="Delete",
                category=ScenarioCategory.FUNCTIONAL,
                method="DELETE",
                path="/items/1",
                expected_statuses=[204],
                description="Would delete data.",
            )
        ],
    )
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        """Record any unsafe transport invocation."""
        nonlocal calls
        calls += 1
        return httpx.Response(204)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        summary = run_suite(suite, client=client)

    assert calls == 0
    assert summary.failed == 1
    assert "blocks HTTP method DELETE" in (summary.results[0].error or "")
