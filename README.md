# API Test Pilot

API Test Pilot turns one OpenAPI, Swagger, or supported Postman specification into the same
executable regression suite locally and in GitHub Actions. It generates functional, negative, and
schema-boundary scenarios; validates response contracts; produces JSON, JUnit XML, and HTML
reports; optionally uses GitHub Copilot for test advice and failure analysis; and notifies Slack or
email recipients.

## Initialize a target

Prerequisites are Python 3.12+ and [uv](https://docs.astral.sh/uv/). Clone this private repository,
install the locked environment, and point `init` at a local file or HTTPS specification:

```bash
uv sync --all-extras --locked --no-editable

uv run --no-sync api-test-pilot init \
  --spec https://api.example.com/openapi.json \
  --base-url https://staging-api.example.com
```

The command validates the contract and creates three coordinated artifacts:

```text
.api-test-pilot/config.yaml
generated-scenarios.yaml
.github/workflows/api-regression.yml
```

Both local execution and GitHub Actions consume `.api-test-pilot/config.yaml`, so changing the
target does not require editing shell commands in a workflow:

```bash
uv run --no-sync api-test-pilot generate --config .api-test-pilot/config.yaml
uv run --no-sync api-test-pilot run --config .api-test-pilot/config.yaml
```

Open `reports/report.html` for the human-readable result. `reports/report.json` is the canonical
machine result and `reports/junit.xml` integrates with CI report viewers.

## Safe execution policy

New projects allow only `GET`, `HEAD`, and `OPTIONS`. This prevents an arbitrary contract from
silently creating, changing, or deleting real data. Opt into each mutating method only for a
disposable or controlled test environment:

```bash
uv run --no-sync api-test-pilot init \
  --spec openapi.yaml \
  --base-url https://staging-api.example.com \
  --allow-method GET \
  --allow-method POST
```

The method allowlist is embedded in the generated suite and enforced again immediately before
each HTTP request. Hand-editing a scenario therefore cannot bypass the policy accidentally. This
repository opts into `POST` only for its deterministic in-process FastAPI fixture.

## Authentication and GitHub secrets

OpenAPI security schemes and supported Postman authentication are converted into environment
variable references. Credential values are never serialized into configuration, scenarios,
reports, or AI prompts. For example:

```yaml
authentication:
  BearerAuth: API_TEST_AUTH_BEARERAUTH
  TenantKey: API_TEST_AUTH_TENANTKEY
```

Set those variables locally before running the suite. In GitHub, create repository or environment
secrets with the same names. The generated workflow contains explicit bindings such as:

```yaml
env:
  API_TEST_AUTH_BEARERAUTH: ${{ secrets.API_TEST_AUTH_BEARERAUTH }}
```

Supported schemes are header/query/cookie API keys, HTTP bearer, HTTP basic using a `user:password`
environment value, OAuth 2 bearer tokens, and OpenID Connect bearer tokens. When OpenAPI provides
alternative security requirements, the runner selects the first alternative whose environment
variables are configured and fails before transport if none are available.

## Response contract validation

A passing status code is not enough. Generated scenarios retain documented response media types,
headers, and dereferenced JSON Schemas. The runner verifies all of them and records concise schema
paths in JSON, JUnit, HTML, and optional Copilot failure analysis.

Functional and edge scenarios expect documented 2xx responses. Negative scenarios prefer the
operation's documented 400/404/422 contract and use a narrow fallback only when the specification
does not describe client errors.

## Postman collections

Postman Collection v2.0/v2.1 JSON is detected automatically. The safe declarative subset supports:

- nested folders and concrete requests;
- collection variables plus repeated `--variable NAME=VALUE` overrides;
- raw JSON or text bodies, query parameters, and non-authorization headers;
- collection- or request-level bearer, basic, and API-key authentication without retaining
  credential values; and
- saved response status codes.

For example:

```bash
uv run --no-sync api-test-pilot init \
  --spec collection.json \
  --base-url https://staging-api.example.com \
  --variable tenant=north
```

Unresolved variables, executable pre-request/test scripts, multipart/form-data bodies, and
unsupported authentication mechanisms fail explicitly. API Test Pilot never executes arbitrary
Postman JavaScript or silently drops it.

## Schema-driven scenarios

Request parameters and JSON bodies use documented examples for functional checks. Edge generation
recursively exercises enums, numeric bounds, string lengths, object properties, arrays, nullable
types, and composed schemas. Resource-safe caps prevent a large `maxLength` or `maxItems` from
creating unreasonable payloads. Required path inputs receive deliberately invalid values instead
of leaving unresolved `{parameter}` placeholders.

## AI-assisted workflows

GitHub Actions installs GitHub Copilot CLI and grants only `contents: read` plus
`copilot-requests: write`. The job-scoped `GITHUB_TOKEN` authenticates Copilot, so no standalone AI
API key is stored. Locally, install and authenticate GitHub Copilot CLI first:

```bash
copilot login
uv run --no-sync api-test-pilot generate --config .api-test-pilot/config.yaml --ai
uv run --no-sync api-test-pilot run --config .api-test-pilot/config.yaml --ai-analysis
```

Deterministic generation never depends on AI. Request headers, bodies, and credentials are excluded
from model context. Scheduled and manually dispatched workflows save generation advice as
`reports/ai-generation-advice.txt`; failure analysis is included only when failures exist. Copilot
is installed and receives `GITHUB_TOKEN` only on trusted scheduled or manually dispatched runs,
never during pull-request regression execution.

## Reports and notifications

The workflow uploads the generated suite and all reports even when regression tests fail. Add
`SLACK_WEBHOOK_URL` as an Actions secret for Slack notifications. For email, configure:

- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, and `SMTP_PASSWORD`;
- `EMAIL_FROM` and `EMAIL_TO`.

The SMTP adapter uses STARTTLS. With no notification secrets configured, the notification step
exits successfully and reports that no channel is configured.

## Commands

```text
api-test-pilot init      Create shared config, local scenarios, and GitHub Actions.
api-test-pilot generate  Regenerate scenarios from a project config or direct specification.
api-test-pilot run       Execute scenarios and write JSON, JUnit, and HTML reports.
api-test-pilot analyze   Add Copilot failure analysis to an existing report set.
api-test-pilot notify    Notify all channels configured in the environment.
```

## Quality gates

```bash
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
uv run --no-sync ty check
uv run --no-sync pytest
```

See [the architecture guide](docs/architecture.md) for module boundaries and the complete data
flow. Security reporting instructions are in [SECURITY.md](SECURITY.md).
