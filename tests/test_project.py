"""Tests for project configuration and GitHub Actions scaffolding."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

import api_test_pilot.cli as cli_module
from api_test_pilot.cli import app
from api_test_pilot.configuration import (
    ArtifactConfiguration,
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
    regression_block = workflow.split("  regression:\n", 1)[1].split("  ai-advice:\n", 1)[0]
    ai_block = workflow.split("  ai-advice:\n", 1)[1]
    root_permissions = workflow.split("concurrency:", 1)[0]
    assert "GitHub Copilot" not in regression_block
    assert "copilot-requests" not in root_permissions
    assert "needs: regression" in ai_block
    assert "continue-on-error: true" in ai_block
    assert "copilot-requests: write" in ai_block
    assert "analyze_failures:" in workflow
    assert "default: false" in workflow
    analysis_block = ai_block.split("- name: Analyze failures with GitHub Copilot", 1)[1].split(
        "- name: Upload AI advice and analysis", 1
    )[0]
    assert "inputs.analyze_failures" in analysis_block
    assert "vars.API_TEST_PILOT_AI_FAILURE_ANALYSIS == 'true'" in analysis_block


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


def test_init_rejects_relative_and_absolute_aliases_for_the_same_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Lexically different paths resolving to one file must not bypass collision checks."""
    monkeypatch.chdir(tmp_path)
    spec = tmp_path / "openapi.yaml"
    _secured_spec(spec)
    shared_output = tmp_path / "shared.yaml"

    result = CliRunner().invoke(
        app,
        [
            "init",
            "--spec",
            str(spec),
            "--config",
            "shared.yaml",
            "--suite",
            str(shared_output),
        ],
    )

    assert result.exit_code != 0
    assert "destinations must be" in result.output
    assert "distinct" in result.output
    assert not shared_output.exists()
    assert not Path(".github/workflows/api-regression.yml").exists()


def test_init_rolls_back_new_outputs_when_a_replacement_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed scaffold replacement should not leave a partially initialized project."""
    monkeypatch.chdir(tmp_path)
    spec = tmp_path / "openapi.yaml"
    _secured_spec(spec)
    original_replace = cli_module._replace_file  # noqa: SLF001 - inject a commit failure.

    def fail_suite_replacement(source: Path, destination: Path) -> None:
        """Raise while committing the second scaffold file after configuration succeeds."""
        if destination == Path("generated-scenarios.yaml"):
            raise OSError("simulated suite replacement failure")
        original_replace(source, destination)

    monkeypatch.setattr(cli_module, "_replace_file", fail_suite_replacement)

    result = CliRunner().invoke(app, ["init", "--spec", str(spec)])

    assert result.exit_code != 0
    assert not Path(".api-test-pilot/config.yaml").exists()
    assert not Path("generated-scenarios.yaml").exists()
    assert not Path(".github/workflows/api-regression.yml").exists()


def test_init_force_restores_existing_outputs_when_a_replacement_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Forced initialization must restore every prior file when a later write fails."""
    monkeypatch.chdir(tmp_path)
    spec = tmp_path / "openapi.yaml"
    _secured_spec(spec)
    prior_outputs = {
        Path(".api-test-pilot/config.yaml"): "previous configuration\n",
        Path("generated-scenarios.yaml"): "previous suite\n",
        Path(".github/workflows/api-regression.yml"): "previous workflow\n",
    }
    for path, content in prior_outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    original_replace = cli_module._replace_file  # noqa: SLF001 - inject a commit failure.

    def fail_suite_replacement(source: Path, destination: Path) -> None:
        """Raise after the first forced replacement to exercise rollback restoration."""
        if destination == Path("generated-scenarios.yaml"):
            raise OSError("simulated suite replacement failure")
        original_replace(source, destination)

    monkeypatch.setattr(cli_module, "_replace_file", fail_suite_replacement)

    result = CliRunner().invoke(app, ["init", "--spec", str(spec), "--force"])

    assert result.exit_code != 0
    for path, content in prior_outputs.items():
        assert path.read_text(encoding="utf-8") == content


