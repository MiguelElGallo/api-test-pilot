"""Deterministic FastAPI fixture used by local and CI regression tests."""

from __future__ import annotations

from typing import Annotated

from fastapi import FastAPI, Query
from pydantic import BaseModel, Field

app = FastAPI(
    title="API Test Pilot Example",
    version="1.0.0",
    description="A deterministic API contract used to demonstrate generated regression tests.",
)


class Item(BaseModel):
    """An example inventory item accepted and returned by the service."""

    name: str = Field(min_length=1, max_length=80, examples=["flight recorder"])
    quantity: int = Field(ge=0, le=10_000, examples=[3])


@app.get("/health", operation_id="health_check")
def health_check() -> dict[str, str]:
    """Return a simple service readiness signal."""
    return {"status": "ok"}


@app.get("/items/{item_id}", operation_id="get_item")
def get_item(
    item_id: int,
    verbose: Annotated[bool, Query(description="Include an explanatory note.")] = False,
) -> dict[str, object]:
    """Return a stable example item for any positive identifier."""
    return {
        "id": item_id,
        "name": "flight recorder",
        "quantity": 3,
        "note": "generated fixture" if verbose else None,
    }


@app.post("/items", response_model=Item, status_code=201, operation_id="create_item")
def create_item(item: Item) -> Item:
    """Echo a validated item to demonstrate request-body scenarios."""
    return item
