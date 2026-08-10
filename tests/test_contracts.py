"""Tests for OpenAPI and Postman normalization."""

from __future__ import annotations

from typing import Any

import pytest

from api_test_pilot.contracts import (
    PostmanFeatureError,
    normalize_contract,
    parse_openapi,
    parse_postman,
)
from api_test_pilot.models import AuthenticationKind


def test_openapi_normalizes_operations_and_references(openapi_document: dict[str, Any]) -> None:
    """OpenAPI references and success codes should become normalized operations."""
    contract = parse_openapi(openapi_document)

    assert contract.source_format == "openapi"
    assert contract.base_url == "https://api.example.test"
    assert len(contract.operations) == 2
    assert contract.operations[0].parameters[0].name == "item_id"
    assert contract.operations[1].request_example == {"name": "probe", "quantity": 0}
    assert contract.operations[1].success_statuses == (201,)


def test_swagger_two_base_url_is_supported() -> None:
    """Swagger 2 documents should derive their server from legacy fields."""
    contract = parse_openapi(
        {
            "swagger": "2.0",
            "host": "legacy.example.test",
            "basePath": "/v1",
            "schemes": ["https"],
            "paths": {"/health": {"get": {"responses": {"204": {}}}}},
        }
    )

    assert contract.base_url == "https://legacy.example.test/v1"
    assert contract.operations[0].success_statuses == (204,)


def test_postman_flattens_folders_and_extracts_requests() -> None:
    """Nested Postman items should retain query and JSON request examples."""
    contract = parse_postman(
        {
            "info": {
                "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
            },
            "item": [
                {
                    "name": "Items",
                    "item": [
                        {
                            "name": "Create",
                            "request": {
                                "method": "POST",
                                "url": "https://api.example.test/items?dry_run=true",
                                "body": {"mode": "raw", "raw": '{"name":"probe"}'},
                            },
                        }
                    ],
                }
            ],
        }
    )

    assert contract.source_format == "postman"
    assert contract.base_url == "https://api.example.test"
    assert contract.operations[0].parameters[0].name == "dry_run"
    assert contract.operations[0].request_example == {"name": "probe"}


def test_unknown_contract_is_rejected() -> None:
    """Format detection should fail explicitly for arbitrary JSON objects."""
    with pytest.raises(ValueError, match="Unsupported contract"):
        normalize_contract({"hello": "world"})


def test_openapi_preserves_auth_responses_and_server_variables() -> None:
    """Auth requirements and response assertions should survive normalization."""
    contract = parse_openapi(
        {
            "openapi": "3.1.0",
            "servers": [
                {
                    "url": "https://{environment}.example.test/v1",
                    "variables": {"environment": {"default": "staging"}},
                }
            ],
            "security": [{"BearerAuth": []}],
            "components": {
                "securitySchemes": {
                    "BearerAuth": {"type": "http", "scheme": "bearer"},
                    "ApiKey": {"type": "apiKey", "in": "query", "name": "api_key"},
                },
                "schemas": {
                    "Health": {
                        "type": "object",
                        "required": ["status"],
                        "properties": {"status": {"type": "string"}},
                    }
                },
            },
            "paths": {
                "/health": {
                    "get": {
                        "responses": {
                            "200": {
                                "description": "Healthy",
                                "headers": {"X-Trace": {"schema": {"type": "string"}}},
                                "content": {
                                    "application/json": {
                                        "schema": {"$ref": "#/components/schemas/Health"}
                                    }
                                },
                            }
                        }
                    }
                }
            },
        }
    )

    operation = contract.operations[0]
    assert contract.base_url == "https://staging.example.test/v1"
    assert operation.security == (("BearerAuth",),)
    assert operation.responses[0].schema is not None
    assert operation.responses[0].schema["required"] == ["status"]
    assert operation.responses[0].headers == ("X-Trace",)
    assert {scheme.kind for scheme in contract.security_schemes} == {
        AuthenticationKind.HTTP_BEARER,
        AuthenticationKind.API_KEY,
    }


