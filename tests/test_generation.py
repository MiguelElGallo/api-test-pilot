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


def test_relative_server_requires_override_for_local_contract(
    openapi_document: dict[str, Any],
) -> None:
    """A local specification cannot provide an executable origin for a relative server."""
    openapi_document["servers"] = [{"url": "/api/v3"}]

    with pytest.raises(ValueError, match=r"relative.*--base-url"):
        generate_suite(parse_openapi(openapi_document), source="openapi.yaml")


@pytest.mark.parametrize(
    ("base_url", "message"),
    [
        ("https://user:secret@api.example.test", "must not embed credentials"),
        ("https://api.example.test?tenant=north", "must not include query parameters"),
        ("https://api.example.test#v1", "must not include query parameters"),
    ],
)
def test_base_url_override_rejects_unsafe_components(
    openapi_document: dict[str, Any], base_url: str, message: str
) -> None:
    """Suite base URLs cannot carry credentials or request-specific components."""
    with pytest.raises(ValueError, match=message):
        generate_suite(parse_openapi(openapi_document), source="fixture", base_url=base_url)


@pytest.mark.parametrize(
    "base_url",
    ["https://api.example.test:bad", "https://api.example.test:99999", "https:///items"],
)
def test_base_url_override_rejects_invalid_host_or_port(
    openapi_document: dict[str, Any], base_url: str
) -> None:
    """Malformed host and port syntax must fail before a suite can reach transport."""
    with pytest.raises(ValueError, match="Invalid base URL"):
        generate_suite(parse_openapi(openapi_document), source="fixture", base_url=base_url)


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


def test_all_of_request_bodies_include_dereferenced_required_fields() -> None:
    """Composed object bodies should inherit every required property for both positive cases."""
    document = {
        "openapi": "3.1.0",
        "servers": [{"url": "https://api.example.test"}],
        "components": {
            "schemas": {
                "Identity": {
                    "type": "object",
                    "required": ["id"],
                    "properties": {"id": {"type": "integer", "minimum": 1}},
                },
                "Details": {
                    "type": "object",
                    "required": ["name"],
                    "properties": {"name": {"type": "string", "minLength": 2, "maxLength": 5}},
                },
                "CreateItem": {
                    "allOf": [
                        {"$ref": "#/components/schemas/Identity"},
                        {"$ref": "#/components/schemas/Details"},
                    ]
                },
            }
        },
        "paths": {
            "/items": {
                "post": {
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/CreateItem"}
                            }
                        },
                    },
                    "responses": {"201": {"description": "created"}},
                }
            }
        },
    }

    suite = generate_suite(parse_openapi(document), source="fixture", allowed_methods=["POST"])
    functional, _, edge = suite.scenarios

    assert functional.body == {"id": 1, "name": "xx"}
    assert edge.body == {"id": 1, "name": "x" * 5}


def test_all_of_request_bodies_merge_nested_dereferenced_object_branches() -> None:
    """Nested object composition should retain fields inherited by an intermediate schema."""
    document = {
        "openapi": "3.1.0",
        "servers": [{"url": "https://api.example.test"}],
        "components": {
            "schemas": {
                "Identifier": {
                    "type": "object",
                    "required": ["id"],
                    "properties": {"id": {"type": "integer", "minimum": 1}},
                },
                "Label": {
                    "type": "object",
                    "required": ["label"],
                    "properties": {"label": {"type": "string", "minLength": 2}},
                },
                "Identity": {
                    "allOf": [
                        {"$ref": "#/components/schemas/Identifier"},
                        {"$ref": "#/components/schemas/Label"},
                    ]
                },
                "State": {
                    "type": "object",
                    "required": ["enabled"],
                    "properties": {"enabled": {"type": "boolean"}},
                },
                "CreateItem": {
                    "allOf": [
                        {"$ref": "#/components/schemas/Identity"},
                        {"$ref": "#/components/schemas/State"},
                    ]
                },
            }
        },
        "paths": {
            "/items": {
                "post": {
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/CreateItem"}
                            }
                        }
                    },
                    "responses": {"201": {"description": "created"}},
                }
            }
        },
    }

    suite = generate_suite(parse_openapi(document), source="fixture", allowed_methods=["POST"])
    functional, _, edge = suite.scenarios

    assert functional.body == {"id": 1, "label": "xx", "enabled": True}
    assert edge.body == {"id": 1, "label": "x" * 128, "enabled": False}


