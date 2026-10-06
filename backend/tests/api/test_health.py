import pytest
from httpx import AsyncClient
from unittest.mock import patch

pytestmark = pytest.mark.asyncio

async def test_liveness_check(async_client: AsyncClient):
    response = await async_client.get("/api/v1/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

async def test_readiness_check_success(async_client: AsyncClient):
    # This will test actual connectivity to the running Docker containers
    response = await async_client.get("/api/v1/health/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["database"] is True
    assert data["redis"] is True

@patch("app.api.routes.health.check_db_connection")
async def test_readiness_check_db_failure(mock_check_db, async_client: AsyncClient):
    mock_check_db.return_value = False
    
    response = await async_client.get("/api/v1/health/ready")
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "unavailable"
    assert data["database"] is False
    # Redis might still be true if the actual container is up

@patch("app.api.routes.health.check_redis_connection")
async def test_readiness_check_redis_failure(mock_check_redis, async_client: AsyncClient):
    mock_check_redis.return_value = False
    
    response = await async_client.get("/api/v1/health/ready")
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "unavailable"
    assert data["redis"] is False
