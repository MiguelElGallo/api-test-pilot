# Environment variables

API Test Pilot reads secrets at run time. Keep them out of configuration files and scenario files.

## API authentication

Authentication variable names are created from the specification and stored in project configuration. Common generated names follow this form:

```text
API_TEST_AUTH_<SECURITY_SCHEME_NAME>
```

For example, `bearerAuth` becomes `API_TEST_AUTH_BEARERAUTH`. The exact name in `.api-test-pilot/config.yaml` is the source of truth.

| Authentication kind | Variable value |
| --- | --- |
| API key | The API-key value. |
| HTTP Basic | `username:password`. |
| HTTP Bearer | Bearer token without the `Bearer ` prefix. |
| OAuth 2 | Ready-to-use bearer access token. |
| OpenID Connect | Ready-to-use bearer token. |

## GitHub Copilot CLI

| Variable | Required | Meaning |
| --- | --- | --- |
| `COPILOT_CLI` | No | Path or command name for GitHub Copilot CLI. When unset, `copilot` is found on `PATH`. |

GitHub Copilot CLI manages its own authentication. In the generated workflow, `GITHUB_TOKEN` is made available only to the optional AI step on trusted scheduled or manually started runs.

## Slack

| Variable | Required | Meaning |
| --- | --- | --- |
| `SLACK_WEBHOOK_URL` | Yes for Slack | Slack incoming-webhook URL. |

## Email

All email variables except `SMTP_PORT` are required to send email.

| Variable | Default | Meaning |
| --- | --- | --- |
| `SMTP_HOST` | None | SMTP server host. |
| `SMTP_PORT` | `587` | SMTP server port. |
| `SMTP_USERNAME` | None | SMTP login name. |
| `SMTP_PASSWORD` | None | SMTP login password. |
| `EMAIL_FROM` | None | Sender address. |
| `EMAIL_TO` | None | Recipient address. |

Email delivery uses STARTTLS and authenticated SMTP.
