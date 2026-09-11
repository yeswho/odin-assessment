import httpx
import pytest

from app.api.routes import get_service
from app.core.config import Settings
from app.main import create_app


@pytest.fixture
async def client(service):
    app = create_app(Settings(ai_mode="mock"))
    app.dependency_overrides[get_service] = lambda: service
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client
    await app.state.engine.dispose()


async def test_http_contract(client, payload):
    first = await client.post("/api/work-items", json=payload.model_dump(by_alias=True))
    assert first.status_code == 201
    item = first.json()["item"]
    assert item["externalId"] == payload.external_id
    assert "attemptToken" not in item
    assert (
        await client.post("/api/work-items", json=payload.model_dump(by_alias=True))
    ).status_code == 200
    path = f"/api/work-items/{item['id']}"
    assert (await client.patch(path + "/status", json={"status": "COMPLETED"})).status_code == 409
    analysed = await client.post(path + "/analyse")
    assert analysed.status_code == 200
    assert analysed.json()["analysis"]["recommendedAction"]
    assert (await client.get("/api/work-items?status=READY_FOR_REVIEW")).json()["total"] == 1
    assert (await client.patch(path + "/status", json={"status": "COMPLETED"})).status_code == 200
    assert (await client.post(path + "/retry")).status_code == 409


@pytest.mark.parametrize(
    "path",
    [
        "/api/work-items?limit=101",
        "/api/work-items?offset=-1",
        "/api/work-items?status=INVALID",
        "/api/work-items/not-a-uuid",
    ],
)
async def test_invalid_query_and_id(client, path):
    response = await client.get(path)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_validation_and_body_limit(client, payload):
    data = payload.model_dump(by_alias=True)
    assert (await client.post("/api/work-items", json={**data, "title": " "})).status_code == 422
    assert (
        await client.post("/api/work-items", json={**data, "status": "COMPLETED"})
    ).status_code == 422
    assert (await client.post("/api/work-items", content="x" * 65537)).status_code == 413
    assert (
        await client.post(
            "/api/work-items", content="{", headers={"Content-Type": "application/json"}
        )
    ).status_code == 422
