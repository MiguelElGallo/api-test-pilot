"""Tests for deterministic scenario strategies."""

from __future__ import annotations

from typing import Any

from api_test_pilot.contracts import parse_openapi
from api_test_pilot.generation import generate_suite
from api_test_pilot.models import ScenarioCategory


def test_generates_all_categories_for_each_operation(openapi_document: dict[str, Any]) -> None:
    """Every operation should receive functional, negative, and edge coverage."""
    suite = generate_suite(parse_openapi(openapi_document), source="fixture")

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
    suite = generate_suite(parse_openapi(openapi_document), source="fixture")
    negative = {
        scenario.identifier: scenario
        for scenario in suite.scenarios
        if scenario.category == ScenarioCategory.NEGATIVE
    }

    assert "{item_id}" in negative["get-item-negative-missing-item-id"].path
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
