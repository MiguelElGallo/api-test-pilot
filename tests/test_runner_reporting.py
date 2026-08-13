"""Execution and report-generation tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from api_test_pilot.models import (
    AuthenticationKind,
    AuthenticationScheme,
    ExecutionPolicy,
    ExpectedResponse,
    Scenario,
    ScenarioCategory,
    ScenarioSuite,
)
from api_test_pilot.reporting import write_all
from api_test_pilot.runner import SuitePolicyError, failure_payload, run_suite


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
    """A suite must not authorize its own mutating method at runtime."""
    suite = ScenarioSuite(
        source="fixture",
        base_url="https://api.example.test",
        execution=ExecutionPolicy(allowed_methods=["DELETE"]),
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


def test_runner_accepts_mutating_method_only_from_independent_runtime_policy() -> None:
    """An explicit caller policy should preserve legitimate opted-in write tests."""
    suite = ScenarioSuite(
        source="fixture",
        base_url="https://api.example.test",
        execution=ExecutionPolicy(allowed_methods=["POST"]),
        scenarios=[
            Scenario(
                identifier="create",
                name="Create",
                category=ScenarioCategory.FUNCTIONAL,
                method="POST",
                path="/items",
                expected_statuses=[201],
                description="Creates test data.",
            )
        ],
    )
    with httpx.Client(
        transport=httpx.MockTransport(lambda _request: httpx.Response(201))
    ) as client:
        summary = run_suite(suite, client=client, runtime_allowed_methods={"POST"})

    assert summary.passed == 1


def test_runner_empty_runtime_policy_denies_all_methods() -> None:
    """An explicitly empty runtime policy must not fall back to safe methods."""
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        """Record any transport call after the policy should have blocked it."""
        nonlocal calls
        calls += 1
        return httpx.Response(200)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        summary = run_suite(_suite(), client=client, runtime_allowed_methods=[])

    assert calls == 0
    assert summary.failed == 2
    assert all("blocks HTTP method GET" in (result.error or "") for result in summary.results)


def test_runner_rejects_suite_selected_environment_secret_before_transport() -> None:
    """Suite data must not grant itself access to an arbitrary process variable."""
    suite = _suite().model_copy(
        update={
            "authentication": {
                "Token": AuthenticationScheme(
                    kind=AuthenticationKind.HTTP_BEARER,
                    environment_variable="GITHUB_TOKEN",
                )
            },
            "scenarios": [_suite().scenarios[0].model_copy(update={"security": [["Token"]]})],
        }
    )
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        """Record any transport call after the policy should have failed."""
        nonlocal calls
        calls += 1
        return httpx.Response(200)

    with (
        httpx.Client(transport=httpx.MockTransport(handler)) as client,
        pytest.raises(SuitePolicyError, match="authentication bindings"),
    ):
        run_suite(suite, client=client, environment={"GITHUB_TOKEN": "secret"})

    assert calls == 0


def test_runner_accepts_authentication_bound_to_trusted_config_and_origin() -> None:
    """Trusted configuration should preserve authenticated API regression."""
    suite = _suite().model_copy(
        update={
            "authentication": {
                "Token": AuthenticationScheme(
                    kind=AuthenticationKind.HTTP_BEARER,
                    environment_variable="API_TEST_AUTH_TOKEN",
                )
            },
            "scenarios": [_suite().scenarios[0].model_copy(update={"security": [["Token"]]})],
        }
    )

    def handler(request: httpx.Request) -> httpx.Response:
        """Confirm the trusted credential reaches only the configured origin."""
        assert request.url.host == "api.example.test"
        assert request.headers["Authorization"] == "Bearer secret"
        return httpx.Response(200)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        summary = run_suite(
            suite,
            client=client,
            environment={"API_TEST_AUTH_TOKEN": "secret"},
            trusted_authentication={"Token": "API_TEST_AUTH_TOKEN"},
            trusted_base_url="https://api.example.test",
        )

    assert summary.passed == 1


def test_runner_never_follows_scenario_redirects() -> None:
    """A redirect must not forward a custom API key to another origin."""
    suite = _suite().model_copy(
        update={
            "authentication": {
                "Token": AuthenticationScheme(
                    kind=AuthenticationKind.API_KEY,
                    environment_variable="API_TEST_AUTH_TOKEN",
                    location="header",
                    parameter_name="X-API-Key",
                )
            },
            "scenarios": [
                scenario.model_copy(update={"security": [["Token"]]})
                for scenario in _suite().scenarios
            ],
        }
    )
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        assert request.headers["X-API-Key"] == "secret"
        return httpx.Response(302, headers={"Location": "https://evil.example/collect"})

    with httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True) as client:
        summary = run_suite(
            suite,
            client=client,
            environment={"API_TEST_AUTH_TOKEN": "secret"},
            trusted_authentication={"Token": "API_TEST_AUTH_TOKEN"},
            trusted_base_url="https://api.example.test",
        )

    assert calls == ["https://api.example.test/health", "https://api.example.test/missing"]
    assert summary.failed == 2