def test_openapi_rejects_server_variable_without_default() -> None:
    """Server templates without defaults should fail before requests are generated."""
    with pytest.raises(ValueError, match="has no default"):
        parse_openapi(
            {
                "openapi": "3.1.0",
                "servers": [{"url": "https://{stage}.test", "variables": {"stage": {}}}],
                "paths": {},
            }
        )


def test_postman_resolves_variables_auth_headers_and_examples() -> None:
    """The safe Postman subset should preserve declarative request behavior."""
    contract = parse_postman(
        {
            "info": {
                "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
            },
            "variable": [{"key": "baseUrl", "value": "https://api.example.test"}],
            "auth": {"type": "bearer", "bearer": [{"key": "token", "value": "{{token}}"}]},
            "item": [
                {
                    "name": "Create",
                    "request": {
                        "method": "POST",
                        "url": "{{baseUrl}}/items?dry_run=true",
                        "header": [{"key": "X-Tenant", "value": "{{tenant}}"}],
                        "body": {"mode": "raw", "raw": '{"name":"{{name}}"}'},
                    },
                    "response": [{"name": "Created", "code": 201}],
                }
            ],
        },
        variables={"tenant": "north", "name": "probe"},
    )

    operation = contract.operations[0]
    assert operation.success_statuses == (201,)
    assert operation.request_example == {"name": "probe"}
    assert {parameter.name for parameter in operation.parameters} == {"dry_run", "X-Tenant"}
    assert operation.security == (("postman_collection_auth",),)
    assert contract.security_schemes[0].environment_hint == "token"


def test_postman_rejects_mixed_absolute_origins() -> None:
    """Collections must not rewrite a request onto the first collection origin."""
    document = {
        "item": [
            {"name": "One", "request": {"method": "GET", "url": "https://one.example.test/a"}},
            {"name": "Two", "request": {"method": "GET", "url": "https://two.example.test/b"}},
        ]
    }

    with pytest.raises(PostmanFeatureError, match="mixed request origins"):
        parse_postman(document)


def test_postman_canonicalizes_default_ports_before_comparing_origins() -> None:
    """Explicit default ports should not make otherwise identical origins look mixed."""
    contract = parse_postman(
        {
            "item": [
                {
                    "name": "Implicit port",
                    "request": {"method": "GET", "url": "https://api.example.test/one"},
                },
                {
                    "name": "Explicit port",
                    "request": {"method": "GET", "url": "https://api.example.test:443/two"},
                },
            ]
        }
    )

    assert contract.base_url == "https://api.example.test"
    assert [operation.path for operation in contract.operations] == ["/one", "/two"]


@pytest.mark.parametrize(
    ("url", "message"),
    [
        ("ftp://api.example.test/items", "must use http or https"),
        ("https://user:secret@api.example.test/items", "must not embed credentials"),
    ],
)
def test_postman_rejects_unsafe_absolute_urls(url: str, message: str) -> None:
    """Only credential-free HTTP origins may become a suite base URL."""
    document = {"item": [{"name": "Unsafe", "request": {"method": "GET", "url": url}}]}

    with pytest.raises(PostmanFeatureError, match=message):
        parse_postman(document)


def test_postman_rejects_non_default_port_as_a_mixed_origin() -> None:
    """A non-default port is a distinct network origin and must not be rewritten."""
    document = {
        "item": [
            {"name": "Default", "request": {"method": "GET", "url": "https://api.example.test/a"}},
            {
                "name": "Non-default",
                "request": {"method": "GET", "url": "https://api.example.test:8443/b"},
            },
        ]
    }

    with pytest.raises(PostmanFeatureError, match="mixed request origins"):
        parse_postman(document)


