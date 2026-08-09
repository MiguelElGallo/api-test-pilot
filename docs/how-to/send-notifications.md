# Send notifications

The `notify` command reads a completed JSON report and sends a short pass or fail summary. You can
use Slack, email, or both.

## Send a Slack message

A Slack incoming webhook is a private URL that accepts a message for one channel. Set it in the
environment, then run `notify`:

```bash
export SLACK_WEBHOOK_URL='https://hooks.slack.com/services/...'
uv run --no-sync api-test-pilot notify --report reports/report.json
```

For GitHub Actions, create a secret with the same name:

```bash
gh secret set SLACK_WEBHOOK_URL
```

## Send an email

SMTP is the standard service used to send email. Set all required values:

```bash
export SMTP_HOST='smtp.example.com'
export SMTP_PORT='587'
export SMTP_USERNAME='api-tests@example.com'
export SMTP_PASSWORD='replace-with-password'
export EMAIL_FROM='api-tests@example.com'
export EMAIL_TO='team@example.com'

uv run --no-sync api-test-pilot notify --report reports/report.json
```

The connection uses STARTTLS before the username and password are sent.

For GitHub Actions, add each value as a repository secret. The generated workflow already calls
`notify` after it uploads the reports.

When no channel is configured, the command succeeds and prints:

```text
Notified: no configured channels
```

See [Environment variables](../reference/environment-variables.md) for the complete list and email
requirements.
