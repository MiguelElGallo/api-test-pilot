"""Project configuration shared by local commands and generated CI workflows."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from api_test_pilot.models import ExecutionPolicy


class TargetConfiguration(BaseModel):
    """Contract location, runtime server, and non-secret Postman variables."""

    model_config = ConfigDict(extra="forbid")

    specification: str
    base_url: str | None = None
    variables: dict[str, str] = Field(default_factory=dict)


class ArtifactConfiguration(BaseModel):
    """Paths for generated scenarios and regression reports."""

    model_config = ConfigDict(extra="forbid")

    suite: str = "generated-scenarios.yaml"
    reports: str = "reports"


class ProjectConfiguration(BaseModel):
    """Versioned single source of truth for local and GitHub Actions execution."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    target: TargetConfiguration
    execution: ExecutionPolicy = Field(default_factory=ExecutionPolicy)
    authentication: dict[str, str] = Field(default_factory=dict)
    artifacts: ArtifactConfiguration = Field(default_factory=ArtifactConfiguration)


def load_project_configuration(path: Path) -> ProjectConfiguration:
    """Read and validate a YAML project configuration."""
    return ProjectConfiguration.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def write_project_configuration(
    configuration: ProjectConfiguration,
    path: Path,
    *,
    overwrite: bool,
) -> None:
    """Write readable configuration without silently replacing an existing project."""
    if path.exists() and not overwrite:
        raise FileExistsError(f"Configuration already exists: {path}; use --force to replace it")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(configuration.model_dump(mode="json"), sort_keys=False),
        encoding="utf-8",
    )


def parse_variable_assignments(assignments: list[str]) -> dict[str, str]:
    """Parse repeated NAME=VALUE options with precise validation errors."""
    variables: dict[str, str] = {}
    for assignment in assignments:
        name, separator, value = assignment.partition("=")
        if not separator or not name.strip():
            raise ValueError(f"Invalid variable '{assignment}'; expected NAME=VALUE")
        variables[name.strip()] = value
    return variables
