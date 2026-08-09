"""Validate HTTP responses against assertions preserved from an API contract."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from jsonschema import SchemaError
from jsonschema.validators import validator_for

from api_test_pilot.models import ExpectedResponse, Scenario

if TYPE_CHECKING:
    import httpx


def _expectation_for_status(scenario: Scenario, status_code: int) -> ExpectedResponse | None:
    """Return the documented response assertion for the observed status."""
    return next(
        (
            expectation
            for expectation in scenario.expected_responses
            if expectation.status_code == status_code
        ),
        None,
    )


def _media_type_matches(expected: str, actual: str) -> bool:
    """Compare media types while allowing parameters and structured JSON suffixes."""
    normalized_expected = expected.split(";", 1)[0].strip().lower()
    normalized_actual = actual.split(";", 1)[0].strip().lower()
    if normalized_expected == normalized_actual:
        return True
    return normalized_expected == "application/json" and normalized_actual.endswith("+json")


def _schema_errors(instance: Any, schema: dict[str, Any]) -> list[str]:
    """Return concise validation failures using the schema's declared dialect."""
    validator_type = validator_for(schema)
    try:
        validator_type.check_schema(schema)
    except SchemaError as exc:
        return [f"Invalid response schema in generated suite: {exc.message}"]
    errors = sorted(validator_type(schema).iter_errors(instance), key=lambda item: list(item.path))
    return [
        f"Response schema mismatch at {'/'.join(str(part) for part in error.path) or '<root>'}: "
        f"{error.message}"
        for error in errors[:5]
    ]


def validate_response(response: httpx.Response, scenario: Scenario) -> list[str]:
    """Validate documented media type, headers, and JSON Schema for a response."""
    expectation = _expectation_for_status(scenario, response.status_code)
    if expectation is None:
        return []
    failures = [
        f"Missing documented response header: {header}"
        for header in expectation.headers
        if header.lower() not in response.headers
    ]
    actual_media_type = response.headers.get("content-type", "")
    if expectation.media_type and not _media_type_matches(
        expectation.media_type, actual_media_type
    ):
        failures.append(
            f"Expected content type {expectation.media_type}, received "
            f"{actual_media_type or '<missing>'}"
        )
    if expectation.response_schema is not None:
        try:
            payload = response.json()
        except ValueError:
            failures.append("Response body is not valid JSON for its documented schema")
        else:
            failures.extend(_schema_errors(payload, expectation.response_schema))
    return failures
