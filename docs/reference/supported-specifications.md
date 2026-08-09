# Supported specifications

API Test Pilot reads JSON or YAML from a local file or an HTTP/HTTPS URL. The document root must be an object.

## OpenAPI and Swagger

Supported versions:

- OpenAPI 3.x
- Swagger/OpenAPI 2.x

Supported details:

- `GET`, `POST`, `PUT`, `PATCH`, `DELETE`, `HEAD`, and `OPTIONS` operations
- path, query, and header parameters
- JSON request bodies and Swagger body parameters
- numeric response status codes
- response format, JSON Schema rules for the JSON shape and values, and documented headers
- local `$ref` JSON pointers
- API key, HTTP Basic, HTTP Bearer, OAuth 2, and OpenID Connect security schemes

For OpenAPI 3, the first `servers` entry is used. Every variable in that URL must have a default. For Swagger 2, the URL comes from the first scheme, `host`, and `basePath`.

Remote `$ref` values are left unchanged. Response entries such as `default` and status ranges such as `2XX` are not turned into exact status checks.

## Postman

Supported collection versions:

- Postman Collection v2.0
- Postman Collection v2.1

Supported details:

- requests inside nested folders
- collection variables and values supplied with `--variable`
- query parameters and non-authentication headers
- raw bodies that contain valid JSON
- collection-level and request-level Bearer, Basic, and API-key authentication
- saved response status codes

The following features are rejected with a clear error:

- pre-request and test scripts
- unresolved `{{variables}}`
- form-data, URL-encoded, file, GraphQL, or other non-raw body modes
- raw bodies that are not valid JSON
- OAuth 1, OAuth 2, Digest, Hawk, NTLM, and AWS Signature authentication
- a literal `Authorization` header without supported Postman authentication settings

Postman folder-level authentication is not inherited. Move authentication to the collection or request before generating tests.
