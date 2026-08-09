"""Tests for deterministic scenario strategies."""

from __future__ import annotations

from typing import Any

import pytest

from api_test_pilot.contracts import parse_openapi
from api_test_pilot.generation import generate_suite
from api_test_pilot.models import ScenarioCategory


def test_generates_all_categories_for_each_operation(openapi_document: dict[str, Any]) -> None:
    """Every operation should receive functional, negative, and edge coverage."""
    suite = generate_suite(
        parse_openapi(openapi_document), source="fixture", allowed_methods=["GET", "POST"]
    )

    assert len(suite.scenarios) == 6
    for operation_prefix in ("get-item", "create-item"):
        categories = {
            scenario.category
            for scenario in suite.scenarios
            if scenario.identifier.startswith(operation_prefix)
        }
        assert categories == set(ScenarioCategory)


def test_negative_strategies_remove_required_inputs(openapi_document: dict[str, Any]) -> None:
    """Negative scenarios should omit path inputs or request bodies."""
    suite = generate_suite(
        parse_openapi(openapi_document), source="fixture", allowed_methods=["GET", "POST"]
    )
    negative = {
        scenario.identifier: scenario
        for scenario in suite.scenarios
        if scenario.category == ScenarioCategory.NEGATIVE
    }

    assert negative["get-item-negative-invalid-item-id"].path.endswith("not-a-valid-value")
    assert negative["create-item-negative-missing-request-body"].body is None
    assert 422 in negative["create-item-negative-missing-request-body"].expected_statuses


def test_base_url_override_is_respected(openapi_document: dict[str, Any]) -> None:
    """CLI users should be able to target an environment other than the contract server."""
    suite = generate_suite(
        parse_openapi(openapi_document),
        source="fixture",
        base_url="http://localhost:9000/",
    )

    assert suite.base_url == "http://localhost:9000"


def test_relative_server_resolves_against_remote_contract(openapi_document: dict[str, Any]) -> None:
    """Relative OpenAPI server URLs should resolve against the specification origin."""
    openapi_document["servers"] = [{"url": "/api/v3"}]

    suite = generate_suite(
        parse_openapi(openapi_document),
        source="https://petstore.example.test/api/v3/openapi.json",
    )

    assert suite.base_url == "https://petstore.example.test/api/v3"


def test_default_policy_excludes_mutating_operations(openapi_document: dict[str, Any]) -> None:
    """Safe generation should require explicit opt-in for POST, PUT, PATCH, and DELETE."""
    suite = generate_suite(parse_openapi(openapi_document), source="fixture")

    assert suite.execution.allowed_methods == ["GET", "HEAD", "OPTIONS"]
    assert {scenario.method for scenario in suite.scenarios} == {"GET"}


def test_negative_fallback_describes_unknown_resource() -> None:
    """An operation with no required input should explain its unknown-path check."""
    contract = parse_openapi(
        {
            "openapi": "3.1.0",
            "servers": [{"url": "https://api.example.test"}],
            "paths": {"/health": {"get": {"responses": {"200": {"description": "ok"}}}}},
        }
    )

    suite = generate_suite(contract, source="fixture")

    assert "unknown resource" in suite.scenarios[1].description


def test_edge_request_body_uses_schema_boundaries(openapi_document: dict[str, Any]) -> None:
    """Body-centric edge cases should differ from the functional example."""
    item_schema = openapi_document["components"]["schemas"]["Item"]
    item_schema["properties"]["name"]["maxLength"] = 12
    item_schema["properties"]["quantity"]["maximum"] = 99
    suite = generate_suite(
        parse_openapi(openapi_document),
        source="fixture",
        allowed_methods=["POST"],
    )
    functional, _, edge = suite.scenarios

    assert functional.body == {"name": "probe", "quantity": 0}
    assert edge.body == {"name": "x" * 12, "quantity": 99}
    assert edge.body != functional.body


def test_generation_preserves_auth_bindings_and_response_contracts() -> None:
    """Suites should carry only environment references plus response assertions."""
    contract = parse_openapi(
        {
            "openapi": "3.1.0",
            "servers": [{"url": "https://api.example.test"}],
            "components": {"securitySchemes": {"BearerAuth": {"type": "http", "scheme": "bearer"}}},
            "security": [{"BearerAuth": []}],
            "paths": {
                "/health": {
                    "get": {
                        "responses": {
                            "200": {
                                "description": "ok",
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "type": "object",
                                            "required": ["status"],
                                            "properties": {"status": {"type": "string"}},
                                        }
                                    }
                                },
                            }
                        }
                    }
                }
            },
        }
    )
    suite = generate_suite(
        contract,
        source="fixture",
        authentication_environment={"BearerAuth": "STAGING_API_TOKEN"},
    )

    assert suite.authentication["BearerAuth"].environment_variable == "STAGING_API_TOKEN"
    assert suite.scenarios[0].security == [["BearerAuth"]]
    assert suite.scenarios[0].expected_responses[0].response_schema is not None


def test_generation_fails_when_policy_matches_no_operations(
    openapi_document: dict[str, Any],
) -> None:
    """A policy typo should not silently produce an empty regression suite."""
    with pytest.raises(ValueError, match="No operations match"):
        generate_suite(
            parse_openapi(openapi_document),
            source="fixture",
            allowed_methods=["DELETE"],
        )
