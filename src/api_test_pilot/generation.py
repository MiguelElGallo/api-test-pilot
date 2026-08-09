"""Deterministic strategies for functional, negative, and edge scenarios."""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any
from urllib.parse import urljoin, urlparse

from api_test_pilot.contracts import Contract, Operation, Parameter
from api_test_pilot.models import Scenario, ScenarioCategory, ScenarioSuite


def _safe_identifier(value: str) -> str:
    """Convert arbitrary operation identifiers into stable report keys."""
    return re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()


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
        return int(schema.get("maximum" if edge else "minimum", 2**31 - 1 if edge else 1))
    if schema_type == "number":
        return float(schema.get("maximum" if edge else "minimum", 1e6 if edge else 1.0))
    if schema_type == "boolean":
        return not edge
    length = int(schema.get("maxLength" if edge else "minLength", 128 if edge else 1))
    return "x" * min(length, 256)


def _request_parts(
    operation: Operation,
    *,
    omit: Parameter | None = None,
    edge: bool = False,
) -> tuple[str, dict[str, str], dict[str, Any], Any | None]:
    """Build path, headers, query, and body from normalized parameters."""
    path = operation.path
    headers: dict[str, str] = {}
    query: dict[str, Any] = {}
    for parameter in operation.parameters:
        if parameter == omit:
            continue
        value = _parameter_value(parameter, edge=edge)
        if parameter.location == "path":
            path = path.replace(f"{{{parameter.name}}}", str(value))
        elif parameter.location == "header":
            headers[parameter.name] = str(value)
        elif parameter.location == "query":
            query[parameter.name] = value
    body = deepcopy(operation.request_example)
    if omit and omit.location == "body":
        body = None
    return path, headers, query, body


def _scenario(
    operation: Operation,
    category: ScenarioCategory,
    suffix: str,
    *,
    omit: Parameter | None = None,
    edge: bool = False,
    expected_statuses: list[int] | None = None,
) -> Scenario:
    """Construct one scenario with a stable identifier."""
    path, headers, query, body = _request_parts(operation, omit=omit, edge=edge)
    return Scenario(
        identifier=f"{_safe_identifier(operation.identifier)}-{category.value}-{suffix}",
        name=f"{operation.summary} [{category.value}: {suffix}]",
        category=category,
        method=operation.method,
        path=path,
        headers=headers,
        query=query,
        body=body,
        expected_statuses=expected_statuses or list(operation.success_statuses),
        description=_description(category, omit=omit, edge=edge),
    )


def _description(
    category: ScenarioCategory,
    *,
    omit: Parameter | None,
    edge: bool,
) -> str:
    """Explain the behavior exercised by a generated scenario."""
    if omit:
        return f"Rejects a request missing required {omit.location} parameter '{omit.name}'."
    if edge:
        return "Exercises documented maximum, last-enum, or high-cardinality boundary values."
    return f"Exercises the documented happy path as a {category.value} regression check."


def generate_suite(
    contract: Contract, *, source: str, base_url: str | None = None
) -> ScenarioSuite:
    """Generate functional, negative, and edge scenarios for every operation."""
    scenarios: list[Scenario] = []
    for operation in contract.operations:
        scenarios.append(_scenario(operation, ScenarioCategory.FUNCTIONAL, "happy-path"))
        required = next(
            (parameter for parameter in operation.parameters if parameter.required), None
        )
        if required:
            scenarios.append(
                _scenario(
                    operation,
                    ScenarioCategory.NEGATIVE,
                    f"missing-{_safe_identifier(required.name)}",
                    omit=required,
                    expected_statuses=[400, 401, 403, 404, 409, 415, 422],
                )
            )
        elif operation.request_schema is not None:
            scenarios.append(
                _scenario(
                    operation,
                    ScenarioCategory.NEGATIVE,
                    "missing-request-body",
                    expected_statuses=[400, 401, 403, 409, 415, 422],
                ).model_copy(update={"body": None})
            )
        else:
            invalid = _scenario(
                operation,
                ScenarioCategory.NEGATIVE,
                "unknown-resource",
                expected_statuses=[404, 405],
            )
            scenarios.append(invalid.model_copy(update={"path": f"{invalid.path}/__invalid__"}))
        scenarios.append(_scenario(operation, ScenarioCategory.EDGE, "boundary-values", edge=True))
    chosen_base_url = base_url or contract.base_url
    if not chosen_base_url:
        raise ValueError("A base URL is required when the contract does not define one")
    if not urlparse(chosen_base_url).scheme and urlparse(source).scheme in {"http", "https"}:
        chosen_base_url = urljoin(source, chosen_base_url)
    return ScenarioSuite(source=source, base_url=chosen_base_url.rstrip("/"), scenarios=scenarios)
