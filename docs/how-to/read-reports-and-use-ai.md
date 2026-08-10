# Read reports and use AI

Every run writes the same result in three formats. GitHub Copilot can add suggestions or explain
failures, but the tests do not depend on it. In GitHub Actions, the deterministic regression runs
before the optional AI job; an unavailable AI service cannot change the pass or fail result.

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
the generated file. Scheduled and manually started workflows request this advice automatically on
a best-effort basis. Download the `api-regression-ai-advice` artifact and open
`ai-reports/ai-generation-advice.txt` to read it.

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

In GitHub Actions, Copilot runs only for scheduled or manually started workflows. It runs in a
separate best-effort job after regression, with its own `copilot-requests: write` permission. Pull
request runs do not give the regression command a Copilot token.

## Enable failure analysis in GitHub Actions

Failure analysis is off by default because it can send up to 1,000 characters from each failed API
response to Copilot.

For a manual run, open the generated **API regression** workflow, choose **Run workflow**, and enable
the `analyze_failures` input. For scheduled runs, create this repository Actions variable:

```text
API_TEST_PILOT_AI_FAILURE_ANALYSIS=true
```

Generation advice still runs when failure analysis is off. When enabled, failure analysis is saved
in the `api-regression-ai-advice` artifact under `ai-reports/ai-failure-analysis.txt`.

See [Where AI helps](../explanation/ai-boundary.md) for the data sent to Copilot and the limits of
the analysis.