def test_init_rollback_attempts_every_restore_and_preserves_the_commit_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One failed rollback should not hide the commit error or skip remaining restorations."""
    monkeypatch.chdir(tmp_path)
    spec = tmp_path / "openapi.yaml"
    _secured_spec(spec)
    config_path = Path(".api-test-pilot/config.yaml")
    suite_path = Path("generated-scenarios.yaml")
    workflow_path = Path(".github/workflows/api-regression.yml")
    prior_outputs = {
        config_path: "previous configuration\n",
        suite_path: "previous suite\n",
        workflow_path: "previous workflow\n",
    }
    for path, content in prior_outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    original_replace = cli_module._replace_file  # noqa: SLF001 - inject failures.
    suite_replacements = 0
    failed_suite_restore_backup: Path | None = None

    def fail_commit_and_one_restore(source: Path, destination: Path) -> None:
        """Fail the final commit and the first rollback while allowing later restoration."""
        nonlocal failed_suite_restore_backup, suite_replacements
        if destination == workflow_path:
            raise OSError("simulated workflow commit failure")
        if destination == suite_path:
            suite_replacements += 1
            if suite_replacements == 2:
                failed_suite_restore_backup = source
                raise OSError("simulated suite rollback failure")
        original_replace(source, destination)

    monkeypatch.setattr(cli_module, "_replace_file", fail_commit_and_one_restore)

    result = CliRunner().invoke(app, ["init", "--spec", str(spec), "--force"])

    assert result.exit_code != 0
    assert isinstance(result.exception, OSError)
    assert str(result.exception) == "simulated workflow commit failure"
    assert failed_suite_restore_backup is not None
    assert result.exception.__notes__ == [
        (
            "Scaffold rollback also encountered: failed to restore overwritten destination "
            f"{suite_path.resolve(strict=False)} from preserved recovery backup "
            f"{failed_suite_restore_backup.resolve(strict=False)}: simulated suite rollback failure"
        )
    ]
    assert failed_suite_restore_backup.exists()
    assert failed_suite_restore_backup.read_bytes() == b"previous suite\n"
    assert config_path.read_text(encoding="utf-8") == prior_outputs[config_path]
    assert workflow_path.read_text(encoding="utf-8") == prior_outputs[workflow_path]


def test_configuration_and_workflow_writers_protect_existing_files(tmp_path: Path) -> None:
    """Low-level writers should also require explicit overwrite authorization."""
    configuration = ProjectConfiguration(
        target=TargetConfiguration(specification="https://example.test/openapi.json")
    )
    config_path = tmp_path / "config.yaml"
    workflow_config_path = Path("config.yaml")
    workflow_path = tmp_path / "workflow.yml"
    write_project_configuration(configuration, config_path, overwrite=False)
    write_workflow(
        configuration,
        workflow_path,
        config_path=workflow_config_path,
        overwrite=False,
    )

    with pytest.raises(FileExistsError, match="Configuration already exists"):
        write_project_configuration(configuration, config_path, overwrite=False)
    with pytest.raises(FileExistsError, match="Workflow already exists"):
        write_workflow(
            configuration,
            workflow_path,
            config_path=workflow_config_path,
            overwrite=False,
        )
    workflow = render_workflow(configuration, config_path=workflow_config_path)
    assert "GITHUB_TOKEN" in workflow
    assert "actions/download-artifact@v8" in workflow


def test_workflow_rejects_unsafe_authentication_environment_names() -> None:
    """Generated Actions syntax should reject auth names that could alter YAML expressions."""
    configuration = ProjectConfiguration(
        target=TargetConfiguration(specification="https://example.test/openapi.json"),
        authentication={"BearerAuth": "TOKEN: ${{ secrets.OTHER }}"},
    )

    with pytest.raises(ValueError, match="valid identifiers"):
        render_workflow(configuration, config_path=Path("config.yaml"))


def test_workflow_rejects_newline_step_injection_from_artifact_path() -> None:
    """Artifact paths must not be able to add YAML steps to a generated workflow."""
    configuration = ProjectConfiguration(
        target=TargetConfiguration(specification="https://example.test/openapi.json"),
        artifacts=ArtifactConfiguration(
            suite="suite.yaml\n      - name: Injected step\n        run: echo unsafe",
            reports="reports",
        ),
    )

    with pytest.raises(ValueError, match=r"artifacts\.suite"):
        render_workflow(configuration, config_path=Path("config.yaml"))


@pytest.mark.parametrize(
    "config_path",
    [
        Path("../config.yaml"),
        Path("/outside/config.yaml"),
        Path("config-${{ github.token }}.yaml"),
    ],
)
def test_workflow_rejects_unsafe_configuration_paths(config_path: Path) -> None:
    """The generated CLI commands must not accept unsafe configuration path interpolation."""
    configuration = ProjectConfiguration(
        target=TargetConfiguration(specification="https://example.test/openapi.json")
    )

    with pytest.raises(ValueError, match="config_path"):
        render_workflow(configuration, config_path=config_path)


@pytest.mark.parametrize(
    "reports",
    [
        "../private-reports",
        "/outside/private-reports",
        "reports/${{ github.token }}",
        "reports/'broken-expression",
        "reports/\x01private",
    ],
)
def test_workflow_rejects_unsafe_report_paths(reports: str) -> None:
    """Report paths must remain inside the project and inert in YAML and expressions."""
    configuration = ProjectConfiguration(
        target=TargetConfiguration(specification="https://example.test/openapi.json"),
        artifacts=ArtifactConfiguration(suite="suite.yaml", reports=reports),
    )

    with pytest.raises(ValueError, match=r"artifacts\.reports"):
        render_workflow(configuration, config_path=Path("config.yaml"))


def test_workflow_quotes_safe_project_paths_with_spaces() -> None:
    """Ordinary spaces should remain supported through POSIX shell quoting."""
    configuration = ProjectConfiguration(
        target=TargetConfiguration(specification="https://example.test/openapi.json"),
        artifacts=ArtifactConfiguration(
            suite="generated files/scenarios.yaml",
            reports="generated files/reports",
        ),
    )

    workflow = render_workflow(
        configuration,
        config_path=Path(".api-test-pilot/project config.yaml"),
    )

    yaml.safe_load(workflow)
    assert "--config '.api-test-pilot/project config.yaml'" in workflow
    assert "--report 'generated files/reports/report.json'" in workflow
    assert "--report 'deterministic-artifacts/generated files/reports/report.json'" in workflow


def test_checked_in_ci_isolates_optional_copilot_from_core_regression() -> None:
    """The repository CI should preserve deterministic results when AI is unavailable."""
    repository_root = Path(__file__).resolve().parents[1]
    workflow = (repository_root / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    regression_block = workflow.split("  regression:\n", 1)[1].split("  ai-advice:\n", 1)[0]
    ai_block = workflow.split("  ai-advice:\n", 1)[1]
    root_permissions = workflow.split("concurrency:", 1)[0]
    assert "GitHub Copilot" not in regression_block
    assert "copilot-requests" not in root_permissions
    assert "needs: regression" in ai_block
    assert "always()" in ai_block
    assert "continue-on-error: true" in ai_block
    assert "copilot-requests: write" in ai_block
    assert "actions/download-artifact@v8" in ai_block
    assert "2>&1 | tee ai-reports/ai-generation-advice.txt" in ai_block
    assert "2>&1 | tee ai-reports/ai-failure-analysis.txt" in ai_block
    assert "analyze_failures:" in workflow
    assert "default: false" in workflow
    analysis_block = ai_block.split("- name: Analyze failures with GitHub Copilot", 1)[1].split(
        "- name: Upload AI advice and analysis", 1
    )[0]
    assert "inputs.analyze_failures" in analysis_block
    assert "vars.API_TEST_PILOT_AI_FAILURE_ANALYSIS == 'true'" in analysis_block


def test_variable_assignment_parser_is_strict() -> None:
    """Postman variable options should accept values with equals signs and reject typos."""
    assert parse_variable_assignments(["token=a=b", "stage=test"]) == {
        "token": "a=b",
        "stage": "test",
    }
    with pytest.raises(ValueError, match="expected NAME=VALUE"):
        parse_variable_assignments(["missing-separator"])
