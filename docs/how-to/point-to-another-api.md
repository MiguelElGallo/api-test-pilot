# Point to another API

Use `init` when you want to replace the current target and regenerate the GitHub Actions workflow.

## Use an OpenAPI URL

Point to the specification and, when needed, choose a different server for the requests:

```bash
uv run --no-sync api-test-pilot init \
  --spec https://api.example.com/openapi.json \
  --base-url https://staging-api.example.com \
  --force
```

`--force` replaces only the three generated project files. Review your existing configuration
before you use it.

## Use a local OpenAPI or Swagger file

```bash
uv run --no-sync api-test-pilot init \
  --spec contracts/openapi.yaml \
  --base-url https://staging-api.example.com \
  --force
```

JSON and YAML files are both supported.

If the local file has a relative server URL, for example `/api/v1`, `--base-url` is required. A
relative URL has no host on its own, so the tool cannot safely guess where to send requests.

## Supply a Postman variable

Pass each non-secret variable as `NAME=VALUE`:

```bash
uv run --no-sync api-test-pilot init \
  --spec collections/orders.postman_collection.json \
  --variable baseUrl=https://staging-api.example.com \
  --variable tenant=north \
  --force
```

Do not pass tokens or passwords through `--variable`; these values are saved in the project
configuration. Use [authentication environment variables](add-authentication.md) for secrets.

Postman requests with absolute URLs must all use the same origin. To run a collection against one
test environment, set `--base-url`; collections that mix origins are rejected instead of having
their requests silently redirected.

## Regenerate after an API change

When the target remains the same and only its specification changed, keep the configuration and
regenerate the suite:

```bash
uv run --no-sync api-test-pilot generate --config .api-test-pilot/config.yaml
```

Then run it:

```bash
uv run --no-sync api-test-pilot run --config .api-test-pilot/config.yaml
```

See [Supported specifications](../reference/supported-specifications.md) for the exact OpenAPI and
Postman features that are read.