def test_generation_fails_when_resource_caps_prevent_a_valid_edge_body() -> None:
    """Resource caps must not quietly write an edge value below the documented minimum."""
    document = {
        "openapi": "3.1.0",
        "servers": [{"url": "https://api.example.test"}],
        "paths": {
            "/items": {
                "post": {
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["value"],
                                    "properties": {"value": {"type": "string", "minLength": 300}},
                                }
                            }
                        }
                    },
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
    }

    with pytest.raises(ValueError, match=r"Generated functional request body.*does not satisfy"):
        generate_suite(parse_openapi(document), source="fixture", allowed_methods=["POST"])


def test_generation_rejects_invalid_documented_positive_parameter_example() -> None:
    """A functional parameter example must satisfy the normalized parameter schema."""
    document = {
        "openapi": "3.1.0",
        "servers": [{"url": "https://api.example.test"}],
        "paths": {
            "/items": {
                "get": {
                    "parameters": [
                        {
                            "name": "limit",
                            "in": "query",
                            "required": True,
                            "example": 6,
                            "schema": {"type": "integer", "maximum": 5},
                        }
                    ],
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
    }

    with pytest.raises(
        ValueError, match=r"Generated functional query parameter 'limit'.*does not satisfy"
    ):
        generate_suite(parse_openapi(document), source="fixture")


def test_generation_rejects_invalid_edge_parameter_candidate_after_resource_cap() -> None:
    """Edge parameter values must fail rather than bypassing a documented minimum length."""
    document = {
        "openapi": "3.1.0",
        "servers": [{"url": "https://api.example.test"}],
        "paths": {
            "/items": {
                "get": {
                    "parameters": [
                        {
                            "name": "X-Token",
                            "in": "header",
                            "required": True,
                            "example": "x" * 300,
                            "schema": {"type": "string", "minLength": 300},
                        }
                    ],
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
    }

    with pytest.raises(
        ValueError, match=r"Generated edge header parameter 'X-Token'.*does not satisfy"
    ):
        generate_suite(parse_openapi(document), source="fixture")


@pytest.mark.parametrize(
    ("version_key", "version", "parameter"),
    [
        (
            "openapi",
            "3.0.3",
            {
                "name": "score",
                "in": "query",
                "required": True,
                "schema": {
                    "type": "integer",
                    "minimum": 0,
                    "exclusiveMinimum": True,
                    "maximum": 10,
                    "exclusiveMaximum": True,
                },
            },
        ),
        (
            "swagger",
            "2.0",
            {
                "name": "score",
                "in": "query",
                "required": True,
                "type": "integer",
                "minimum": 0,
                "exclusiveMinimum": True,
                "maximum": 10,
                "exclusiveMaximum": True,
            },
        ),
    ],
)
def test_generation_normalizes_legacy_boolean_exclusive_bounds(
    version_key: str, version: str, parameter: dict[str, Any]
) -> None:
    """Swagger and OpenAPI 3.0 bounds should become valid numeric JSON Schema bounds."""
    document = {
        version_key: version,
        "servers": [{"url": "https://api.example.test"}],
        "host": "api.example.test",
        "schemes": ["https"],
        "paths": {
            "/items": {
                "get": {
                    "parameters": [parameter],
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
    }

    suite = generate_suite(parse_openapi(document), source="fixture")
    functional, _, edge = suite.scenarios

    assert functional.query == {"score": 1}
    assert edge.query == {"score": 9}


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
