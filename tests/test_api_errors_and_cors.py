"""Tests for CORS policy and structured JSON error handlers."""

import pytest
from fastapi import APIRouter
from httpx import ASGITransport, AsyncClient
from icarus_api import ApiSettings, create_app
from pydantic import BaseModel


class SampleBody(BaseModel):
    name: str
    count: int


dummy_router = APIRouter()


@dummy_router.post("/dummy-validation")
async def dummy_validation_endpoint(body: SampleBody) -> dict[str, str]:
    return {"name": body.name}


@dummy_router.get("/dummy-internal-error")
async def dummy_internal_error_endpoint() -> dict[str, str]:
    raise RuntimeError("Unexpected internal explosion")


@pytest.mark.asyncio
async def test_cors_headers_returned_for_allowed_origins() -> None:
    """CORS middleware should attach access-control headers for allowed origins."""
    settings = ApiSettings(cors_origins=["http://localhost:3000"])
    app = create_app(settings=settings)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health", headers={"Origin": "http://localhost:3000"})
        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"


@pytest.mark.asyncio
async def test_not_found_returns_normalized_json_error() -> None:
    """404 Not Found should return normalized error schema."""
    app = create_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/v1/does-not-exist")
        assert response.status_code == 404
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "not_found"
        assert isinstance(data["error"]["message"], str)


@pytest.mark.asyncio
async def test_validation_error_returns_normalized_json_error() -> None:
    """Request validation failure (422) should return normalized error schema."""
    app = create_app()
    app.include_router(dummy_router)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        payload = {"name": "test", "count": "not-an-int"}
        response = await client.post("/dummy-validation", json=payload)
        assert response.status_code == 422
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "validation_error"
        assert "details" in data["error"]


@pytest.mark.asyncio
async def test_unhandled_exception_returns_normalized_500_error() -> None:
    """Unhandled server errors (500) should return normalized error schema."""
    app = create_app()
    app.include_router(dummy_router)

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/dummy-internal-error")
        assert response.status_code == 500
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "internal_server_error"
        assert data["error"]["message"] == "An internal server error occurred"
