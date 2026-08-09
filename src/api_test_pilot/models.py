"""Typed domain models shared by generation, execution, and reporting."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

SAFE_HTTP_METHODS = ("GET", "HEAD", "OPTIONS")


class ScenarioCategory(StrEnum):
    """Supported categories of generated API behavior."""

    FUNCTIONAL = "functional"
    NEGATIVE = "negative"
    EDGE = "edge"


class AuthenticationKind(StrEnum):
    """Authentication mechanisms supported by the HTTP runner."""

    API_KEY = "api_key"
    HTTP_BASIC = "http_basic"
    HTTP_BEARER = "http_bearer"
    OAUTH2 = "oauth2"
    OPENID_CONNECT = "openid_connect"


class AuthenticationScheme(BaseModel):
    """A secret-free runtime binding for one contract security scheme."""

    model_config = ConfigDict(extra="forbid")

    kind: AuthenticationKind
    environment_variable: str
    location: str | None = None
    parameter_name: str | None = None


class ExpectedResponse(BaseModel):
    """Contract assertions for one documented HTTP response status."""

    model_config = ConfigDict(extra="forbid")

    status_code: int
    media_type: str | None = None
    response_schema: dict[str, Any] | None = None
    headers: list[str] = Field(default_factory=list)


class ExecutionPolicy(BaseModel):
    """Explicit allowlist that prevents accidental mutating API requests."""

    model_config = ConfigDict(extra="forbid")

    allowed_methods: list[str] = Field(default_factory=lambda: list(SAFE_HTTP_METHODS))

    @field_validator("allowed_methods")
    @classmethod
    def normalize_methods(cls, methods: list[str]) -> list[str]:
        """Normalize and de-duplicate configured HTTP methods."""
        normalized = list(dict.fromkeys(method.upper() for method in methods))
        if not normalized:
            raise ValueError("At least one HTTP method must be allowed")
        return normalized


class Scenario(BaseModel):
    """A serializable HTTP scenario derived from an API contract."""

    model_config = ConfigDict(extra="forbid")

    identifier: str
    name: str
    category: ScenarioCategory
    method: str
    path: str
    headers: dict[str, str] = Field(default_factory=dict)
    query: dict[str, Any] = Field(default_factory=dict)
    body: Any | None = None
    expected_statuses: list[int]
    expected_responses: list[ExpectedResponse] = Field(default_factory=list)
    security: list[list[str]] = Field(default_factory=list)
    description: str


class ScenarioSuite(BaseModel):
    """A versioned collection of scenarios and its source metadata."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "2.0"
    source: str
    base_url: str
    execution: ExecutionPolicy = Field(default_factory=ExecutionPolicy)
    authentication: dict[str, AuthenticationScheme] = Field(default_factory=dict)
    scenarios: list[Scenario]


class ScenarioResult(BaseModel):
    """The observed outcome for one scenario execution."""

    model_config = ConfigDict(extra="forbid")

    scenario: Scenario
    passed: bool
    status_code: int | None = None
    duration_ms: float
    error: str | None = None
    response_excerpt: str | None = None


class RunSummary(BaseModel):
    """Aggregate counts for a completed test run."""

    model_config = ConfigDict(extra="forbid")

    started_at: datetime
    finished_at: datetime
    base_url: str
    total: int
    passed: int
    failed: int
    results: list[ScenarioResult]
    ai_analysis: str | None = None

    @classmethod
    def from_results(
        cls,
        *,
        started_at: datetime,
        base_url: str,
        results: list[ScenarioResult],
    ) -> RunSummary:
        """Create a summary with internally consistent pass/fail counts."""
        passed = sum(result.passed for result in results)
        return cls(
            started_at=started_at,
            finished_at=datetime.now(UTC),
            base_url=base_url,
            total=len(results),
            passed=passed,
            failed=len(results) - passed,
            results=results,
        )


class NotificationSettings(BaseModel):
    """Optional notification channels loaded from environment variables."""

    model_config = ConfigDict(extra="forbid")

    slack_webhook_url: HttpUrl | None = None
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    email_from: str | None = None
    email_to: str | None = None
