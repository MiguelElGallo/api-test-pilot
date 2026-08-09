# Architecture

API Test Pilot keeps contract parsing, strategy generation, HTTP execution, provider integrations,
and output adapters independent. This lets teams add a new contract format or report destination
without changing the runner.

```mermaid
flowchart LR
    A["OpenAPI / Swagger"] --> L["Contract loader"]
    B["Postman collection"] --> L
    L --> N["Normalized operations"]
    N --> G["Deterministic strategies"]
    G --> F["Functional scenarios"]
    G --> X["Negative scenarios"]
    G --> E["Edge scenarios"]
    F --> R["HTTP runner"]
    X --> R
    E --> R
    R --> O["JSON / JUnit / HTML reports"]
    R --> AI["GitHub Models failure triage"]
    O --> S["Slack / SMTP notifications"]
    AI --> O
```

## Cohesion boundaries

- `loaders` owns retrieval and JSON/YAML decoding.
- `contracts` owns format detection and normalization.
- `generation` owns deterministic scenario strategies.
- `runner` owns HTTP execution and observed outcomes.
- `ai` owns the optional GitHub Models boundary.
- `reporting` owns JSON, JUnit XML, and HTML serialization.
- `notifications` owns Slack and SMTP delivery.
- `cli` composes those modules without embedding domain logic.

AI is additive: deterministic test generation and execution work offline. Failure payloads exclude
request headers and bodies to reduce the chance of transmitting credentials or sensitive data.
