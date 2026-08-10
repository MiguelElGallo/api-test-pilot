# Test a public API

In this tutorial, you will test the public Postman Echo API. It returns information about the
request it receives, which makes it useful for a first test run.

By the end, you will have:

- one project configuration;
- three generated test scenarios;
- a GitHub Actions workflow; and
- JSON, JUnit, and HTML reports from a real API run.

The commands below were run against `https://postman-echo.com` and produced a **3/3 pass** result.

## Before you start

You need:

- Python 3.12 or newer;
- [`uv`](https://docs.astral.sh/uv/); and
- a clone of the API Test Pilot repository.

Open a terminal in the repository folder. Install the locked dependencies:

```console
$ uv sync --all-extras --locked --no-editable
```

## Create the test project

The repository includes a small Postman collection for Postman Echo. Point `init` to that file:

```console
$ uv run --no-sync api-test-pilot init --spec examples/postman-echo.collection.json
Initialized .api-test-pilot/config.yaml, generated-scenarios.yaml, and .github/workflows/api-regression.yml with 3 safe scenarios
```

You now have these files:

```text
.api-test-pilot/config.yaml              # The target and safety settings
generated-scenarios.yaml                 # The requests and expected results
.github/workflows/api-regression.yml      # The same run for GitHub Actions
```

!!! info "What is a scenario?"

    A scenario is one request plus the result it should receive. It is the smallest test in a
    generated suite.

## Read the configuration

Open `.api-test-pilot/config.yaml`:

```yaml
schema_version: '1.0'
target:
  specification: examples/postman-echo.collection.json
  base_url: null
  variables: {}
execution:
  allowed_methods:
  - GET
  - HEAD
  - OPTIONS
authentication: {}
artifacts:
  suite: generated-scenarios.yaml
  reports: reports
```

The Postman file already contains `https://postman-echo.com`, so `base_url` can stay empty. The
allowed methods show that this first run cannot change data.

## Run the tests

Run the generated suite through the project configuration:

```console
$ uv run --no-sync api-test-pilot run --config .api-test-pilot/config.yaml
Regression result: 3/3 passed; reports: reports/report.json, reports/junit.xml, reports/report.html
```

This output was captured from the real public API. You can also inspect the
[complete terminal capture](../assets/captures/postman-echo.txt).

## See what was tested

The generated file contains one functional, one negative, and one edge scenario:

```yaml
- identifier: postman-0-echo-get-functional-happy-path
  category: functional
  method: GET
  path: /get
  expected_statuses: [200]

- identifier: postman-0-echo-get-negative-unknown-resource
  category: negative
  method: GET
  path: /get/__invalid__
  expected_statuses: [404]

- identifier: postman-0-echo-get-edge-boundary-values
  category: edge
  method: GET
  path: /get
  expected_statuses: [200]
```

The functional request uses the saved Postman value. The negative request asks for a path that
does not exist. The edge request sends a longer query value.

## Read the report

Open `reports/report.html` in a browser. It shows the target, totals, each scenario, its status, and
any error.

The JSON report confirms the real result:

```json
{
  "total": 3,
  "passed": 3,
  "failed": 0,
  "base_url": "https://postman-echo.com"
}
```

## Find the same run in GitHub Actions

Open `.github/workflows/api-regression.yml`. The workflow regenerates the suite from the same
configuration, runs it, uploads the reports, and sends notifications when you configure them.

Commit `.api-test-pilot/config.yaml` and `.github/workflows/api-regression.yml` to your branch.
GitHub recreates `generated-scenarios.yaml` during each run, so that file can stay ignored.

## What you learned

You started with one Postman file and produced local tests, CI automation, and three report formats.
The target and safety rules live in one configuration, so the local and GitHub runs stay together.

Next, use [Point to another API](../how-to/point-to-another-api.md) when you are ready to use your
own specification.
