---
hide:
  - navigation
---

# API tests from one specification

API Test Pilot reads an OpenAPI, Swagger, or supported Postman file and creates API tests you can
run on your computer and in GitHub Actions.

These files are **API specifications**: they describe the available requests and responses in a
format that tools can read.

It creates three kinds of checks:

- **Functional** checks send a normal request.
- **Negative** checks send a request that should be rejected.
- **Edge** checks use values near documented limits.

You get the same test plan in both places, plus JSON, JUnit, and HTML reports.

[Run the first tutorial](tutorials/test-a-public-api.md){ .md-button .md-button--primary }
[View the command reference](reference/command-line.md){ .md-button }

## Find your way

<div class="grid cards" markdown>

-   **Learn by doing**

    ---

    Start with a public API. Generate three tests and read the result.

    [Open the tutorial](tutorials/index.md)

-   **Finish a task**

    ---

    Change the target, add a secret, allow a write request, or send a notification.

    [Choose a how-to guide](how-to/index.md)

-   **Look up a detail**

    ---

    Check every command, setting, file format, and environment variable.

    [Open the reference](reference/index.md)

-   **Understand a decision**

    ---

    Learn how tests are generated, why write requests are blocked, and where AI fits.

    [Read the explanation](explanation/index.md)

</div>

## What `init` creates

One command creates the files used by your computer and GitHub Actions:

```console
$ uv run --no-sync api-test-pilot init --spec openapi.yaml
Initialized .api-test-pilot/config.yaml, generated-scenarios.yaml, and .github/workflows/api-regression.yml with 3 safe scenarios
```

The configuration stores locations and policy. It does not store secret values.

!!! note "Safe first run"

    New projects allow only `GET`, `HEAD`, and `OPTIONS`. A `POST`, `PUT`, `PATCH`, or `DELETE`
    request runs only after you allow that method.
