"""Load supported contract formats from local files or HTTPS URLs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
import yaml


class ContractLoadError(ValueError):
    """Indicate that a contract could not be retrieved or parsed."""


_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_MAX_REDIRECTS = 5


def _origin(url: str) -> tuple[str, str, int | None]:
    """Return a normalized HTTP origin for redirect comparison."""
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    default_port = 443 if scheme == "https" else 80 if scheme == "http" else None
    try:
        port = parsed.port or default_port
    except ValueError as exc:
        raise ContractLoadError(f"Invalid contract URL port in {url}") from exc
    return scheme, (parsed.hostname or "").lower(), port


def _load_remote_contract(source: str, *, timeout: float) -> dict[str, Any]:
    """Retrieve a contract while confining every redirect to its initial origin."""
    initial_origin = _origin(source)
    current_url = source
    for redirect_count in range(_MAX_REDIRECTS + 1):
        try:
            response = httpx.get(current_url, timeout=timeout, follow_redirects=False)
        except httpx.HTTPError as exc:
            raise ContractLoadError(f"Unable to retrieve {current_url}: {exc}") from exc
        location = response.headers.get("location")
        if response.status_code in _REDIRECT_STATUSES and location:
            if redirect_count == _MAX_REDIRECTS:
                raise ContractLoadError(f"Too many redirects while retrieving {source}")
            redirected_url = urljoin(current_url, location)
            if _origin(redirected_url) != initial_origin:
                raise ContractLoadError(
                    f"Refusing cross-origin redirect from {current_url} to {redirected_url}"
                )
            current_url = redirected_url
            continue
        try:
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ContractLoadError(f"Unable to retrieve {current_url}: {exc}") from exc
        return _parse_document(response.text, current_url)
    raise AssertionError("Redirect loop must return or raise")


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
    """Load an OpenAPI or Postman document from an HTTP(S) URL or local path."""
    parsed = urlparse(source)
    if parsed.scheme in {"http", "https"}:
        return _load_remote_contract(source, timeout=timeout)

    path = Path(source).expanduser()
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ContractLoadError(f"Unable to read {path}: {exc}") from exc
    return _parse_document(raw, str(path))
