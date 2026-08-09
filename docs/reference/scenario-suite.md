# Scenario suite

Generation writes a YAML file named `generated-scenarios.yaml` by default. JSON input is also accepted by `run`.

```yaml
schema_version: "2.0"
source: examples/postman-echo.collection.json
base_url: https://postman-echo.com
execution:
  allowed_methods: [GET, HEAD, OPTIONS]
authentication: {}
scenarios: []
```

Unknown fields are rejected.

## Suite fields

| Field | Type | Meaning |
| --- | --- | --- |
| `schema_version` | String | Scenario format version. The current value is `"2.0"`. |
| `source` | String | Specification path or URL used during generation. |
| `base_url` | String | Server used for requests. |
| `execution.allowed_methods` | String list | Methods that the runner will accept. |
| `authentication` | Object | Secret-free runtime bindings for security schemes. |
| `scenarios` | List | Generated requests and expected responses. |

## Scenario fields

| Field | Type | Meaning |
| --- | --- | --- |
| `identifier` | String | Stable scenario name used in reports. |
| `name` | String | Human-readable name. |
| `category` | String | `functional`, `negative`, or `edge`. |
| `method` | String | HTTP method. |
| `path` | String | Request path, joined to `base_url`. |
| `headers` | String map | Non-secret request headers. |
| `query` | Object | Query parameters. |
| `body` | Any JSON value or `null` | Request body. |
| `expected_statuses` | Integer list | Accepted response status codes. |
| `expected_responses` | List | Detailed checks selected by actual status code. |
| `security` | List of string lists | Alternative security-scheme groups from the specification. |
| `description` | String | Reason for the scenario. |

## Expected response fields

| Field | Type | Meaning |
| --- | --- | --- |
| `status_code` | Integer | Status to which this detailed check applies. |
| `media_type` | String or `null` | Required response media type. Parameters such as `charset` do not affect comparison. |
| `response_schema` | Object or `null` | JSON Schema used to validate a JSON response. |
| `headers` | String list | Response headers that must be present. Header-name comparison is case-insensitive. |

## Authentication binding fields

Each key in `authentication` is a security-scheme name.

| Field | Type | Meaning |
| --- | --- | --- |
| `kind` | String | `api_key`, `http_basic`, `http_bearer`, `oauth2`, or `openid_connect`. |
| `environment_variable` | String | Environment variable read immediately before the request. |
| `location` | String or `null` | API-key location, normally `header` or `query`. |
| `parameter_name` | String or `null` | API-key header or query name. |

OAuth 2 and OpenID Connect bindings accept a ready-to-use bearer token. API Test Pilot does not perform an interactive login or token exchange.
