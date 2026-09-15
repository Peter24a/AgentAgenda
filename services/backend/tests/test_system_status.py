import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_and_root(client: AsyncClient):
    res_h = await client.get("/health")
    assert res_h.status_code == 200
    assert res_h.json()["status"] == "healthy"

    res_root = await client.get("/")
    assert res_root.status_code == 200
    assert res_root.json()["status"] == "online"
    assert "llm_model" in res_root.json()


@pytest.mark.asyncio
async def test_system_status_subsystems(client: AsyncClient):
    res = await client.get("/v1/status")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] in ("healthy", "degraded")
    assert data["sync_schema_version"] == 1
    assert data["database"]["status"] == "connected"
    assert data["storage"]["status"] == "ready"
    assert data["worker"]["status"] in ("active", "offline")
    assert "llm" in data
    assert "timestamp" in data
