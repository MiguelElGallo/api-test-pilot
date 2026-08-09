"""Optional Slack webhook and SMTP result notifications."""

from __future__ import annotations

import os
import smtplib
import ssl
from email.message import EmailMessage

import httpx

from api_test_pilot.models import NotificationSettings, RunSummary


def settings_from_environment() -> NotificationSettings:
    """Load notification settings without requiring either channel."""
    return NotificationSettings(
        slack_webhook_url=os.getenv("SLACK_WEBHOOK_URL") or None,
        smtp_host=os.getenv("SMTP_HOST") or None,
        smtp_port=int(os.getenv("SMTP_PORT", "587")),
        smtp_username=os.getenv("SMTP_USERNAME") or None,
        smtp_password=os.getenv("SMTP_PASSWORD") or None,
        email_from=os.getenv("EMAIL_FROM") or None,
        email_to=os.getenv("EMAIL_TO") or None,
    )


def _message(summary: RunSummary) -> str:
    """Create a concise channel-independent pipeline summary."""
    state = "PASSED" if summary.failed == 0 else "FAILED"
    return (
        f"API regression {state}: {summary.passed}/{summary.total} passed, "
        f"{summary.failed} failed against {summary.base_url}."
    )


def notify_slack(summary: RunSummary, webhook_url: str, *, timeout: float = 10.0) -> None:
    """Send one Slack incoming-webhook notification."""
    response = httpx.post(webhook_url, json={"text": _message(summary)}, timeout=timeout)
    response.raise_for_status()


def notify_email(summary: RunSummary, settings: NotificationSettings) -> None:
    """Send one STARTTLS SMTP notification using configured credentials."""
    required = {
        "smtp_host": settings.smtp_host,
        "smtp_username": settings.smtp_username,
        "smtp_password": settings.smtp_password,
        "email_from": settings.email_from,
        "email_to": settings.email_to,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise ValueError(f"Incomplete email settings: {', '.join(missing)}")
    smtp_host = settings.smtp_host or ""
    smtp_username = settings.smtp_username or ""
    smtp_password = settings.smtp_password or ""
    message = EmailMessage()
    message["Subject"] = f"API regression {'passed' if summary.failed == 0 else 'failed'}"
    message["From"] = settings.email_from
    message["To"] = settings.email_to
    message.set_content(_message(summary))
    with smtplib.SMTP(smtp_host, settings.smtp_port, timeout=15) as server:
        server.starttls(context=ssl.create_default_context())
        server.login(smtp_username, smtp_password)
        server.send_message(message)


def notify_configured(summary: RunSummary, settings: NotificationSettings) -> list[str]:
    """Send all fully configured channels and return their names."""
    channels: list[str] = []
    if settings.slack_webhook_url:
        notify_slack(summary, str(settings.slack_webhook_url))
        channels.append("slack")
    if settings.smtp_host or settings.email_to:
        notify_email(summary, settings)
        channels.append("email")
    return channels
