"""Tests for response contract validation."""

from __future__ import annotations

import httpx

from api_test_pilot.models import ExpectedResponse, Scenario, ScenarioCategory
from api_test_pilot.validation import validate_response


def _scenario(schema: dict[str, object] | None = None) -> Scenario:
    """Create a scenario with JSON, header, and schema assertions."""
    return Scenario(
        identifier="contract",
        name="Contract",
        category=ScenarioCategory.FUNCTIONAL,
        method="GET",
        path="/contract",
        expected_statuses=[200],
        expected_responses=[
            ExpectedResponse(
                status_code=200,
                media_type="application/json",
                response_schema=schema,
                headers=["X-Trace"],
            )
        ],
        description="Validates a response contract.",
    )


def test_valid_response_satisfies_all_contract_assertions() -> None:
    """Matching JSON, content type, and headers should produce no failures."""
    response = httpx.Response(
        200,
        json={"status": "ok"},
        headers={"Content-Type": "application/problem+json", "X-Trace": "1"},
    )

    failures = validate_response(
        response,
        _scenario(
            {
                "type": "object",
                "required": ["status"],
                "properties": {"status": {"type": "string"}},
            }
        ),
    )

    assert failures == []


def test_invalid_response_reports_header_media_and_schema_failures() -> None:
    """Contract mismatches should be concise and aggregated for reports."""
    response = httpx.Response(200, json={"status": 42}, headers={"Content-Type": "text/plain"})

    failures = validate_response(
        response,
        _scenario(
            {
                "type": "object",
                "properties": {"status": {"type": "string"}},
            }
        ),
    )

    assert any("Missing documented response header" in failure for failure in failures)
    assert any("Expected content type" in failure for failure in failures)
    assert any("schema mismatch" in failure for failure in failures)


def test_non_json_and_invalid_embedded_schema_are_reported() -> None:
    """Malformed JSON and malformed suite schemas should fail deterministically."""
    non_json = httpx.Response(
        200,
        text="not-json",
        headers={"Content-Type": "application/json", "X-Trace": "1"},
    )
    invalid_schema = httpx.Response(
        200,
        json={"status": "ok"},
        headers={"Content-Type": "application/json", "X-Trace": "1"},
    )

    assert "not valid JSON" in validate_response(non_json, _scenario({"type": "object"}))[0]
    assert (
        "Invalid response schema" in validate_response(invalid_schema, _scenario({"type": 42}))[0]
    )


def test_undocumented_status_has_no_additional_assertions() -> None:
    """Status handling remains the runner's responsibility when no assertion exists."""
    assert validate_response(httpx.Response(404), _scenario()) == []
