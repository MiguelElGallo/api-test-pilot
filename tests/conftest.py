"""Shared contract and scenario fixtures."""

from __future__ import annotations

from typing import Any

import pytest


@pytest.fixture
def openapi_document() -> dict[str, Any]:
    """Return a compact contract with path parameters and a required JSON body."""
    return {
        "openapi": "3.1.0",
        "info": {"title": "Fixture", "version": "1.0.0"},
        "servers": [{"url": "https://api.example.test"}],
        "paths": {
            "/items/{item_id}": {
                "get": {
                    "operationId": "get_item",
                    "summary": "Get item",
                    "parameters": [
                        {
                            "name": "item_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "integer", "minimum": 1, "maximum": 99},
                        }
                    ],
                    "responses": {"200": {"description": "Found"}},
                }
            },
            "/items": {
                "post": {
                    "operationId": "create_item",
                    "summary": "Create item",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {"schema": {"$ref": "#/components/schemas/Item"}}
                        },
                    },
                    "responses": {"201": {"description": "Created"}},
                }
            },
        },
        "components": {
            "schemas": {
                "Item": {
                    "type": "object",
                    "required": ["name", "quantity"],
                    "properties": {
                        "name": {"type": "string", "example": "probe"},
                        "quantity": {"type": "integer", "minimum": 0},
                    },
                }
            }
        },
    }
