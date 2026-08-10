# Where AI helps

GitHub Copilot is optional. Test generation, request execution, response checks, and pass/fail results do not depend on it.

## Fixed rules produce the tests

The main suite comes from fixed generation rules. That gives code review and CI a repeatable result.

With `generate --ai`, GitHub Copilot receives a short summary containing the source format, base URL, and operation IDs, methods, and paths. It returns additional ideas as text. Those ideas do not change the generated suite automatically.

## Evidence supports failure analysis

With `run --ai-analysis` or `analyze`, GitHub Copilot receives only failed scenarios. Each item contains:

- scenario ID and category;
- method and path;
- expected and actual status;
- the recorded error; and
- up to 1,000 characters of the response.

Request headers and request bodies are excluded. The prompt also tells GitHub Copilot to treat response text as data, not as instructions.

The response excerpt can still contain sensitive data returned by the API. For that reason, failure
analysis in GitHub Actions is off by default. A person must enable the `analyze_failures` input for
a manual run, or a repository owner must set `API_TEST_PILOT_AI_FAILURE_ANALYSIS=true` for scheduled
runs. Teams testing private data should decide whether AI analysis is appropriate for that target.

## AI is advice, not authority

Generation advice is printed for a person to review. Failure analysis is stored beside the factual result. Neither can turn a failed scenario into a pass, send a new API request, or edit project files.

This boundary keeps the useful part of AI—finding missing ideas and grouping likely causes—without asking it to decide whether the regression passed.

## CI limits when Copilot runs

The generated GitHub Actions workflow runs the fixed-rule regression first. It installs and calls
GitHub Copilot CLI only in a separate best-effort job for scheduled or manually started runs.
Generation advice runs automatically in that job. Failure analysis runs only with the explicit
manual input or scheduled repository variable described above. Pull requests and normal pushes
still run the fixed-rule regression, but they do not send test context to Copilot. An unavailable
Copilot service is recorded as an AI limitation and cannot stop the factual regression result from
being published.
