# API Test Pilot

[![API regression](https://github.com/MiguelElGallo/api-test-pilot/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/MiguelElGallo/api-test-pilot/actions/workflows/ci.yml)
[![Documentation](https://github.com/MiguelElGallo/api-test-pilot/actions/workflows/docs.yml/badge.svg?branch=main)](https://github.com/MiguelElGallo/api-test-pilot/actions/workflows/docs.yml)
[![GitHub release](https://img.shields.io/github/v/release/MiguelElGallo/api-test-pilot?display_name=tag&sort=semver)](https://github.com/MiguelElGallo/api-test-pilot/releases/latest)
[![Release checks](https://github.com/MiguelElGallo/api-test-pilot/actions/workflows/release.yml/badge.svg)](https://github.com/MiguelElGallo/api-test-pilot/actions/workflows/release.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-2ea44f.svg)](LICENSE)

API Test Pilot turns one OpenAPI, Swagger, or supported Postman specification into the same
executable regression suite locally and in GitHub Actions. It generates functional, negative, and
schema-boundary scenarios; validates response contracts; produces JSON, JUnit XML, and HTML
reports; optionally uses GitHub Copilot for test advice and failure analysis; and notifies Slack or
email recipients.

[Read the documentation](https://miguelelgallo.github.io/api-test-pilot/), or start with the
[real Postman Echo tutorial](docs/tutorials/test-a-public-api.md).

## Initialize a target

Prerequisites are Python 3.12+ and [uv](https://docs.astral.sh/uv/). Clone this public repository,
install the locked environment, and point `init` at a local file or HTTP/HTTPS specification:

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

The generated suite records its allowed methods, but the runner also requires an independent
runtime allowlist immediately before each HTTP request. Project runs take that authority from
`.api-test-pilot/config.yaml`; direct suite runs default to safe methods and require an explicit
`--allow-method` for writes. This repository opts into `POST` only for its deterministic in-process
FastAPI fixture.

## Authentication and GitHub secrets

OpenAPI security schemes and supported Postman authentication are converted into environment
variable references. Credential values are never serialized into configuration, scenarios,
reports, or AI prompts. For example:

```yaml
authentication:
  BearerAuth: API_TEST_AUTH_BEARERAUTH
  TenantKey: API_TEST_AUTH_TENANTKEY
```

Set those variables locally before running the suite through its project configuration. Authenticated
projects pin the resolved `base_url`, and the runner requires the suite's credential names and target
to match that trusted configuration. In GitHub, create repository or environment secrets with the
same names. The generated workflow contains explicit bindings such as:

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
- raw JSON bodies, query parameters, and non-authorization headers;
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

Unresolved variables, executable pre-request/test scripts, non-JSON or multipart/form-data bodies,
unsupported authentication mechanisms, and collections that target more than one origin fail
explicitly. API Test Pilot never executes arbitrary Postman JavaScript, silently drops a body, or
silently sends a request to a different origin.

Scenario execution does not automatically follow redirects. Remote contract loading follows only
same-origin redirects and rejects cross-origin or HTTPS-downgrade hops.

## Schema-driven scenarios

Request parameters and JSON bodies use documented examples for functional checks. Edge generation
recursively exercises enums, numeric bounds, string lengths, object properties, arrays, nullable
types, and composed schemas. Compatible object `allOf` schemas are explicitly combined into one
JSON body, and every generated request body is checked against the source schema. Unsupported or
incompatible composition fails with a clear error. Resource-safe caps prevent a large `maxLength`
or `maxItems` from creating unreasonable payloads. Required path inputs receive deliberately
invalid values instead of leaving unresolved `{parameter}` placeholders.

Only `application/json` request bodies are supported. An OpenAPI or Swagger operation that
declares XML, multipart, form, `application/problem+json`, or another request format is rejected
during generation rather than being sent as JSON. Response media types are always checked, but JSON
Schema body validation is applied only to JSON responses. When a local OpenAPI or Swagger file
declares a relative server such as `/api/v1`, supply an absolute `--base-url`; a remote
specification can resolve that path against its own origin.

## AI-assisted workflows

GitHub Actions runs the deterministic regression first. On trusted scheduled or manually started
runs, a separate best-effort AI job can then install GitHub Copilot CLI and request generation
advice. Only that job receives `copilot-requests: write`; no standalone AI API key is stored.
Locally, install and authenticate GitHub Copilot CLI first:

```bash
copilot login
uv run --no-sync api-test-pilot generate --config .api-test-pilot/config.yaml --ai
uv run --no-sync api-test-pilot run --config .api-test-pilot/config.yaml --ai-analysis
```

Deterministic generation never depends on AI. Request headers, bodies, and credentials are excluded
from model context. Scheduled and manually dispatched workflows save generation advice in the
separate `api-regression-ai-advice` artifact, under `ai-reports/ai-generation-advice.txt`. Failure
analysis is off by default because it can include response excerpts. For a manual run, enable the
`analyze_failures` input. For scheduled runs, set the repository Actions variable
`API_TEST_PILOT_AI_FAILURE_ANALYSIS` to `true`. Copilot is never installed for pull-request
regression. If AI is unavailable, the regression result and its reports remain authoritative.

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

Pytest is configured to import the checked-out `src/` tree, including when `uv sync --no-editable`
is used. Release automation separately installs the built wheel into a clean environment and runs a
small command-line smoke test, so source testing and packaging testing both remain covered.

Read [how generation works](docs/explanation/how-generation-works.md) for the complete data flow.
Security reporting instructions are in [SECURITY.md](SECURITY.md).
