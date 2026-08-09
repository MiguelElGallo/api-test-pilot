"""Command-line workflow tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from typer.testing import CliRunner

from api_test_pilot.cli import app


def test_generate_command_writes_suite(
    tmp_path: Path,
    openapi_document: dict[str, Any],
) -> None:
    """The CLI should turn a local OpenAPI contract into a YAML suite."""
    spec = tmp_path / "openapi.yaml"
    output = tmp_path / "suite.yaml"
    spec.write_text(yaml.safe_dump(openapi_document), encoding="utf-8")

    result = CliRunner().invoke(
        app,
        ["generate", "--spec", str(spec), "--output", str(output)],
    )

    assert result.exit_code == 0
    assert "Generated 6 scenarios" in result.stdout
    assert len(yaml.safe_load(output.read_text(encoding="utf-8"))["scenarios"]) == 6
