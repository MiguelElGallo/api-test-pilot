# Documentation peer review

This record covers the Zensical documentation added for API Test Pilot. Each review used two passes:

1. **Purpose:** the page must serve one Diátaxis need—learning, completing a task, looking up facts, or understanding a design choice.
2. **Clarity and evidence:** the language must stay direct, define necessary terms, match the implementation, and avoid claims that were not checked.

## Information architecture review

| Section | Review result | Evidence |
| --- | --- | --- |
| Home | Pass | Defines an API specification and the three scenario types, then routes readers to the four sections. It does not try to replace them. |
| Tutorials | Pass | The index stays learning-focused. The Postman Echo tutorial builds one complete result in order and ends with a real 3/3 run. |
| How-to guides | Pass | Each page starts from a clear goal: change a target, add authentication, allow writes, read reports/use AI, or send notifications. Background design was moved to Explanation. |
| Reference | Pass | Commands, configuration, supported inputs, suite fields, reports, and environment variables are described as exact facts. Task steps link back to How-to or Tutorials. |
| Explanation | Pass | The pages explain generation, safety, shared configuration, and the AI boundary. Command recipes and complete field lists remain in their own sections. |

## Page review

| Page or page group | Implementation check | Clarity check | Result |
| --- | --- | --- | --- |
| `docs/index.md` | Generated files and safe methods match CLI defaults. | “API specification,” functional, negative, and edge are defined on first use. | Pass |
| `docs/tutorials/index.md` | Links to the working example. | Gives one learning path without extra setup choices. | Pass |
| `docs/tutorials/test-a-public-api.md` | Commands were run against Postman Echo; configuration, three scenarios, report paths, and 3/3 counts were read back. | Each step shows an observable result and explains only the new idea needed for that step. | Pass |
| `docs/how-to/point-to-another-api.md` | Options match `init` and `generate`; local paths and URLs are supported. | Starts from the target-change task and keeps alternatives short. | Pass |
| `docs/how-to/add-authentication.md` | Scheme names, generated environment names, and GitHub secret use match generation and authentication code. | Separates secret names from secret values in plain language. | Pass |
| `docs/how-to/allow-write-requests.md` | Method checks match generation and runner policy. | Replaced the less familiar word “allowlist” with “list of allowed methods.” | Pass |
| `docs/how-to/read-reports-and-use-ai.md` | JSON, JUnit, HTML, `analyze`, and `--ai-analysis` behavior match the CLI and report writers. | Separates factual results from optional AI advice. | Pass |
| `docs/how-to/send-notifications.md` | Slack and complete SMTP settings match notification code and the generated workflow. | Uses copy-ready secret names and states when no channel is called. | Pass |
| `docs/reference/command-line.md` | Compared with Typer command definitions and live `--help` output. | Uses short meanings and records exit behavior without procedural detours. | Pass |
| `docs/reference/project-configuration.md` | Every Pydantic field, default, and unknown-field rule is represented. | Tables use “Meaning” instead of internal model terms. | Pass |
| `docs/reference/supported-specifications.md` | Compared with OpenAPI and Postman normalization code, including rejected Postman features. | Supported features and limits are separate and explicit. | Pass |
| `docs/reference/scenario-suite.md` | Compared with `ScenarioSuite`, `Scenario`, `ExpectedResponse`, and authentication models. | Field descriptions stay concise; OAuth token behavior is stated directly. | Pass |
| `docs/reference/report-formats.md` | Compared with JSON, JUnit, HTML writers and the 1,000-character response limit. | Gives each format one clear use. | Pass |
| `docs/reference/environment-variables.md` | Compared with generated auth names, Copilot discovery, Slack, and SMTP settings. | Corrected the prefix to `API_TEST_AUTH_` during review. | Pass |
| `docs/explanation/how-generation-works.md` | Flow and value choices match loader, normalization, generation, runner, validation, and reports. | Defines “deterministic”; the diagram was changed from wide to vertical after visual review. | Pass |
| `docs/explanation/safety-model.md` | Checks method enforcement, secret resolution, Postman script rejection, and report contents. | States both what the controls prevent and what they cannot guarantee. | Pass |
| `docs/explanation/one-configuration.md` | Matches the generated workflow’s `generate --config` and `run --config` calls. | Explains configuration drift without turning into setup instructions. | Pass |
| `docs/explanation/ai-boundary.md` | Compared with Copilot request payloads and workflow event guards. | Makes advice, factual results, and the response-data privacy limit distinct. | Pass |

## Problems found and fixed during review

- The checked-in example configuration occupied `.api-test-pilot/config.yaml`, so the documented default `init` command could not work in a fresh clone. The repository’s own CI target moved to `.api-test-pilot/ci.yaml`.
- The tutorial originally implied that the ignored generated suite should be committed. It now says to commit the configuration and workflow; CI regenerates the suite.
- The fallback negative scenario described itself as a normal path. It now says that it requests an unknown resource and expects a not-found response.
- Postman raw text was accepted by code while the documented safe subset said JSON. The parser now rejects non-JSON raw bodies, with a regression test.
- The first visual build showed unrendered icon shortcodes. They were removed instead of requiring readers to understand decorative syntax.
- The first generation diagram was too wide to read comfortably. It now flows from top to bottom.

## Verification record

| Check | Result |
| --- | --- |
| Real public tutorial run | `3/3` passed against `https://postman-echo.com`; raw capture is in `docs/assets/captures/postman-echo.txt`. |
| Zensical strict build | Pass: `No issues found`. |
| Desktop visual review | Pass: navigation, cards, tutorial steps, code blocks, and diagrams rendered correctly. |
| Mobile visual review | Pass at 390 × 844; no horizontal page overflow. |
| Ruff lint and format | Pass. |
| ty type check | Pass. |
| pytest | Pass: 58 tests, 85.44% coverage. |

GitHub Actions and the published Pages URL are checked again after the pull request is merged.
