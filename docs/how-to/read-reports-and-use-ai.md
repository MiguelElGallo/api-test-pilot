# Read reports and use AI

Every run writes the same result in three formats. GitHub Copilot can add suggestions or explain
failures, but the tests do not depend on it.

## Open the reports

Run the suite:

```bash
uv run --no-sync api-test-pilot run --config .api-test-pilot/config.yaml
```

Then choose the format you need:

- Open `reports/report.html` to read the result in a browser.
- Read `reports/report.json` from another program.
- Give `reports/junit.xml` to a test report viewer.

The command exits with status `1` when any scenario fails. GitHub Actions uses that status to mark
the regression step as failed after it uploads the reports.

## Ask for test ideas

Install and sign in to GitHub Copilot CLI. Then add `--ai` while generating:

```bash
copilot login
uv run --no-sync api-test-pilot generate \
  --config .api-test-pilot/config.yaml \
  --ai
```

The normal suite is generated first. Copilot's suggestions are printed separately and do not change
the generated file.

## Analyze failures during a run

```bash
uv run --no-sync api-test-pilot run \
  --config .api-test-pilot/config.yaml \
  --ai-analysis
```

## Analyze an existing report

Use this when the tests already ran:

```bash
uv run --no-sync api-test-pilot analyze --report reports/report.json
```

The command updates the JSON and HTML report set with the analysis. It does nothing when all tests
passed.

In GitHub Actions, Copilot runs only for scheduled or manually started workflows. Pull request runs
do not give the regression command a Copilot token.

See [Where AI helps](../explanation/ai-boundary.md) for the data sent to Copilot and the limits of
the analysis.
