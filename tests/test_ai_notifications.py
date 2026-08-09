"""Tests for optional GitHub Models and notification adapters."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Self

import httpx
import pytest

from api_test_pilot.ai import AIAnalysisError, GitHubModelsClient
from api_test_pilot.models import NotificationSettings, RunSummary
from api_test_pilot.notifications import (
    notify_configured,
    notify_email,
    notify_slack,
    settings_from_environment,
)


def _empty_summary() -> RunSummary:
    """Create a successful report for adapter tests."""
    now = datetime.now(UTC)
    return RunSummary(
        started_at=now,
        finished_at=now,
        base_url="https://api.example.test",
        total=0,
        passed=0,
        failed=0,
        results=[],
    )


def test_ai_client_is_optional_without_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """Local users should not need an AI credential for deterministic tests."""
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    assert GitHubModelsClient.from_environment() is None


def test_ai_client_reads_safe_environment_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provider settings should be configurable without changing implementation code."""
    monkeypatch.setenv("GITHUB_TOKEN", "fixture-token")
    monkeypatch.setenv("GITHUB_MODELS_MODEL", "openai/fixture")

    client = GitHubModelsClient.from_environment()

    assert client is not None
    assert client.model == "openai/fixture"
    assert client.analyze_failures(_empty_summary()) == "No failed scenarios require AI analysis."


def test_ai_client_parses_completion(monkeypatch: pytest.MonkeyPatch) -> None:
    """GitHub Models completion content should be returned as plain text."""

    class Response:
        """Small response double matching the used HTTPX methods."""

        def raise_for_status(self) -> None:
            """Represent a successful response."""

        def json(self) -> dict[str, object]:
            """Return the expected completion envelope."""
            return {"choices": [{"message": {"content": "Check the boundary."}}]}

    monkeypatch.setattr(httpx, "post", lambda *_args, **_kwargs: Response())

    assert GitHubModelsClient("token").generation_advice({}) == "Check the boundary."


def test_ai_client_wraps_invalid_response(monkeypatch: pytest.MonkeyPatch) -> None:
    """Malformed provider responses should become actionable domain errors."""

    class Response:
        """Response double that lacks completion choices."""

        def raise_for_status(self) -> None:
            """Represent a successful HTTP response."""

        def json(self) -> dict[str, object]:
            """Return a malformed completion body."""
            return {}

    monkeypatch.setattr(httpx, "post", lambda *_args, **_kwargs: Response())
    with pytest.raises(AIAnalysisError, match="GitHub Models request failed"):
        GitHubModelsClient("token").generation_advice({})


def test_no_notification_configuration_is_a_noop() -> None:
    """Pipelines without notification secrets should complete without network calls."""
    assert notify_configured(_empty_summary(), NotificationSettings()) == []


def test_notification_settings_load_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Notification adapters should receive typed values from environment variables."""
    monkeypatch.setenv("SMTP_HOST", "smtp.example.test")
    monkeypatch.setenv("SMTP_PORT", "2525")
    monkeypatch.setenv("EMAIL_TO", "team@example.test")

    settings = settings_from_environment()

    assert settings.smtp_host == "smtp.example.test"
    assert settings.smtp_port == 2525
    assert settings.email_to == "team@example.test"


def test_email_requires_complete_settings() -> None:
    """Partially configured SMTP delivery should fail with the missing fields."""
    with pytest.raises(ValueError, match="Incomplete email settings"):
        notify_email(_empty_summary(), NotificationSettings(smtp_host="smtp.example.test"))


def test_email_sends_with_starttls(monkeypatch: pytest.MonkeyPatch) -> None:
    """Complete SMTP settings should authenticate and send one message."""
    events: list[str] = []

    class SMTP:
        """Context-manager double for the standard-library SMTP client."""

        def __init__(self, _host: str, _port: int, *, timeout: int) -> None:
            """Record that the transport was constructed with a timeout."""
            events.append(f"connect:{timeout}")

        def __enter__(self) -> Self:
            """Return the active transport double."""
            return self

        def __exit__(self, *_args: object) -> None:
            """Close the transport context without suppressing errors."""

        def starttls(self, *, context: object) -> None:
            """Record TLS negotiation."""
            events.append(f"tls:{context is not None}")

        def login(self, _username: str, _password: str) -> None:
            """Record SMTP authentication."""
            events.append("login")

        def send_message(self, _message: object) -> None:
            """Record message submission."""
            events.append("send")

    monkeypatch.setattr("api_test_pilot.notifications.smtplib.SMTP", SMTP)
    settings = NotificationSettings(
        smtp_host="smtp.example.test",
        smtp_username="user",
        smtp_password=events.__class__.__name__,
        email_from="ci@example.test",
        email_to="team@example.test",
    )

    notify_email(_empty_summary(), settings)

    assert events == ["connect:15", "tls:True", "login", "send"]


def test_slack_posts_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    """Slack notifications should post a compact pass/fail payload."""
    captured: dict[str, object] = {}

    class Response:
        """Minimal successful HTTP response double."""

        def raise_for_status(self) -> None:
            """Represent a successful webhook request."""

    def post(url: str, **kwargs: object) -> Response:
        """Capture outgoing webhook request values."""
        captured.update({"url": url, **kwargs})
        return Response()

    monkeypatch.setattr(httpx, "post", post)
    notify_slack(_empty_summary(), "https://hooks.slack.test/fixture")

    assert captured["url"] == "https://hooks.slack.test/fixture"
    assert "PASSED" in str(captured["json"])
