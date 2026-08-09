# API Test Pilot

API Test Pilot generates executable functional, negative, and edge-case API scenarios from
OpenAPI/Swagger or Postman collections. It runs those scenarios in CI, produces JSON, JUnit XML,
and HTML reports, optionally asks GitHub Models for test suggestions and failure analysis, and can
notify Slack or email recipients.

The repository includes a deterministic FastAPI fixture for CI and demonstrates public-contract
generation with [Swagger Petstore](https://petstore3.swagger.io/api/v3/openapi.json). No FastAPI
Cloud deployment is required for the public example.

## Quick start

Prerequisites: Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --all-extras --no-editable

# Generate from the public Swagger Petstore contract.
uv run --no-sync api-test-pilot generate \
  --spec https://petstore3.swagger.io/api/v3/openapi.json \
  --output generated-scenarios.yaml

# For a deterministic local regression, run the bundled API.
uv run --no-sync uvicorn api_test_pilot.example_api:app --port 8000
uv run --no-sync api-test-pilot generate \
  --spec http://127.0.0.1:8000/openapi.json \
  --base-url http://127.0.0.1:8000 \
  --output generated-scenarios.yaml
uv run --no-sync api-test-pilot run --suite generated-scenarios.yaml --report-dir reports
```

Open `reports/report.html` for a human-readable report. `reports/report.json` is the canonical
machine result and `reports/junit.xml` integrates with CI report viewers.

## Postman collections

Postman Collection v2.0/v2.1 JSON is detected automatically:

```bash
uv run --no-sync api-test-pilot generate \
  --spec examples/postman-echo.collection.json \
  --output generated-scenarios.yaml
```

Collection variables are intentionally not resolved implicitly; export a collection with concrete
URLs or use `--base-url` for the target environment.

## AI-assisted workflows

GitHub Actions grants the regression job only `contents: read` and `models: read`. The job-scoped
`GITHUB_TOKEN` calls GitHub Models, so no standalone AI API key is stored. Locally, use a GitHub
token with Models read access:

```bash
GITHUB_TOKEN="..." uv run --no-sync api-test-pilot generate --spec openapi.yaml --ai
GITHUB_TOKEN="..." uv run --no-sync api-test-pilot run --suite generated-scenarios.yaml --ai-analysis
```

Deterministic generation never depends on AI. Generation advice is printed separately, while
failure analysis is embedded in the HTML and JSON reports. Request headers and bodies are not sent
to the model.

## Notifications

The regression workflow always invokes the notification adapter after reports are created. With no
notification secrets, it exits successfully and reports that no channel is configured.

For Slack, add the repository Actions secret `SLACK_WEBHOOK_URL`.

For email, add these Actions secrets:

- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`
- `EMAIL_FROM`, `EMAIL_TO`

The SMTP adapter uses STARTTLS. Configure either channel or both. Secrets are never serialized into
test reports.

## Commands

```text
api-test-pilot generate  Generate scenarios from a path or HTTPS contract URL.
api-test-pilot run       Execute scenarios and write JSON, JUnit, and HTML reports.
api-test-pilot notify    Notify all channels configured in the environment.
```

## Quality gates

```bash
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
uv run --no-sync ty check
uv run --no-sync pytest
```

See [the architecture guide](docs/architecture.md) for module boundaries and the data flow.

## Security notes

- Only load contracts from trusted paths or HTTPS sources.
- Generated suites may contain example data from the source contract; review before publishing.
- GitHub Models receives only a compact failure summary without request headers or request bodies.
- Slack webhooks and SMTP credentials belong in GitHub Actions secrets, never source control.
