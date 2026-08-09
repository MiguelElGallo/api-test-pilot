"""Tests for runtime authentication binding without secret persistence."""

from __future__ import annotations

import base64

import pytest

from api_test_pilot.authentication import AuthenticationError, resolve_authentication
from api_test_pilot.models import (
    AuthenticationKind,
    AuthenticationScheme,
    Scenario,
    ScenarioCategory,
)


def _scenario(*, security: list[list[str]]) -> Scenario:
    """Create a small secured scenario fixture."""
    return Scenario(
        identifier="secured",
        name="Secured",
        category=ScenarioCategory.FUNCTIONAL,
        method="GET",
        path="/secured",
        expected_statuses=[200],
        security=security,
        description="Checks authentication.",
    )


@pytest.mark.parametrize(
    ("location", "expected_collection"),
    [("header", "headers"), ("query", "query"), ("cookie", "cookies")],
)
def test_api_keys_are_applied_to_the_documented_location(
    location: str, expected_collection: str
) -> None:
    """API keys should be injected ephemerally into headers, queries, or cookies."""
    authentication = resolve_authentication(
        _scenario(security=[["ApiKey"]]),
        {
            "ApiKey": AuthenticationScheme(
                kind=AuthenticationKind.API_KEY,
                environment_variable="API_KEY",
                location=location,
                parameter_name="credential",
            )
        },
        environment={"API_KEY": "secret-value"},
    )

    assert getattr(authentication, expected_collection)["credential"] == "secret-value"


def test_bearer_and_basic_auth_use_authorization_header() -> None:
    """HTTP credentials should use standard authorization encodings."""
    bearer = resolve_authentication(
        _scenario(security=[["Bearer"]]),
        {
            "Bearer": AuthenticationScheme(
                kind=AuthenticationKind.HTTP_BEARER,
                environment_variable="TOKEN",
            )
        },
        environment={"TOKEN": "abc"},
    )
    basic = resolve_authentication(
        _scenario(security=[["Basic"]]),
        {
            "Basic": AuthenticationScheme(
                kind=AuthenticationKind.HTTP_BASIC,
                environment_variable="BASIC",
            )
        },
        environment={"BASIC": "user:password"},
    )

    assert bearer.headers["Authorization"] == "Bearer abc"
    assert basic.headers["Authorization"] == (
        f"Basic {base64.b64encode(b'user:password').decode()}"
    )


def test_authentication_selects_a_satisfied_alternative() -> None:
    """OpenAPI OR alternatives should use the first one with configured credentials."""
    authentication = resolve_authentication(
        _scenario(security=[["Missing"], ["Bearer"]]),
        {
            "Missing": AuthenticationScheme(
                kind=AuthenticationKind.HTTP_BEARER,
                environment_variable="MISSING",
            ),
            "Bearer": AuthenticationScheme(
                kind=AuthenticationKind.OAUTH2,
                environment_variable="TOKEN",
            ),
        },
        environment={"TOKEN": "available"},
    )

    assert authentication.headers["Authorization"] == "Bearer available"


def test_missing_or_undefined_authentication_fails_before_transport() -> None:
    """Missing configuration should produce precise errors without leaking values."""
    with pytest.raises(AuthenticationError, match="TOKEN"):
        resolve_authentication(
            _scenario(security=[["Bearer"]]),
            {
                "Bearer": AuthenticationScheme(
                    kind=AuthenticationKind.HTTP_BEARER,
                    environment_variable="TOKEN",
                )
            },
            environment={},
        )
    with pytest.raises(AuthenticationError, match="undefined authentication scheme"):
        resolve_authentication(_scenario(security=[["Unknown"]]), {}, environment={})


def test_public_scenario_preserves_existing_request_values() -> None:
    """Unsecured requests should keep their generated headers and query parameters."""
    scenario = _scenario(security=[]).model_copy(
        update={"headers": {"X-Test": "yes"}, "query": {"page": 1}}
    )

    authentication = resolve_authentication(scenario, {}, environment={})

    assert authentication.headers == {"X-Test": "yes"}
    assert authentication.query == {"page": 1}
