"""Load supported contract formats from local files or HTTPS URLs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
import yaml


class ContractLoadError(ValueError):
    """Indicate that a contract could not be retrieved or parsed."""


def _parse_document(raw: str, source: str) -> dict[str, Any]:
    """Parse JSON first and YAML second, returning a mapping document."""
    try:
        document = json.loads(raw)
    except json.JSONDecodeError:
        try:
            document = yaml.safe_load(raw)
        except yaml.YAMLError as exc:
            raise ContractLoadError(f"Invalid JSON or YAML in {source}: {exc}") from exc
    if not isinstance(document, dict):
        raise ContractLoadError(f"Contract root in {source} must be an object")
    return document


def load_contract(source: str, *, timeout: float = 20.0) -> dict[str, Any]:
    """Load an OpenAPI or Postman document from an HTTPS URL or local path."""
    parsed = urlparse(source)
    if parsed.scheme in {"http", "https"}:
        try:
            response = httpx.get(source, timeout=timeout, follow_redirects=True)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ContractLoadError(f"Unable to retrieve {source}: {exc}") from exc
        return _parse_document(response.text, source)

    path = Path(source).expanduser()
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ContractLoadError(f"Unable to read {path}: {exc}") from exc
    return _parse_document(raw, str(path))
