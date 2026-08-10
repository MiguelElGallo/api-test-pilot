"""Small JSON Schema helpers shared by contract normalization and generation."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


def _allows_object(schema: dict[str, Any]) -> bool:
    """Return whether a schema branch can apply to an object instance."""
    schema_type = schema.get("type")
    if schema_type is None:
        return True
    if isinstance(schema_type, str):
        return schema_type == "object"
    return isinstance(schema_type, list) and "object" in schema_type


def external_schema_references(value: Any) -> tuple[str, ...]:
    """Return external ``$ref`` values that cannot be embedded in a generated suite."""
    references: set[str] = set()

    def visit(candidate: Any) -> None:
        """Collect references recursively without resolving or fetching any document."""
        if isinstance(candidate, list):
            for item in candidate:
                visit(item)
        elif isinstance(candidate, dict):
            reference = candidate.get("$ref")
            if isinstance(reference, str) and not reference.startswith("#/"):
                references.add(reference)
            for item in candidate.values():
                visit(item)

    visit(value)
    return tuple(sorted(references))


def _object_all_of_fragments(schema: dict[str, Any]) -> list[dict[str, Any]] | None:
    """Flatten object-compatible ``allOf`` branches without synthesizing other schemas."""
    if not _allows_object(schema):
        return None
    branches = schema.get("allOf")
    own_constraints = {key: value for key, value in schema.items() if key != "allOf"}
    if not isinstance(branches, list):
        return [own_constraints] if own_constraints else []

    fragments = [own_constraints] if own_constraints else []
    for branch in branches:
        if not isinstance(branch, dict):
            return None
        nested_fragments = _object_all_of_fragments(branch)
        if nested_fragments is None:
            return None
        fragments.extend(nested_fragments)
    return fragments


def merged_all_of_object_schema(schema: dict[str, Any]) -> dict[str, Any] | None:
    """Merge common object ``allOf`` branches for deterministic value generation.

    The original schema remains the source of truth for validation. This helper only
    combines object properties and required fields so a generated request includes
    constraints inherited through composition. Conflicting constraints remain nested
    under ``allOf`` on the affected property and are caught by schema validation.
    """
    branches = schema.get("allOf")
    if not isinstance(branches, list) or not branches:
        return None

    fragments = _object_all_of_fragments(schema)
    if fragments is None:
        return None

    properties: dict[str, Any] = {}
    required: set[str] = set()
    for fragment in fragments:
        required.update(str(name) for name in fragment.get("required", []) if isinstance(name, str))
        for name, property_schema in fragment.get("properties", {}).items():
            if not isinstance(property_schema, dict):
                continue
            if name in properties:
                properties[name] = {"allOf": [properties[name], deepcopy(property_schema)]}
            else:
                properties[name] = deepcopy(property_schema)

    return {
        "type": "object",
        "properties": properties,
        "required": sorted(required),
    }
