"""Tests for project configuration and GitHub Actions scaffolding."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from api_test_pilot.cli import app
from api_test_pilot.configuration import (
    ProjectConfiguration,
    TargetConfiguration,
    load_project_configuration,
    parse_variable_assignments,
    write_project_configuration,
)
from api_test_pilot.workflow import render_workflow, write_workflow


def _secured_spec(path: Path) -> None:
    """Write a minimal authenticated OpenAPI target for scaffold tests."""
    document = {
        "openapi": "3.1.0",
        "servers": [{"url": "https://staging.example.test"}],
        "security": [{"BearerAuth": []}],
        "components": {"securitySchemes": {"BearerAuth": {"type": "http", "scheme": "bearer"}}},
        "paths": {
            "/health": {
                "get": {
                    "responses": {
                        "200": {
                            "description": "ok",
                            "content": {"application/json": {"schema": {"type": "object"}}},
                        }
                    }
                }
            }
        },
    }
    path.write_text(yaml.safe_dump(document), encoding="utf-8")


def test_init_scaffolds_shared_local_and_actions_configuration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One target selection should create config, suite, and target-independent Actions."""
    monkeypatch.chdir(tmp_path)
    spec = tmp_path / "openapi.yaml"
    _secured_spec(spec)

    result = CliRunner().invoke(app, ["init", "--spec", str(spec)])

    assert result.exit_code == 0, result.output
    configuration = load_project_configuration(Path(".api-test-pilot/config.yaml"))
    suite = yaml.safe_load(Path("generated-scenarios.yaml").read_text(encoding="utf-8"))
    workflow = Path(".github/workflows/api-regression.yml").read_text(encoding="utf-8")
    assert configuration.target.specification == str(spec)
    assert configuration.execution.allowed_methods == ["GET", "HEAD", "OPTIONS"]
    assert configuration.authentication == {"BearerAuth": "API_TEST_AUTH_BEARERAUTH"}
    assert len(suite["scenarios"]) == 3
    assert "api-test-pilot generate --config .api-test-pilot/config.yaml" in workflow
    assert "secrets.API_TEST_AUTH_BEARERAUTH" in workflow
    assert "example_api" not in workflow
    regression_block = workflow.split("- name: Execute regression", 1)[1].split(
        "- name: Analyze failures", 1
    )[0]
    assert "GITHUB_TOKEN" not in regression_block


def test_generate_from_project_configuration_uses_configured_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Configured generation should use the persisted target and suite destination."""
    monkeypatch.chdir(tmp_path)
    spec = tmp_path / "openapi.yaml"
    _secured_spec(spec)
    configuration = ProjectConfiguration(target=TargetConfiguration(specification=str(spec)))
    config_path = tmp_path / "project.yaml"
    write_project_configuration(configuration, config_path, overwrite=False)

    result = CliRunner().invoke(app, ["generate", "--config", str(config_path)])

    assert result.exit_code == 0, result.output
    assert Path("generated-scenarios.yaml").exists()


def test_init_refuses_partial_overwrite_without_force(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Existing scaffold outputs should block initialization before any file changes."""
    monkeypatch.chdir(tmp_path)
    spec = tmp_path / "openapi.yaml"
    _secured_spec(spec)
    workflow = Path(".github/workflows/api-regression.yml")
    workflow.parent.mkdir(parents=True)
    workflow.write_text("owned by user\n", encoding="utf-8")

    result = CliRunner().invoke(app, ["init", "--spec", str(spec)])

    assert result.exit_code != 0
    assert workflow.read_text(encoding="utf-8") == "owned by user\n"
    assert not Path(".api-test-pilot/config.yaml").exists()


def test_configuration_and_workflow_writers_protect_existing_files(tmp_path: Path) -> None:
    """Low-level writers should also require explicit overwrite authorization."""
    configuration = ProjectConfiguration(
        target=TargetConfiguration(specification="https://example.test/openapi.json")
    )
    config_path = tmp_path / "config.yaml"
    workflow_path = tmp_path / "workflow.yml"
    write_project_configuration(configuration, config_path, overwrite=False)
    write_workflow(
        configuration,
        workflow_path,
        config_path=config_path,
        overwrite=False,
    )

    with pytest.raises(FileExistsError, match="Configuration already exists"):
        write_project_configuration(configuration, config_path, overwrite=False)
    with pytest.raises(FileExistsError, match="Workflow already exists"):
        write_workflow(
            configuration,
            workflow_path,
            config_path=config_path,
            overwrite=False,
        )
    assert "GITHUB_TOKEN" in render_workflow(configuration, config_path=config_path)


def test_variable_assignment_parser_is_strict() -> None:
    """Postman variable options should accept values with equals signs and reject typos."""
    assert parse_variable_assignments(["token=a=b", "stage=test"]) == {
        "token": "a=b",
        "stage": "test",
    }
    with pytest.raises(ValueError, match="expected NAME=VALUE"):
        parse_variable_assignments(["missing-separator"])
