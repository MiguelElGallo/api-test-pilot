"""Resolve secret environment bindings into ephemeral HTTP request authentication."""

from __future__ import annotations

import base64
import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from api_test_pilot.models import (
    AuthenticationKind,
    AuthenticationScheme,
    Scenario,
)


class AuthenticationError(RuntimeError):
    """Indicate that required authentication cannot be applied safely."""


@dataclass(frozen=True, slots=True)
class RequestAuthentication:
    """Ephemeral request values after applying one security alternative."""

    headers: dict[str, str]
    query: dict[str, Any]
    cookies: dict[str, str]


def _apply_scheme(
    scheme: AuthenticationScheme,
    secret: str,
    *,
    headers: dict[str, str],
    query: dict[str, Any],
    cookies: dict[str, str],
) -> None:
    """Apply one resolved credential without retaining it in the scenario model."""
    if scheme.kind == AuthenticationKind.API_KEY:
        parameter_name = scheme.parameter_name or "X-API-Key"
        if scheme.location == "query":
            query[parameter_name] = secret
        elif scheme.location == "cookie":
            cookies[parameter_name] = secret
        else:
            headers[parameter_name] = secret
        return
    if scheme.kind == AuthenticationKind.HTTP_BASIC:
        encoded = base64.b64encode(secret.encode()).decode()
        headers["Authorization"] = f"Basic {encoded}"
        return
    if scheme.kind in {
        AuthenticationKind.HTTP_BEARER,
        AuthenticationKind.OAUTH2,
        AuthenticationKind.OPENID_CONNECT,
    }:
        headers["Authorization"] = f"Bearer {secret}"
        return
    raise AuthenticationError(f"Unsupported authentication kind: {scheme.kind}")


def resolve_authentication(
    scenario: Scenario,
    schemes: Mapping[str, AuthenticationScheme],
    *,
    environment: Mapping[str, str] | None = None,
) -> RequestAuthentication:
    """Select the first satisfiable security alternative and apply its credentials."""
    headers = dict(scenario.headers)
    query: dict[str, Any] = dict(scenario.query)
    cookies: dict[str, str] = {}
    if not scenario.security:
        return RequestAuthentication(headers, query, cookies)
    values = environment if environment is not None else os.environ
    missing_variables: set[str] = set()
    for requirement in scenario.security:
        resolved: list[tuple[AuthenticationScheme, str]] = []
        for name in requirement:
            scheme = schemes.get(name)
            if scheme is None:
                raise AuthenticationError(
                    f"Scenario references undefined authentication scheme '{name}'"
                )
            secret = values.get(scheme.environment_variable, "")
            if not secret:
                missing_variables.add(scheme.environment_variable)
                break
            resolved.append((scheme, secret))
        else:
            for scheme, secret in resolved:
                _apply_scheme(
                    scheme,
                    secret,
                    headers=headers,
                    query=query,
                    cookies=cookies,
                )
            return RequestAuthentication(headers, query, cookies)
    missing = ", ".join(sorted(missing_variables)) or "unknown authentication variables"
    raise AuthenticationError(f"Required authentication is not configured: {missing}")
