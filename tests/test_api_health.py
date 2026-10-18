"""Integration tests for FastAPI application skeleton and health diagnostic endpoints."""

from unittest.mock import MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from icarus_api import create_app
from icarus_core.persistence import DatabaseManager


@pytest.mark.asyncio
async def test_health_liveness_endpoint_returns_ok_and_metadata() -> None:
    """GET /health should return 200 OK with status, version, and uptime."""
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["version"] == "0.1.0"
        assert isinstance(data["uptime_seconds"], (int, float))
        assert data["uptime_seconds"] >= 0


@pytest.mark.asyncio
async def test_health_readiness_returns_ok_when_database_is_connected() -> None:
    """GET /health/ready should return 200 OK when the database engine is reachable."""
    db_manager = DatabaseManager("sqlite:///:memory:")
    app = create_app(db_manager=db_manager)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["database"] == "connected"
        assert data["version"] == "0.1.0"
        assert isinstance(data["uptime_seconds"], (int, float))


@pytest.mark.asyncio
async def test_health_readiness_returns_503_when_database_is_disconnected() -> None:
    """GET /health/ready should return 503 Service Unavailable when database ping fails."""
    mock_db = MagicMock(spec=DatabaseManager)
    mock_db.is_connected.return_value = False
    mock_db.close.return_value = None

    app = create_app(db_manager=mock_db)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health/ready")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "degraded"
        assert data["database"] == "disconnected"
        assert data["version"] == "0.1.0"
