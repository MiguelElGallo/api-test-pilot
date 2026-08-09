"""End-to-end generated regression coverage against the bundled FastAPI service."""

from __future__ import annotations

from fastapi.testclient import TestClient

from api_test_pilot.contracts import parse_openapi
from api_test_pilot.example_api import app
from api_test_pilot.generation import generate_suite
from api_test_pilot.runner import run_suite


def test_generated_suite_passes_against_example_api() -> None:
    """Generated functional, negative, and edge scenarios should all pass live."""
    with TestClient(app) as client:
        contract = parse_openapi(client.get("/openapi.json").json())
        suite = generate_suite(contract, source="in-process", base_url="http://testserver")
        summary = run_suite(suite, client=client)

    assert summary.total == len(contract.operations) * 3
    assert summary.failed == 0
    assert summary.passed == summary.total
