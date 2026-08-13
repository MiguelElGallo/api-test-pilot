"""Tests for local and remote specification loading."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from api_test_pilot.loaders.factory import ContractLoadError, load_contract


def test_loads_yaml_file(tmp_path: Path) -> None:
    """YAML paths should produce mapping documents."""
    source = tmp_path / "openapi.yaml"
    source.write_text("openapi: 3.1.0\ninfo:\n  title: Fixture\n", encoding="utf-8")

    assert load_contract(str(source))["openapi"] == "3.1.0"


def test_rejects_non_mapping_document(tmp_path: Path) -> None:
    """A sequence root is invalid for all supported contract formats."""
    source = tmp_path / "invalid.yaml"
    source.write_text("- one\n- two\n", encoding="utf-8")

    with pytest.raises(ContractLoadError, match="must be an object"):
        load_contract(str(source))


def test_wraps_remote_transport_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Transport errors should be reported as contract-loading failures."""

    def fail(*_args: object, **_kwargs: object) -> None:
        """Simulate an unavailable specification endpoint."""
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(httpx, "get", fail)
    with pytest.raises(ContractLoadError, match="Unable to retrieve"):
        load_contract("https://example.test/openapi.json")


def test_remote_contract_allows_only_same_origin_redirects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Legitimate same-origin moves should work without permitting an origin pivot."""
    requested: list[str] = []

    def get(url: str, **_kwargs: object) -> httpx.Response:
        requested.append(url)
        if url == "https://example.test/openapi.json":
            return httpx.Response(
                302,
                headers={"Location": "/v2/openapi.json"},
                request=httpx.Request("GET", url),
            )
        return httpx.Response(
            200,
            json={"openapi": "3.1.0"},
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(httpx, "get", get)

    assert load_contract("https://example.test/openapi.json")["openapi"] == "3.1.0"
    assert requested == [
        "https://example.test/openapi.json",
        "https://example.test/v2/openapi.json",
    ]


def test_remote_contract_rejects_cross_origin_redirect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A contract host must not pivot retrieval into another network origin."""
    monkeypatch.setattr(
        httpx,
        "get",
        lambda *_args, **_kwargs: httpx.Response(
            302,
            headers={"Location": "http://127.0.0.1/latest/meta-data"},
        ),
    )

    with pytest.raises(ContractLoadError, match="cross-origin redirect"):
        load_contract("https://example.test/openapi.json")
