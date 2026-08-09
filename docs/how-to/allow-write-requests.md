# Allow write requests

New projects block methods that can change data. Allow a method only against a test environment
where created or deleted data is expected.

## Choose the allowed methods

Pass every method you want during `init`:

```bash
uv run --no-sync api-test-pilot init \
  --spec openapi.yaml \
  --base-url https://staging-api.example.com \
  --allow-method GET \
  --allow-method POST \
  --force
```

Or edit the existing project configuration:

```yaml
execution:
  allowed_methods:
  - GET
  - POST
```

Regenerate the suite after editing:

```bash
uv run --no-sync api-test-pilot generate --config .api-test-pilot/config.yaml
```

## Check the target before running

Confirm the target in the same file:

```yaml
target:
  base_url: https://staging-api.example.com
```

Then run the tests:

```bash
uv run --no-sync api-test-pilot run --config .api-test-pilot/config.yaml
```

The generated suite keeps the list of allowed methods, and the runner checks it again before each
request. A hand-edited `DELETE` scenario cannot run unless `DELETE` is also allowed in the suite.

Read [Why tests are safe by default](../explanation/safety-model.md) for the reason behind this
two-step check.
