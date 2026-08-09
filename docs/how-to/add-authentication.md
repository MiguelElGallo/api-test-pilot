# Add authentication

API Test Pilot reads supported security schemes from OpenAPI and Postman. It saves the name of an
environment variable, never the secret itself.

## Find the generated variable name

After `init`, open `.api-test-pilot/config.yaml`:

```yaml
authentication:
  BearerAuth: API_TEST_AUTH_BEARERAUTH
```

`BearerAuth` is the name in the API specification. `API_TEST_AUTH_BEARERAUTH` is the environment
variable that must contain the real token.

## Run locally with a bearer token

Set the value only for the current terminal session:

```bash
export API_TEST_AUTH_BEARERAUTH='replace-with-your-token'
uv run --no-sync api-test-pilot run --config .api-test-pilot/config.yaml
```

The runner adds `Authorization: Bearer ...` immediately before the request. The token is not added
to the scenario file or reports.

## Add the GitHub Actions secret

Create a repository secret with the same name:

```bash
gh secret set API_TEST_AUTH_BEARERAUTH
```

Enter the token when GitHub CLI asks for it. The generated workflow already maps the secret to the
environment variable.

## Use another supported scheme

The value format depends on the scheme:

| Scheme | Environment value |
| --- | --- |
| Bearer, OAuth 2, OpenID Connect | The token only |
| HTTP basic | `username:password` |
| API key | The key only |

The specification decides whether an API key is sent as a header, query value, or cookie.

If none of an operation's allowed authentication choices is configured, the scenario fails before
any network request is sent.

See [Environment variables](../reference/environment-variables.md) for all secret names used by the
tool and workflow.
