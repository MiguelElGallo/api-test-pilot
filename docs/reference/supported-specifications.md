# Supported specifications

API Test Pilot reads JSON or YAML from a local file or an HTTP/HTTPS URL. The document root must be an object.

## OpenAPI and Swagger

Supported versions:

- OpenAPI 3.x
- Swagger/OpenAPI 2.x

Supported details:

- `GET`, `POST`, `PUT`, `PATCH`, `DELETE`, `HEAD`, and `OPTIONS` operations
- path, query, and header parameters
- `application/json` request bodies and Swagger body parameters
- compatible object `allOf` schemas, combined into one JSON request body
- numeric response status codes
- response format, JSON Schema rules for the JSON shape and values, and documented headers
- local `$ref` JSON pointers
- API key, HTTP Basic, HTTP Bearer, OAuth 2, and OpenID Connect security schemes

For OpenAPI 3, the first `servers` entry is used. Every variable in that URL must have a default.
For Swagger 2, the URL comes from the first scheme, `host`, and `basePath`. A relative server in a
remote specification is resolved against that specification's origin. A local specification with a
relative server requires an absolute `--base-url`.

Remote `$ref` values are never fetched. A remote reference in a request schema or parameter stops
generation and asks you to bundle the referenced schema into the specification with local `#/`
references. A remote reference in a response schema remains in the generated suite; when that
response is checked, the scenario records an explicit validation failure instead of fetching it.

Response entries such as `default` and status ranges such as `2XX` are not turned into exact status
checks.

Response media types are checked for every documented response. JSON Schema body validation applies
only when the received response is JSON.

The following OpenAPI and Swagger request features are rejected with a clear error:

- XML, multipart, form, `application/problem+json`, or other non-`application/json` request bodies
- unsupported or incompatible composed request schemas that cannot form a valid JSON body
- Swagger `formData` parameters

### Generated schema values

Generation has direct strategies for common schema details:

- `example`, `examples`, `default`, and `enum`
- `type`, object `properties`, `required`, array `items`, `minItems`, and `maxItems`
- `minimum`, `maximum`, `exclusiveMinimum`, and `exclusiveMaximum`
- `minLength`, `maxLength`, and the email `format`
- nullable types plus `allOf`, `oneOf`, and `anyOf` composition

Every generated functional and edge request body and parameter is checked against its source
schema. Constraints without a direct generation strategy, such as `pattern`, `const`, and
`multipleOf`, are still enforced. If a generated value does not meet one of those constraints,
generation stops with a clear validation error instead of writing an invalid positive test.

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

All absolute request URLs in one collection must use the same canonical HTTP(S) origin (scheme,
host, and port). They cannot embed a user name or password. Use `--base-url` when you want to send
the whole collection to a controlled test environment.

The following features are rejected with a clear error:

- pre-request and test scripts
- unresolved `{{variables}}`
- form-data, URL-encoded, file, GraphQL, or other non-raw body modes
- raw bodies that are not valid JSON
- OAuth 1, OAuth 2, Digest, Hawk, NTLM, and AWS Signature authentication
- a literal `Authorization` header without supported Postman authentication settings
- a collection that uses more than one origin
- an absolute request URL that is not HTTP(S) or embeds user credentials

Postman folder-level authentication is not inherited. Move authentication to the collection or request before generating tests.
