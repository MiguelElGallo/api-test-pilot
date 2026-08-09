# Why tests are safe by default

API tests send real requests. A useful default must prevent a first run from changing or deleting data.

## Reading is the default

New projects allow `GET`, `HEAD`, and `OPTIONS`. Methods that commonly change data—`POST`, `PUT`, `PATCH`, and `DELETE`—are excluded until a person adds them to the configuration.

This is a default, not a claim that every `GET` endpoint is harmless. The person who owns the target API still chooses the correct test server and data.

## The method rule is checked twice

Generation skips operations whose methods are not allowed. The suite also stores the allowed methods, and the runner checks the rule immediately before each request.

The second check matters because a generated YAML file can be edited. Adding a `DELETE` scenario by hand does not make it runnable unless `DELETE` is also allowed by the suite policy.

## Secrets stay outside generated files

The configuration and suite store environment-variable names, not credentials. A secret is read only when authentication is added to a request. Reports do not contain request headers or bodies.

This design does not make every response safe to share. A failed API can return private data in its response, and the report keeps up to the first 1,000 characters for diagnosis. Treat reports according to the data returned by the tested API.

## Postman code is not executed

Postman collections can contain JavaScript before or after requests. API Test Pilot rejects those scripts. Running copied code would make the effects of a test harder to see and would require a JavaScript environment inside the test tool.

The supported Postman path is intentionally smaller: saved requests, variables, JSON bodies, headers, examples, and supported authentication settings.

## Safe generation has limits

Safety rules reduce accidental damage; they cannot understand the business meaning of every endpoint. A read request may trigger work, and an allowed write request may use realistic examples from a specification.

For that reason, write tests belong on a disposable or controlled test server. Method approval, target selection, and restricted credentials work together; none of them is enough alone.
