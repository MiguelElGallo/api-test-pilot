"""End-to-end generated regression coverage against the bundled FastAPI service."""

from __future__ import annotations

import socket
from collections.abc import Iterator
from contextlib import contextmanager
from threading import Thread
from time import monotonic, sleep

import httpx
import uvicorn

from api_test_pilot.contracts import parse_openapi
from api_test_pilot.example_api import app
from api_test_pilot.generation import generate_suite
from api_test_pilot.runner import run_suite


@contextmanager
def _example_server() -> Iterator[str]:
    """Run the example API on a pre-bound ephemeral localhost socket."""
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    host, port = listener.getsockname()
    server = uvicorn.Server(
        uvicorn.Config(app, log_level="warning", access_log=False, lifespan="off")
    )
    thread = Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    try:
        deadline = monotonic() + 5
        while not server.started:
            if not thread.is_alive():
                raise RuntimeError("Example API server stopped before it became ready")
            if monotonic() >= deadline:
                raise TimeoutError("Example API server did not become ready within five seconds")
            sleep(0.01)
        yield f"http://{host}:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        if listener.fileno() != -1:
            listener.close()


def test_generated_suite_passes_against_example_api() -> None:
    """Generated functional, negative, and edge scenarios should all pass live."""
    with _example_server() as base_url:
        with httpx.Client(base_url=base_url) as client:
            contract = parse_openapi(client.get("/openapi.json").json())
        suite = generate_suite(
            contract,
            source=f"{base_url}/openapi.json",
            base_url=base_url,
            allowed_methods=["GET", "POST"],
        )
        summary = run_suite(suite)

    assert summary.total == len(contract.operations) * 3
    assert summary.failed == 0
    assert summary.passed == summary.total