def test_openapi_rejects_request_features_the_runner_cannot_preserve() -> None:
    """Unsupported request encodings and parameter locations must fail at parsing time."""
    xml_request = {
        "openapi": "3.1.0",
        "paths": {
            "/items": {
                "post": {
                    "requestBody": {"content": {"application/xml": {"schema": {"type": "string"}}}},
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
    }
    swagger_form = {
        "swagger": "2.0",
        "paths": {
            "/items": {
                "post": {
                    "parameters": [{"name": "name", "in": "formData", "type": "string"}],
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
    }
    cookie_parameter = {
        "openapi": "3.1.0",
        "paths": {
            "/items": {
                "get": {
                    "parameters": [
                        {"name": "session", "in": "cookie", "schema": {"type": "string"}}
                    ],
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
    }

    with pytest.raises(ValueError, match="application/json"):
        parse_openapi(xml_request)
    with pytest.raises(ValueError, match="formData"):
        parse_openapi(swagger_form)
    with pytest.raises(ValueError, match="cookie"):
        parse_openapi(cookie_parameter)


def test_openapi_rejects_external_request_schema_references() -> None:
    """Request schemas must be self-contained because generation never fetches references."""
    document = {
        "openapi": "3.1.0",
        "paths": {
            "/items": {
                "post": {
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "https://schemas.example.test/item.json"}
                            }
                        }
                    },
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
    }

    with pytest.raises(ValueError, match=r"External \$ref.*bundle"):
        parse_openapi(document)


def test_openapi_rejects_external_parameter_schema_references() -> None:
    """Parameter schemas must be self-contained before candidate generation starts."""
    document = {
        "openapi": "3.1.0",
        "paths": {
            "/items": {
                "get": {
                    "parameters": [
                        {
                            "name": "filter",
                            "in": "query",
                            "schema": {"$ref": "https://schemas.example.test/filter.json"},
                        }
                    ],
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
    }

    with pytest.raises(ValueError, match=r"External \$ref.*bundle"):
        parse_openapi(document)


def test_swagger_rejects_non_json_body_media_type() -> None:
    """Swagger body requests must use JSON because the runner serializes JSON only."""
    document = {
        "swagger": "2.0",
        "consumes": ["application/xml"],
        "paths": {
            "/items": {
                "post": {
                    "parameters": [{"name": "item", "in": "body", "schema": {"type": "object"}}],
                    "responses": {"200": {"description": "ok"}},
                }
            }
        },
    }

    with pytest.raises(ValueError, match="application/json"):
        parse_openapi(document)


@pytest.mark.parametrize(
    ("document", "message"),
    [
        (
            {"item": [{"name": "Missing", "request": {"method": "GET", "url": "{{host}}/x"}}]},
            "Unresolved Postman variables",
        ),
        (
            {
                "event": [{"listen": "test", "script": {"exec": ["pm.test('x')"]}}],
                "item": [],
            },
            "scripts are not executed",
        ),
        (
            {
                "item": [
                    {
                        "name": "Unsafe header",
                        "request": {
                            "method": "GET",
                            "url": "https://api.example.test/x",
                            "header": [{"key": "Authorization", "value": "Bearer secret"}],
                        },
                    }
                ]
            },
            "Authorization header cannot be persisted",
        ),
        (
            {
                "item": [
                    {
                        "name": "Text body",
                        "request": {
                            "method": "POST",
                            "url": "https://api.example.test/x",
                            "body": {"mode": "raw", "raw": "plain text"},
                        },
                    }
                ]
            },
            "raw request bodies must contain valid JSON",
        ),
        (
            {
                "auth": {"type": "custom-auth"},
                "item": [
                    {
                        "name": "Unknown auth",
                        "request": {"method": "GET", "url": "https://api.example.test/x"},
                    }
                ],
            },
            "authentication type 'custom-auth' is not supported",
        ),
        (
            {
                "item": [
                    {
                        "name": "Wrong content type",
                        "request": {
                            "method": "POST",
                            "url": "https://api.example.test/x",
                            "header": [{"key": "Content-Type", "value": "text/plain"}],
                            "body": {"mode": "raw", "raw": '{"name":"probe"}'},
                        },
                    }
                ]
            },
            "require an application/json Content-Type",
        ),
    ],
)
def test_postman_rejects_ambiguous_or_executable_features(
    document: dict[str, Any], message: str
) -> None:
    """Unsupported Postman behavior should fail explicitly instead of being dropped."""
    with pytest.raises(PostmanFeatureError, match=message):
        parse_postman(document)
