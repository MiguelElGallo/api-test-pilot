"""Deterministic strategies for functional, negative, and edge scenarios."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from copy import deepcopy
from typing import Any
from urllib.parse import urljoin, urlparse

from api_test_pilot.contracts import Contract, Operation, Parameter, ResponseContract
from api_test_pilot.models import (
    SAFE_HTTP_METHODS,
    AuthenticationScheme,
    ExecutionPolicy,
    ExpectedResponse,
    Scenario,
    ScenarioCategory,
    ScenarioSuite,
)


def _safe_identifier(value: str) -> str:
    """Convert arbitrary operation identifiers into stable report keys."""
    return re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()


def _environment_name(value: str) -> str:
    """Create a conventional secret environment variable from a scheme name."""
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_").upper()
    return f"API_TEST_AUTH_{normalized or 'TOKEN'}"


def _parameter_value(parameter: Parameter, *, edge: bool = False) -> Any:
    """Produce a representative or boundary value for one parameter."""
    schema = parameter.schema
    if parameter.example is not None and not edge:
        return parameter.example
    choices = schema.get("enum")
    if isinstance(choices, list) and choices:
        return choices[-1] if edge else choices[0]
    schema_type = schema.get("type", "string")
    if schema_type == "integer":
        key = "maximum" if edge else "minimum"
        return int(schema.get(key, 2**31 - 1 if edge else 1))
    if schema_type == "number":
        key = "maximum" if edge else "minimum"
        return float(schema.get(key, 1e6 if edge else 1.0))
    if schema_type == "boolean":
        return not edge
    if schema.get("format") == "email":
        return "boundary@example.com" if edge else "test@example.com"
    key = "maxLength" if edge else "minLength"
    length = int(schema.get(key, 128 if edge else 1))
    return "x" * min(max(length, 1), 256)


def _schema_value(  # noqa: PLR0912 - each JSON Schema type has a distinct boundary strategy.
    schema: dict[str, Any], *, edge: bool
) -> Any:
    """Generate a valid representative or boundary value from a dereferenced schema."""
    if not isinstance(schema, dict):
        return None
    if not edge:
        if "example" in schema:
            return deepcopy(schema["example"])
        examples = schema.get("examples")
        if isinstance(examples, list) and examples:
            return deepcopy(examples[0])
        if "default" in schema:
            return deepcopy(schema["default"])
    choices = schema.get("enum")
    if isinstance(choices, list) and choices:
        return deepcopy(choices[-1] if edge else choices[0])
    for composition in ("oneOf", "anyOf"):
        branches = schema.get(composition)
        if isinstance(branches, list) and branches:
            return _schema_value(branches[-1] if edge else branches[0], edge=edge)
    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        concrete_types = [item for item in schema_type if item != "null"]
        schema_type = concrete_types[0] if concrete_types else "null"
    if schema_type == "object" or "properties" in schema:
        properties = schema.get("properties", {})
        required = set(schema.get("required", []))
        selected = (
            properties
            if edge
            else {
                name: value
                for name, value in properties.items()
                if name in required
                or "example" in value
                or "examples" in value
                or "default" in value
            }
        )
        return {name: _schema_value(value, edge=edge) for name, value in selected.items()}
    if schema_type == "array":
        lower = int(schema.get("minItems", 1))
        upper = int(schema.get("maxItems", max(lower, 5)))
        count = min(upper if edge else lower, 20)
        return [_schema_value(schema.get("items", {}), edge=edge) for _ in range(count)]
    if schema_type == "integer":
        if edge and "maximum" in schema:
            return int(schema["maximum"])
        if edge and "exclusiveMaximum" in schema:
            return int(schema["exclusiveMaximum"]) - 1
        if "minimum" in schema:
            return int(schema["minimum"])
        return 2**31 - 1 if edge else 1
    if schema_type == "number":
        if edge and "maximum" in schema:
            return float(schema["maximum"])
        if edge and "exclusiveMaximum" in schema:
            return float(schema["exclusiveMaximum"]) - 0.01
        if "minimum" in schema:
            return float(schema["minimum"])
        return 1e6 if edge else 1.0
    if schema_type == "boolean":
        return not edge
    if schema_type == "null":
        return None
    if schema.get("format") == "email":
        return "boundary@example.com" if edge else "test@example.com"
    length_key = "maxLength" if edge else "minLength"
    length = int(schema.get(length_key, 128 if edge else 1))
    return "x" * min(max(length, 1), 256)


def _invalid_parameter_value(parameter: Parameter) -> Any:
    """Create a deliberately schema-incompatible value for a required path parameter."""
    schema_type = parameter.schema.get("type", "string")
    if schema_type in {"integer", "number", "boolean"}:
        return "not-a-valid-value"
    maximum = parameter.schema.get("maxLength")
    if isinstance(maximum, int):
        return "x" * min(maximum + 1, 257)
    choices = parameter.schema.get("enum")
    if isinstance(choices, list):
        return "not-in-enum"
    return "__invalid__"


def _request_parts(
    operation: Operation,
    *,
    omit: Parameter | None = None,
    invalid: Parameter | None = None,
    edge: bool = False,
) -> tuple[str, dict[str, str], dict[str, Any], Any | None]:
    """Build path, headers, query, and body from normalized parameters."""
    path = operation.path
    headers: dict[str, str] = {}
    query: dict[str, Any] = {}
    for parameter in operation.parameters:
        if parameter == omit:
            continue
        value = (
            _invalid_parameter_value(parameter)
            if parameter == invalid
            else _parameter_value(parameter, edge=edge)
        )
        if parameter.location == "path":
            path = path.replace(f"{{{parameter.name}}}", str(value))
        elif parameter.location == "header":
            headers[parameter.name] = str(value)
        elif parameter.location == "query":
            query[parameter.name] = value
    if operation.request_schema is not None:
        body = _schema_value(operation.request_schema, edge=edge)
        if not edge and operation.request_example is not None:
            body = deepcopy(operation.request_example)
    else:
        body = deepcopy(operation.request_example)
    return path, headers, query, body


def _expected_response(response: ResponseContract) -> ExpectedResponse:
    """Convert a normalized response into a serializable suite assertion."""
    return ExpectedResponse(
        status_code=response.status_code,
        media_type=response.media_type,
        response_schema=deepcopy(response.schema),
        headers=list(response.headers),
    )


def _response_assertions(
    operation: Operation, expected_statuses: Iterable[int]
) -> list[ExpectedResponse]:
    """Select contract assertions for the statuses accepted by one scenario."""
    statuses = set(expected_statuses)
    return [
        _expected_response(response)
        for response in operation.responses
        if response.status_code in statuses
    ]


def _negative_statuses(operation: Operation, *, path_parameter: bool = False) -> list[int]:
    """Choose narrow documented client errors for malformed or missing input."""
    preferred = (400, 404, 422) if path_parameter else (400, 422)
    documented = {
        response.status_code
        for response in operation.responses
        if 400 <= response.status_code < 500 and response.status_code not in {401, 403}
    }
    selected = [status for status in preferred if status in documented]
    if selected:
        return selected
    if documented:
        return [min(documented)]
    return list(preferred)


def _scenario(
    operation: Operation,
    category: ScenarioCategory,
    suffix: str,
    *,
    omit: Parameter | None = None,
    invalid: Parameter | None = None,
    edge: bool = False,
    expected_statuses: list[int] | None = None,
) -> Scenario:
    """Construct one scenario with stable identifiers and response assertions."""
    path, headers, query, body = _request_parts(operation, omit=omit, invalid=invalid, edge=edge)
    statuses = expected_statuses or list(operation.success_statuses)
    return Scenario(
        identifier=f"{_safe_identifier(operation.identifier)}-{category.value}-{suffix}",
        name=f"{operation.summary} [{category.value}: {suffix}]",
        category=category,
        method=operation.method,
        path=path,
        headers=headers,
        query=query,
        body=body,
        expected_statuses=statuses,
        expected_responses=_response_assertions(operation, statuses),
        security=[list(requirement) for requirement in operation.security],
        description=_description(category, omit=omit, invalid=invalid, edge=edge),
    )


def _description(
    category: ScenarioCategory,
    *,
    omit: Parameter | None,
    invalid: Parameter | None,
    edge: bool,
) -> str:
    """Explain the behavior exercised by a generated scenario."""
    if invalid:
        return f"Rejects an invalid required path parameter '{invalid.name}'."
    if omit:
        return f"Rejects a request missing required {omit.location} parameter '{omit.name}'."
    if edge:
        return "Exercises documented schema boundaries with resource-safe generation caps."
    return f"Exercises the documented happy path as a {category.value} regression check."


def _negative_scenario(operation: Operation) -> Scenario:
    """Generate one focused negative scenario for an operation."""
    required = next((parameter for parameter in operation.parameters if parameter.required), None)
    if required and required.location == "path":
        statuses = _negative_statuses(operation, path_parameter=True)
        return _scenario(
            operation,
            ScenarioCategory.NEGATIVE,
            f"invalid-{_safe_identifier(required.name)}",
            invalid=required,
            expected_statuses=statuses,
        )
    if required:
        statuses = _negative_statuses(operation)
        return _scenario(
            operation,
            ScenarioCategory.NEGATIVE,
            f"missing-{_safe_identifier(required.name)}",
            omit=required,
            expected_statuses=statuses,
        )
    if operation.request_schema is not None or operation.request_required:
        statuses = _negative_statuses(operation)
        scenario = _scenario(
            operation,
            ScenarioCategory.NEGATIVE,
            "missing-request-body",
            expected_statuses=statuses,
        )
        return scenario.model_copy(update={"body": None})
    scenario = _scenario(
        operation,
        ScenarioCategory.NEGATIVE,
        "unknown-resource",
        expected_statuses=[404],
    )
    return scenario.model_copy(update={"path": f"{scenario.path.rstrip('/')}/__invalid__"})


def generate_suite(
    contract: Contract,
    *,
    source: str,
    base_url: str | None = None,
    allowed_methods: Iterable[str] | None = None,
    authentication_environment: Mapping[str, str] | None = None,
) -> ScenarioSuite:
    """Generate safe functional, negative, and edge scenarios for allowed operations."""
    policy = ExecutionPolicy(
        allowed_methods=list(allowed_methods)
        if allowed_methods is not None
        else list(SAFE_HTTP_METHODS)
    )
    allowed = set(policy.allowed_methods)
    operations = [operation for operation in contract.operations if operation.method in allowed]
    if not operations:
        available = ", ".join(sorted({operation.method for operation in contract.operations}))
        raise ValueError(
            f"No operations match allowed methods {sorted(allowed)}; contract methods: {available}"
        )
    scenarios: list[Scenario] = []
    for operation in operations:
        scenarios.extend(
            [
                _scenario(operation, ScenarioCategory.FUNCTIONAL, "happy-path"),
                _negative_scenario(operation),
                _scenario(
                    operation,
                    ScenarioCategory.EDGE,
                    "boundary-values",
                    edge=True,
                ),
            ]
        )
    chosen_base_url = base_url or contract.base_url
    if not chosen_base_url:
        raise ValueError("A base URL is required when the contract does not define one")
    if not urlparse(chosen_base_url).scheme and urlparse(source).scheme in {"http", "https"}:
        chosen_base_url = urljoin(source, chosen_base_url)
    configured_environment = authentication_environment or {}
    authentication = {
        scheme.name: AuthenticationScheme(
            kind=scheme.kind,
            environment_variable=configured_environment.get(
                scheme.name,
                _environment_name(scheme.environment_hint or scheme.name),
            ),
            location=scheme.location,
            parameter_name=scheme.parameter_name,
        )
        for scheme in contract.security_schemes
    }
    return ScenarioSuite(
        source=source,
        base_url=chosen_base_url.rstrip("/"),
        execution=policy,
        authentication=authentication,
        scenarios=scenarios,
    )
