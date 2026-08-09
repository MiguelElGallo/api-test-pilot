"""Normalize OpenAPI and Postman documents into transport-neutral operations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse


@dataclass(frozen=True, slots=True)
class Parameter:
    """A normalized request parameter from an API contract."""

    name: str
    location: str
    required: bool
    schema: dict[str, Any] = field(default_factory=dict)
    example: Any | None = None


@dataclass(frozen=True, slots=True)
class Operation:
    """A normalized operation consumed by scenario strategies."""

    identifier: str
    method: str
    path: str
    summary: str
    parameters: tuple[Parameter, ...]
    request_schema: dict[str, Any] | None
    request_example: Any | None
    request_required: bool
    success_statuses: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class Contract:
    """A normalized API contract with a preferred base URL."""

    source_format: str
    base_url: str
    operations: tuple[Operation, ...]


_HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}


def _resolve_ref(document: dict[str, Any], value: Any) -> Any:
    """Resolve a local JSON pointer while leaving remote references untouched."""
    if not isinstance(value, dict) or "$ref" not in value:
        return value
    reference = value["$ref"]
    if not isinstance(reference, str) or not reference.startswith("#/"):
        return value
    current: Any = document
    for part in reference[2:].split("/"):
        if not isinstance(current, dict):
            return value
        current = current.get(part.replace("~1", "/").replace("~0", "~"))
    return current if current is not None else value


def _openapi_example(schema: dict[str, Any], document: dict[str, Any]) -> Any:
    """Create a small valid example from common JSON Schema keywords."""
    schema = _resolve_ref(document, schema)
    if not isinstance(schema, dict):
        return None
    if "example" in schema:
        return schema["example"]
    if "default" in schema:
        return schema["default"]
    choices = schema.get("enum")
    if isinstance(choices, list) and choices:
        return choices[0]
    schema_type = schema.get("type")
    if schema_type == "object" or "properties" in schema:
        properties = schema.get("properties", {})
        required = set(schema.get("required", []))
        return {
            name: _openapi_example(value, document)
            for name, value in properties.items()
            if name in required or "example" in value or "default" in value
        }
    if schema_type == "array":
        return [_openapi_example(schema.get("items", {}), document)]
    if schema_type == "integer":
        return int(schema.get("minimum", 1))
    if schema_type == "number":
        return float(schema.get("minimum", 1.0))
    if schema_type == "boolean":
        return True
    if schema.get("format") == "email":
        return "test@example.com"
    return schema.get("minLength", 1) * "x"


def parse_openapi(document: dict[str, Any]) -> Contract:
    """Normalize an OpenAPI 2.x or 3.x document."""
    servers = document.get("servers", [])
    if servers and isinstance(servers[0], dict):
        base_url = str(servers[0].get("url", ""))
    else:
        scheme = document.get("schemes", ["https"])[0]
        base_url = f"{scheme}://{document.get('host', '')}{document.get('basePath', '')}"
    operations: list[Operation] = []
    for path, path_item in document.get("paths", {}).items():
        if not isinstance(path_item, dict):
            continue
        common_parameters = path_item.get("parameters", [])
        for method, operation in path_item.items():
            if method.lower() not in _HTTP_METHODS or not isinstance(operation, dict):
                continue
            raw_parameters = [*common_parameters, *operation.get("parameters", [])]
            parameters = tuple(
                Parameter(
                    name=str(parameter.get("name", "parameter")),
                    location=str(parameter.get("in", "query")),
                    required=bool(parameter.get("required", False)),
                    schema=_resolve_ref(document, parameter.get("schema", parameter)),
                    example=parameter.get("example"),
                )
                for raw_parameter in raw_parameters
                if isinstance((parameter := _resolve_ref(document, raw_parameter)), dict)
            )
            request_body = operation.get("requestBody", {})
            content = request_body.get("content", {}) if isinstance(request_body, dict) else {}
            media = content.get("application/json", next(iter(content.values()), {}))
            request_schema = _resolve_ref(document, media.get("schema")) if media else None
            request_example = media.get("example") if media else None
            if request_example is None and isinstance(request_schema, dict):
                request_example = _openapi_example(request_schema, document)
            statuses = tuple(
                sorted(
                    int(status)
                    for status in operation.get("responses", {})
                    if str(status).isdigit() and 200 <= int(status) < 300
                )
            ) or (200,)
            operations.append(
                Operation(
                    identifier=str(operation.get("operationId", f"{method}_{path}")),
                    method=method.upper(),
                    path=str(path),
                    summary=str(operation.get("summary", f"{method.upper()} {path}")),
                    parameters=parameters,
                    request_schema=request_schema,
                    request_example=request_example,
                    request_required=bool(request_body.get("required", False)),
                    success_statuses=statuses,
                )
            )
    return Contract("openapi", base_url, tuple(operations))


def _postman_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flatten nested Postman folders into request items."""
    flattened: list[dict[str, Any]] = []
    for item in items:
        nested = item.get("item")
        if isinstance(nested, list):
            flattened.extend(_postman_items(nested))
        elif "request" in item:
            flattened.append(item)
    return flattened


def parse_postman(document: dict[str, Any]) -> Contract:
    """Normalize a Postman Collection v2.0 or v2.1 document."""
    operations: list[Operation] = []
    base_url = ""
    for index, item in enumerate(_postman_items(document.get("item", []))):
        request = item.get("request", {})
        if isinstance(request, str):
            request = {"url": request, "method": "GET"}
        raw_url = request.get("url", "")
        if isinstance(raw_url, dict):
            raw_url = raw_url.get("raw", "")
        parsed = urlparse(str(raw_url).replace("{{baseUrl}}", "http://localhost"))
        if parsed.netloc and not base_url:
            base_url = f"{parsed.scheme}://{parsed.netloc}"
        path = parsed.path or "/"
        query = tuple(
            Parameter(name=key, location="query", required=False, example=value)
            for key, value in __import__("urllib.parse").parse.parse_qsl(parsed.query)
        )
        body = request.get("body", {})
        raw_body = body.get("raw") if isinstance(body, dict) else None
        body_example: Any | None = None
        if raw_body:
            try:
                body_example = __import__("json").loads(raw_body)
            except ValueError:
                body_example = raw_body
        operations.append(
            Operation(
                identifier=f"postman_{index}_{item.get('name', 'request')}",
                method=str(request.get("method", "GET")).upper(),
                path=path,
                summary=str(item.get("name", f"Request {index + 1}")),
                parameters=query,
                request_schema=None,
                request_example=body_example,
                request_required=body_example is not None,
                success_statuses=(200, 201, 202, 204),
            )
        )
    return Contract("postman", base_url, tuple(operations))


def normalize_contract(document: dict[str, Any]) -> Contract:
    """Detect and normalize a supported API contract."""
    if "openapi" in document or "swagger" in document:
        return parse_openapi(document)
    schema = str(document.get("info", {}).get("schema", ""))
    if "postman" in schema or "item" in document:
        return parse_postman(document)
    raise ValueError("Unsupported contract: expected OpenAPI/Swagger or Postman Collection")
