"""Normalize OpenAPI and Postman documents into transport-neutral operations."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qsl, urlparse

from api_test_pilot.models import AuthenticationKind


class PostmanFeatureError(ValueError):
    """Indicate that a collection depends on unsupported executable behavior."""


@dataclass(frozen=True, slots=True)
class Parameter:
    """A normalized request parameter from an API contract."""

    name: str
    location: str
    required: bool
    schema: dict[str, Any] = field(default_factory=dict)
    example: Any | None = None


@dataclass(frozen=True, slots=True)
class ResponseContract:
    """A normalized response schema and metadata for one status code."""

    status_code: int
    media_type: str | None = None
    schema: dict[str, Any] | None = None
    headers: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SecurityScheme:
    """A normalized, secret-free API authentication mechanism."""

    name: str
    kind: AuthenticationKind
    location: str | None = None
    parameter_name: str | None = None
    environment_hint: str | None = None


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
    responses: tuple[ResponseContract, ...] = ()
    security: tuple[tuple[str, ...], ...] = ()


@dataclass(frozen=True, slots=True)
class Contract:
    """A normalized API contract with a preferred base URL."""

    source_format: str
    base_url: str
    operations: tuple[Operation, ...]
    security_schemes: tuple[SecurityScheme, ...] = ()


_HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}
_VARIABLE_PATTERN = re.compile(r"{{\s*([^{}]+?)\s*}}")


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


def _dereference_schema(
    document: dict[str, Any],
    value: Any,
    *,
    references: frozenset[str] = frozenset(),
) -> Any:
    """Expand local schema references so generated suites remain self-contained."""
    if isinstance(value, list):
        return [_dereference_schema(document, item, references=references) for item in value]
    if not isinstance(value, dict):
        return value
    reference = value.get("$ref")
    if isinstance(reference, str) and reference.startswith("#/"):
        if reference in references:
            return {}
        resolved = _resolve_ref(document, value)
        return _dereference_schema(document, resolved, references=references | {reference})
    expanded = {
        key: _dereference_schema(document, item, references=references)
        for key, item in value.items()
    }
    if expanded.pop("nullable", False):
        schema_type = expanded.get("type")
        if isinstance(schema_type, str):
            expanded["type"] = [schema_type, "null"]
        elif "anyOf" in expanded:
            expanded["anyOf"].append({"type": "null"})
    return expanded


def _schema_example(  # noqa: PLR0912 - JSON Schema types require distinct strategies.
    schema: dict[str, Any], document: dict[str, Any]
) -> Any:
    """Create a small valid example from common JSON Schema keywords."""
    schema = _dereference_schema(document, schema)
    if not isinstance(schema, dict):
        return None
    if "example" in schema:
        return schema["example"]
    examples = schema.get("examples")
    if isinstance(examples, list) and examples:
        return examples[0]
    if "default" in schema:
        return schema["default"]
    choices = schema.get("enum")
    if isinstance(choices, list) and choices:
        return choices[0]
    for composition in ("oneOf", "anyOf"):
        branches = schema.get(composition)
        if isinstance(branches, list) and branches:
            return _schema_example(branches[0], document)
    schema_type = schema.get("type")
    if schema_type == "object" or "properties" in schema:
        properties = schema.get("properties", {})
        required = set(schema.get("required", []))
        return {
            name: _schema_example(value, document)
            for name, value in properties.items()
            if name in required or "example" in value or "examples" in value or "default" in value
        }
    if schema_type == "array":
        return [_schema_example(schema.get("items", {}), document)]
    if schema_type == "integer":
        return int(schema.get("minimum", 1))
    if schema_type == "number":
        return float(schema.get("minimum", 1.0))
    if schema_type == "boolean":
        return True
    if schema.get("format") == "email":
        return "test@example.com"
    return "x" * int(schema.get("minLength", 1))


def _server_url(document: dict[str, Any]) -> str:
    """Return the first OpenAPI server URL with documented variable defaults applied."""
    servers = document.get("servers", [])
    if servers and isinstance(servers[0], dict):
        server = servers[0]
        url = str(server.get("url", ""))
        for name, details in server.get("variables", {}).items():
            if not isinstance(details, dict) or "default" not in details:
                raise ValueError(f"OpenAPI server variable '{name}' has no default value")
            url = url.replace(f"{{{name}}}", str(details["default"]))
        return url
    schemes = document.get("schemes", ["https"])
    scheme = schemes[0] if schemes else "https"
    host = document.get("host", "")
    return f"{scheme}://{host}{document.get('basePath', '')}" if host else ""


def _openapi_security_schemes(document: dict[str, Any]) -> tuple[SecurityScheme, ...]:
    """Normalize OpenAPI 2 and 3 security scheme declarations."""
    raw_schemes = document.get("components", {}).get(
        "securitySchemes", document.get("securityDefinitions", {})
    )
    schemes: list[SecurityScheme] = []
    for name, raw_scheme in raw_schemes.items():
        scheme = _resolve_ref(document, raw_scheme)
        if not isinstance(scheme, dict):
            continue
        scheme_type = str(scheme.get("type", "")).lower()
        http_scheme = str(scheme.get("scheme", "")).lower()
        if scheme_type == "apikey":
            schemes.append(
                SecurityScheme(
                    name=name,
                    kind=AuthenticationKind.API_KEY,
                    location=str(scheme.get("in", "header")),
                    parameter_name=str(scheme.get("name", "X-API-Key")),
                )
            )
        elif scheme_type == "basic" or (scheme_type == "http" and http_scheme == "basic"):
            schemes.append(SecurityScheme(name=name, kind=AuthenticationKind.HTTP_BASIC))
        elif scheme_type == "http" and http_scheme == "bearer":
            schemes.append(SecurityScheme(name=name, kind=AuthenticationKind.HTTP_BEARER))
        elif scheme_type == "oauth2":
            schemes.append(SecurityScheme(name=name, kind=AuthenticationKind.OAUTH2))
        elif scheme_type == "openidconnect":
            schemes.append(SecurityScheme(name=name, kind=AuthenticationKind.OPENID_CONNECT))
    return tuple(schemes)


def _security_requirements(raw_security: Any) -> tuple[tuple[str, ...], ...]:
    """Preserve OpenAPI security alternatives without scopes or secret material."""
    if not isinstance(raw_security, list):
        return ()
    return tuple(
        tuple(str(name) for name in requirement)
        for requirement in raw_security
        if isinstance(requirement, dict) and requirement
    )


def _response_contracts(
    document: dict[str, Any], operation: dict[str, Any]
) -> tuple[ResponseContract, ...]:
    """Normalize response statuses, schemas, media types, and documented headers."""
    responses: list[ResponseContract] = []
    for raw_status, raw_response in operation.get("responses", {}).items():
        if not str(raw_status).isdigit():
            continue
        response = _resolve_ref(document, raw_response)
        if not isinstance(response, dict):
            continue
        content = response.get("content", {})
        media_type: str | None = None
        schema: dict[str, Any] | None = None
        if isinstance(content, dict) and content:
            media_type = (
                "application/json" if "application/json" in content else next(iter(content))
            )
            media = content.get(media_type, {})
            if isinstance(media, dict) and isinstance(media.get("schema"), dict):
                schema = _dereference_schema(document, media["schema"])
        elif isinstance(response.get("schema"), dict):
            schema = _dereference_schema(document, response["schema"])
            produces = operation.get("produces", document.get("produces", ["application/json"]))
            media_type = str(produces[0]) if produces else "application/json"
        headers = response.get("headers", {})
        responses.append(
            ResponseContract(
                status_code=int(raw_status),
                media_type=media_type,
                schema=schema,
                headers=tuple(str(name) for name in headers),
            )
        )
    return tuple(sorted(responses, key=lambda item: item.status_code))


def _request_contract(
    document: dict[str, Any],
    operation: dict[str, Any],
    raw_parameters: list[Any],
) -> tuple[dict[str, Any] | None, Any | None, bool]:
    """Extract an OpenAPI 2 or 3 JSON request body contract."""
    request_body = _resolve_ref(document, operation.get("requestBody", {}))
    if isinstance(request_body, dict) and request_body:
        content = request_body.get("content", {})
        media = content.get("application/json", next(iter(content.values()), {}))
        request_schema = (
            _dereference_schema(document, media.get("schema")) if isinstance(media, dict) else None
        )
        request_example = media.get("example") if isinstance(media, dict) else None
        if request_example is None and isinstance(media, dict):
            examples = media.get("examples")
            if isinstance(examples, dict) and examples:
                first_example = next(iter(examples.values()))
                if isinstance(first_example, dict):
                    request_example = first_example.get("value")
        if request_example is None and isinstance(request_schema, dict):
            request_example = _schema_example(request_schema, document)
        return request_schema, request_example, bool(request_body.get("required", False))
    for raw_parameter in raw_parameters:
        parameter = _resolve_ref(document, raw_parameter)
        if isinstance(parameter, dict) and parameter.get("in") == "body":
            schema = _dereference_schema(document, parameter.get("schema", {}))
            return schema, _schema_example(schema, document), bool(parameter.get("required", False))
    return None, None, False


def parse_openapi(document: dict[str, Any]) -> Contract:
    """Normalize an OpenAPI 2.x or 3.x document."""
    operations: list[Operation] = []
    inherited_security = document.get("security", [])
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
                    schema=_dereference_schema(
                        document, parameter.get("schema", parameter.get("items", parameter))
                    ),
                    example=parameter.get("example", parameter.get("schema", {}).get("example")),
                )
                for raw_parameter in raw_parameters
                if isinstance((parameter := _resolve_ref(document, raw_parameter)), dict)
                and parameter.get("in") != "body"
            )
            request_schema, request_example, request_required = _request_contract(
                document, operation, raw_parameters
            )
            responses = _response_contracts(document, operation)
            success_statuses = tuple(
                response.status_code for response in responses if 200 <= response.status_code < 300
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
                    request_required=request_required,
                    success_statuses=success_statuses,
                    responses=responses,
                    security=_security_requirements(operation.get("security", inherited_security)),
                )
            )
    return Contract(
        "openapi",
        _server_url(document),
        tuple(operations),
        _openapi_security_schemes(document),
    )


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


def _reject_postman_scripts(document: dict[str, Any]) -> None:
    """Reject scripts because executing arbitrary collection JavaScript is unsafe."""
    stack: list[dict[str, Any]] = [document]
    while stack:
        current = stack.pop()
        for event in current.get("event", []):
            script = event.get("script", {}) if isinstance(event, dict) else {}
            commands = script.get("exec", []) if isinstance(script, dict) else []
            if commands:
                listener = event.get("listen", "script")
                raise PostmanFeatureError(
                    f"Postman {listener} scripts are not executed; export a script-free collection"
                )
        stack.extend(item for item in current.get("item", []) if isinstance(item, dict))


def _postman_variables(
    document: dict[str, Any], overrides: dict[str, str] | None
) -> dict[str, str]:
    """Combine collection variable defaults with explicit environment overrides."""
    variables = {
        str(variable.get("key")): str(variable.get("value", ""))
        for variable in document.get("variable", [])
        if isinstance(variable, dict) and variable.get("key") is not None
    }
    variables.update(overrides or {})
    return variables


def _interpolate_postman(value: str, variables: dict[str, str]) -> str:
    """Resolve Postman variables or fail with a precise configuration error."""
    missing: set[str] = set()

    def replace(match: re.Match[str]) -> str:
        """Replace one Postman variable reference while collecting missing names."""
        name = match.group(1)
        if name not in variables:
            missing.add(name)
            return match.group(0)
        return variables[name]

    resolved = _VARIABLE_PATTERN.sub(replace, value)
    if missing:
        names = ", ".join(sorted(missing))
        raise PostmanFeatureError(f"Unresolved Postman variables: {names}; provide --variable")
    return resolved


def _postman_security_scheme(name: str, raw_auth: Any) -> SecurityScheme | None:
    """Normalize supported Postman auth without copying credential values."""
    if not isinstance(raw_auth, dict):
        return None
    auth_type = str(raw_auth.get("type", "")).lower()
    entries = raw_auth.get(auth_type, [])
    values = {
        str(entry.get("key")): str(entry.get("value", ""))
        for entry in entries
        if isinstance(entry, dict)
    }
    if auth_type == "noauth":
        return None
    if auth_type == "bearer":
        hint = _variable_name(values.get("token", ""))
        return SecurityScheme(name, AuthenticationKind.HTTP_BEARER, environment_hint=hint)
    if auth_type == "basic":
        return SecurityScheme(name, AuthenticationKind.HTTP_BASIC)
    if auth_type == "apikey":
        hint = _variable_name(values.get("value", ""))
        return SecurityScheme(
            name,
            AuthenticationKind.API_KEY,
            location=values.get("in", "header"),
            parameter_name=values.get("key", "X-API-Key"),
            environment_hint=hint,
        )
    if auth_type in {"oauth2", "oauth1", "digest", "hawk", "ntlm", "awsv4"}:
        raise PostmanFeatureError(f"Postman authentication type '{auth_type}' is not supported")
    return None


def _variable_name(value: str) -> str | None:
    """Return the variable name when an auth value is one Postman placeholder."""
    match = _VARIABLE_PATTERN.fullmatch(value.strip())
    return match.group(1) if match else None


def _postman_headers(request: dict[str, Any], variables: dict[str, str]) -> tuple[Parameter, ...]:
    """Normalize enabled non-authorization Postman request headers."""
    return tuple(
        Parameter(
            name=str(header.get("key", "header")),
            location="header",
            required=False,
            example=_interpolate_postman(str(header.get("value", "")), variables),
        )
        for header in request.get("header", [])
        if isinstance(header, dict)
        and not header.get("disabled", False)
        and str(header.get("key", "")).lower() != "authorization"
    )


def _has_authorization_header(request: dict[str, Any]) -> bool:
    """Return whether a Postman request carries an enabled Authorization header."""
    return any(
        isinstance(header, dict)
        and not header.get("disabled", False)
        and str(header.get("key", "")).lower() == "authorization"
        for header in request.get("header", [])
    )


def _postman_request_security(
    *,
    index: int,
    item: dict[str, Any],
    request: dict[str, Any],
    collection_scheme: SecurityScheme | None,
    schemes: dict[str, SecurityScheme],
) -> tuple[tuple[str, ...], ...]:
    """Resolve request-level auth or inherit the collection scheme."""
    request_auth = request.get("auth", item.get("auth"))
    security: tuple[tuple[str, ...], ...] = ()
    if isinstance(request_auth, dict) and request_auth.get("type") == "noauth":
        security = ()
    elif request_auth:
        scheme_name = f"postman_request_{index}_auth"
        request_scheme = _postman_security_scheme(scheme_name, request_auth)
        if request_scheme:
            schemes[scheme_name] = request_scheme
            security = ((scheme_name,),)
    elif collection_scheme:
        security = ((collection_scheme.name,),)
    if _has_authorization_header(request) and not security:
        raise PostmanFeatureError(
            "A literal Postman Authorization header cannot be persisted; use collection "
            "or request authentication with an environment variable"
        )
    return security


def parse_postman(document: dict[str, Any], *, variables: dict[str, str] | None = None) -> Contract:
    """Normalize the safe declarative subset of a Postman v2.0/v2.1 collection."""
    _reject_postman_scripts(document)
    resolved_variables = _postman_variables(document, variables)
    operations: list[Operation] = []
    schemes: dict[str, SecurityScheme] = {}
    base_url = ""
    collection_scheme = _postman_security_scheme("postman_collection_auth", document.get("auth"))
    if collection_scheme:
        schemes[collection_scheme.name] = collection_scheme
    for index, item in enumerate(_postman_items(document.get("item", []))):
        request = item.get("request", {})
        if isinstance(request, str):
            request = {"url": request, "method": "GET"}
        raw_url = request.get("url", "")
        if isinstance(raw_url, dict):
            raw_url = raw_url.get("raw", "")
        parsed = urlparse(_interpolate_postman(str(raw_url), resolved_variables))
        if parsed.netloc and not base_url:
            base_url = f"{parsed.scheme}://{parsed.netloc}"
        path = parsed.path or "/"
        query = tuple(
            Parameter(name=key, location="query", required=False, example=value)
            for key, value in parse_qsl(parsed.query)
        )
        body = request.get("body", {})
        if isinstance(body, dict) and body.get("mode") not in {None, "raw"}:
            raise PostmanFeatureError(
                f"Postman body mode '{body.get('mode')}' is not supported; use raw JSON or text"
            )
        raw_body = body.get("raw") if isinstance(body, dict) else None
        body_example: Any | None = None
        if raw_body is not None:
            interpolated_body = _interpolate_postman(str(raw_body), resolved_variables)
            try:
                body_example = json.loads(interpolated_body)
            except ValueError:
                body_example = interpolated_body
        security = _postman_request_security(
            index=index,
            item=item,
            request=request,
            collection_scheme=collection_scheme,
            schemes=schemes,
        )
        status_codes = tuple(
            sorted(
                {
                    int(response["code"])
                    for response in item.get("response", [])
                    if isinstance(response, dict) and str(response.get("code", "")).isdigit()
                }
            )
        )
        success_statuses = tuple(code for code in status_codes if 200 <= code < 300) or (200,)
        responses = tuple(ResponseContract(code) for code in status_codes)
        operations.append(
            Operation(
                identifier=f"postman_{index}_{item.get('name', 'request')}",
                method=str(request.get("method", "GET")).upper(),
                path=path,
                summary=str(item.get("name", f"Request {index + 1}")),
                parameters=(*query, *_postman_headers(request, resolved_variables)),
                request_schema=None,
                request_example=body_example,
                request_required=body_example is not None,
                success_statuses=success_statuses,
                responses=responses,
                security=security,
            )
        )
    return Contract("postman", base_url, tuple(operations), tuple(schemes.values()))


def normalize_contract(
    document: dict[str, Any], *, variables: dict[str, str] | None = None
) -> Contract:
    """Detect and normalize a supported API contract."""
    if "openapi" in document or "swagger" in document:
        return parse_openapi(document)
    schema = str(document.get("info", {}).get("schema", ""))
    if "postman" in schema or "item" in document:
        return parse_postman(document, variables=variables)
    raise ValueError("Unsupported contract: expected OpenAPI/Swagger or Postman Collection")
