"""HTTP execution engine for generated API scenarios."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from time import perf_counter
from typing import Any

import httpx

from api_test_pilot.authentication import AuthenticationError, resolve_authentication
from api_test_pilot.models import (
    AuthenticationScheme,
    RunSummary,
    Scenario,
    ScenarioResult,
    ScenarioSuite,
)
from api_test_pilot.validation import validate_response


def _ensure_method_allowed(method: str, allowed_methods: set[str] | None) -> None:
    """Reject a request before transport when its method is outside the suite policy."""
    if allowed_methods is not None and method.upper() not in allowed_methods:
        raise AuthenticationError(f"Execution policy blocks HTTP method {method.upper()}")


def execute_scenario(
    client: httpx.Client,
    scenario: Scenario,
    *,
    base_url: str,
    authentication: Mapping[str, AuthenticationScheme] | None = None,
    environment: Mapping[str, str] | None = None,
    allowed_methods: set[str] | None = None,
) -> ScenarioResult:
    """Execute one scenario and capture transport failures without aborting the suite."""
    started = perf_counter()
    status_code: int | None = None
    excerpt: str | None = None
    error: str | None = None
    try:
        _ensure_method_allowed(scenario.method, allowed_methods)
        request_auth = resolve_authentication(
            scenario,
            authentication or {},
            environment=environment,
        )
        cookie_arguments = {"cookies": request_auth.cookies} if request_auth.cookies else {}
        response = client.request(
            scenario.method,
            f"{base_url.rstrip('/')}/{scenario.path.lstrip('/')}",
            headers=request_auth.headers,
            params=request_auth.query,
            json=scenario.body,
            **cookie_arguments,
        )
        status_code = response.status_code
        excerpt = response.text[:1_000]
        contract_failures = validate_response(response, scenario)
        passed = status_code in scenario.expected_statuses and not contract_failures
        if status_code not in scenario.expected_statuses:
            error = f"Expected {scenario.expected_statuses}, received {status_code}"
        elif contract_failures:
            error = "; ".join(contract_failures)
    except (httpx.HTTPError, AuthenticationError) as exc:
        passed = False
        error = f"{type(exc).__name__}: {exc}"
    return ScenarioResult(
        scenario=scenario,
        passed=passed,
        status_code=status_code,
        duration_ms=round((perf_counter() - started) * 1_000, 2),
        error=error,
        response_excerpt=excerpt,
    )


def run_suite(
    suite: ScenarioSuite,
    *,
    timeout: float = 15.0,
    client: httpx.Client | None = None,
    environment: Mapping[str, str] | None = None,
) -> RunSummary:
    """Execute all scenarios and return a summary suitable for machine reporting."""
    started_at = datetime.now(UTC)
    allowed_methods = set(suite.execution.allowed_methods)
    if client is not None:
        results = [
            execute_scenario(
                client,
                scenario,
                base_url=suite.base_url,
                authentication=suite.authentication,
                environment=environment,
                allowed_methods=allowed_methods,
            )
            for scenario in suite.scenarios
        ]
    else:
        with httpx.Client(timeout=timeout, follow_redirects=True) as owned_client:
            results = [
                execute_scenario(
                    owned_client,
                    scenario,
                    base_url=suite.base_url,
                    authentication=suite.authentication,
                    environment=environment,
                    allowed_methods=allowed_methods,
                )
                for scenario in suite.scenarios
            ]
    return RunSummary.from_results(
        started_at=started_at,
        base_url=suite.base_url,
        results=results,
    )


def failure_payload(summary: RunSummary) -> list[dict[str, Any]]:
    """Return a compact, redacted failure payload for AI analysis."""
    return [
        {
            "scenario": result.scenario.identifier,
            "category": result.scenario.category.value,
            "request": f"{result.scenario.method} {result.scenario.path}",
            "expected_statuses": result.scenario.expected_statuses,
            "actual_status": result.status_code,
            "error": result.error,
            "response_excerpt": result.response_excerpt,
        }
        for result in summary.results
        if not result.passed
    ]
