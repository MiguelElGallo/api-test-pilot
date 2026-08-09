# Report formats

Every completed run writes three files in the report directory.

| File | Use |
| --- | --- |
| `report.json` | Complete, machine-readable result and the input for `analyze` and `notify`. |
| `junit.xml` | Test result for CI systems that understand JUnit XML. |
| `report.html` | Self-contained report for a person to open in a browser. |

## JSON

The JSON report contains:

| Field | Type | Meaning |
| --- | --- | --- |
| `started_at` | Date and time | UTC start time. |
| `finished_at` | Date and time | UTC finish time. |
| `base_url` | String | Tested server. |
| `total` | Integer | Number of scenarios. |
| `passed` | Integer | Passed scenarios. |
| `failed` | Integer | Failed scenarios. |
| `results` | List | One result for every scenario. |
| `ai_analysis` | String or `null` | Optional GitHub Copilot failure analysis. |

Each result contains the full scenario plus `passed`, `status_code`, `duration_ms`, `error`, and `response_excerpt`. The response excerpt is limited to 1,000 characters.

## JUnit XML

The file contains one `testsuite` named `api-test-pilot` and one `testcase` per scenario. The category appears in the class name. A failed case contains its error and response excerpt.

## HTML

The HTML report has no external assets. It shows the target, total counts, one table row per scenario, and optional AI-assisted failure analysis.

Request credentials are not written to any report.
