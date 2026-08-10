# Project configuration

The default project configuration is `.api-test-pilot/config.yaml`. Local commands and the generated GitHub Actions workflow read the same file.

```yaml
schema_version: "1.0"
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

Unknown fields are rejected.

## Top-level fields

| Field | Type | Default | Meaning |
| --- | --- | --- | --- |
| `schema_version` | String | `"1.0"` | Configuration format version. |
| `target` | Object | Required | Specification and target server settings. |
| `execution` | Object | Safe methods | Methods that generated scenarios may use. |
| `authentication` | Object | `{}` | Map from a specification security-scheme name to an environment-variable name. |
| `artifacts` | Object | Default paths | Generated suite and report locations. |

## `target`

| Field | Type | Default | Meaning |
| --- | --- | --- | --- |
| `specification` | String | Required | Local path or HTTP/HTTPS URL. |
| `base_url` | String or `null` | `null` | Server URL override. |
| `variables` | String map | `{}` | Non-secret values used to replace Postman `{{variables}}`. |

When `base_url` is set, it also supplies the Postman variable `baseUrl` unless `target.variables.baseUrl` is already set.

## `execution`

`allowed_methods` is a non-empty list of HTTP methods. Values are changed to uppercase and duplicates are removed. The default is:

```yaml
execution:
  allowed_methods: [GET, HEAD, OPTIONS]
```

## `authentication`

Keys must match security-scheme names in the specification. Values name environment variables; they never contain the secrets themselves.

```yaml
authentication:
  bearerAuth: API_TEST_BEARER_AUTH
  partnerKey: PARTNER_API_KEY
```

## `artifacts`

| Field | Type | Default | Meaning |
| --- | --- | --- | --- |
| `suite` | String | `generated-scenarios.yaml` | Generated YAML scenario file. |
| `reports` | String | `reports` | Directory for JSON, JUnit XML, and HTML reports. |

## Paths used by GitHub Actions

The configuration path passed to `init`, plus `artifacts.suite` and `artifacts.reports`, is written
into the generated workflow. Use project-relative POSIX paths such as `reports/api` or
`generated/scenarios.yaml`.

These paths cannot be empty, be `.` by itself, be absolute, start with `-`, use `..` or backslashes,
or contain control characters, single quotes, or GitHub expression characters (`$`, `{`, or `}`).
Generation stops before writing an unsafe workflow.
