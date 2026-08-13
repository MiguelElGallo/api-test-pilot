# Command line

The program is installed as `api-test-pilot`. Run it without a command to see the command list.

```console
api-test-pilot [OPTIONS] COMMAND [ARGS]...
```

## `init`

Create a project configuration, a generated scenario suite, and a GitHub Actions workflow.

```console
api-test-pilot init --spec SOURCE [OPTIONS]
```

| Option | Default | Meaning |
| --- | --- | --- |
| `--spec TEXT` | Required | Local path or HTTP/HTTPS URL for an OpenAPI, Swagger, or Postman file. |
| `--base-url TEXT` | From the specification | Replace the server URL. Required when a local OpenAPI or Swagger file uses a relative server URL. |
| `--allow-method TEXT` | `GET`, `HEAD`, `OPTIONS` | Allow one HTTP method. Repeat the option to allow more than one. |
| `--variable TEXT` | None | Set one non-secret Postman variable as `NAME=VALUE`. Repeat as needed. |
| `--config PATH` | `.api-test-pilot/config.yaml` | Configuration file to create. |
| `--suite PATH` | `generated-scenarios.yaml` | Scenario file to create. |
| `--workflow PATH` | `.github/workflows/api-regression.yml` | GitHub Actions workflow to create. |
| `--force` | Off | Replace existing output files. |

`init` stops before writing anything when an output file already exists and `--force` is not set.

## `generate`

Create functional, negative, and edge scenarios without running them.

```console
api-test-pilot generate [OPTIONS]
```

| Option | Default | Meaning |
| --- | --- | --- |
| `--spec TEXT` | None | Specification path or URL. Required when `--config` is not used. |
| `--config PATH` | None | Read the target, methods, authentication names, and output paths from a project configuration. |
| `--output PATH` | From configuration or `generated-scenarios.yaml` | Scenario file to write. |
| `--base-url TEXT` | From the specification | Replace the server URL. Required for a local OpenAPI or Swagger file with a relative server URL; valid only with `--spec`. |
| `--allow-method TEXT` | Safe methods | Allow one HTTP method. Repeat as needed. Valid only with `--spec`. |
| `--variable TEXT` | None | Set one non-secret Postman variable. Valid only with `--spec`. |
| `--ai` | Off | Print optional GitHub Copilot suggestions after fixed-rule generation. |

`--config` cannot be combined with `--spec`, `--base-url`, `--allow-method`, or `--variable`.

## `run`

Run a scenario suite and write all report formats.

```console
api-test-pilot run [OPTIONS]
```

| Option | Default | Meaning |
| --- | --- | --- |
| `--suite PATH` | From configuration or `generated-scenarios.yaml` | YAML or JSON scenario file to run. |
| `--config PATH` | None | Read suite and report paths from a project configuration. |
| `--report-dir PATH` | From configuration or `reports` | Directory for the reports. |
| `--ai-analysis` | Off | Ask GitHub Copilot to analyze failed scenarios. |
| `--allow-method TEXT` | Safe methods | Runtime-authorize a method for a direct suite run. Repeat as needed; cannot be combined with `--config`. |

The exit code is `1` when any scenario fails. A completed run always writes JSON, JUnit XML, and HTML reports before returning that code.
Authenticated suites must run with `--config`. Their authentication bindings and base URL must match
the trusted project configuration. `init` pins the resolved base URL for this purpose.

## `analyze`

Add GitHub Copilot failure analysis to an existing report set.

```console
api-test-pilot analyze [--report PATH]
```

`--report` defaults to `reports/report.json`. The command rewrites all three reports in the same directory. It does nothing when the report has no failures. It returns exit code `2` when GitHub Copilot CLI is unavailable.

## `notify`

Send the result from a completed JSON report to every configured channel.

```console
api-test-pilot notify [--report PATH]
```

`--report` defaults to `reports/report.json`. When no notification variables are set, the command prints `Notified: no configured channels`.
