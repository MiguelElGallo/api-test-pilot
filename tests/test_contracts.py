"""Tests for OpenAPI and Postman normalization."""

from __future__ import annotations

from typing import Any

import pytest

from api_test_pilot.contracts import normalize_contract, parse_openapi, parse_postman


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
