"""Tests for optional GitHub Copilot CLI and notification adapters."""

from __future__ import annotations

from datetime import UTC, datetime
from subprocess import CompletedProcess
from typing import Self

import httpx
import pytest

from api_test_pilot.ai import AIAnalysisError, CopilotClient
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


def test_ai_client_is_optional_without_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    """Local users should not need Copilot CLI for deterministic tests."""
    monkeypatch.delenv("COPILOT_CLI", raising=False)
    monkeypatch.setattr("api_test_pilot.ai.shutil.which", lambda _name: None)

    assert CopilotClient.discover() is None


def test_ai_client_reads_executable_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    """The Copilot executable should be configurable without changing implementation code."""
    monkeypatch.setenv("COPILOT_CLI", "/fixture/copilot")

    client = CopilotClient.discover()

    assert client is not None
    assert client.executable == "/fixture/copilot"
    assert client.analyze_failures(_empty_summary()) == "No failed scenarios require AI analysis."


def test_ai_client_parses_completion(monkeypatch: pytest.MonkeyPatch) -> None:
    """GitHub Copilot CLI output should be returned as plain text."""

    def run(*_args: object, **_kwargs: object) -> CompletedProcess[str]:
        """Return a successful Copilot CLI process result."""
        return CompletedProcess([], 0, stdout="Check the boundary.\n", stderr="")

    monkeypatch.setattr("api_test_pilot.ai.subprocess.run", run)

    assert CopilotClient().generation_advice({}) == "Check the boundary."


def test_ai_client_wraps_failed_process(monkeypatch: pytest.MonkeyPatch) -> None:
    """Failed Copilot processes should become actionable domain errors."""

    def run(*_args: object, **_kwargs: object) -> CompletedProcess[str]:
        """Return a failed Copilot CLI process result."""
        return CompletedProcess([], 7, stdout="", stderr="authentication failed")

    monkeypatch.setattr("api_test_pilot.ai.subprocess.run", run)
    with pytest.raises(AIAnalysisError, match="exit code 7"):
        CopilotClient().generation_advice({})


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


def test_empty_smtp_port_uses_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """An unset GitHub secret rendered as an empty string should retain the default port."""
    monkeypatch.setenv("SMTP_PORT", "")

    assert settings_from_environment().smtp_port == 587


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
