"""HTTP execution engine for generated API scenarios."""

from __future__ import annotations

from datetime import UTC, datetime
from time import perf_counter
from typing import Any

import httpx

from api_test_pilot.models import RunSummary, Scenario, ScenarioResult, ScenarioSuite


def execute_scenario(
    client: httpx.Client,
    scenario: Scenario,
    *,
    base_url: str,
) -> ScenarioResult:
    """Execute one scenario and capture transport failures without aborting the suite."""
    started = perf_counter()
    status_code: int | None = None
    excerpt: str | None = None
    error: str | None = None
    try:
        response = client.request(
            scenario.method,
            f"{base_url.rstrip('/')}/{scenario.path.lstrip('/')}",
            headers=scenario.headers,
            params=scenario.query,
            json=scenario.body,
        )
        status_code = response.status_code
        excerpt = response.text[:1_000]
        passed = status_code in scenario.expected_statuses
        if not passed:
            error = f"Expected {scenario.expected_statuses}, received {status_code}"
    except httpx.HTTPError as exc:
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
) -> RunSummary:
    """Execute all scenarios and return a summary suitable for machine reporting."""
    started_at = datetime.now(UTC)
    if client is not None:
        results = [
            execute_scenario(client, scenario, base_url=suite.base_url)
            for scenario in suite.scenarios
        ]
    else:
        with httpx.Client(timeout=timeout, follow_redirects=True) as owned_client:
            results = [
                execute_scenario(owned_client, scenario, base_url=suite.base_url)
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
