"""Actual PostgreSQL integration tests, isolated in a unique temporary schema."""

import asyncio
import os
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from alembic import command
from alembic.config import Config
from app.api.routes import get_service
from app.core.config import Settings
from app.main import create_app
from app.models.work_item import WorkItem
from app.repositories.work_items import WorkItemRepository
from app.services.work_items import WorkItemService
from app.workflow.states import Status
from tests.conftest import VALID_ANALYSIS, StubProvider

pytestmark = pytest.mark.integration


@pytest.fixture
async def repository():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to run against PostgreSQL")
    schema = "test_odin_" + uuid4().hex
    admin = create_async_engine(url)
    async with admin.begin() as connection:
        await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(
        url, connect_args={"options": f"-csearch_path={schema}"}, pool_size=10, max_overflow=10
    )
    try:
        async with engine.begin() as connection:

            def migrate(sync_connection):
                config = Config("alembic.ini")
                config.attributes["connection"] = sync_connection
                command.upgrade(config, "head")

            await connection.run_sync(migrate)
        yield WorkItemRepository(async_sessionmaker(engine, expire_on_commit=False))
    finally:
        await engine.dispose()
        async with admin.begin() as connection:
            # Identifier is generated locally, never supplied by a caller.
            await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await admin.dispose()


async def test_concurrent_intake_has_one_row(repository, payload):
    results = await asyncio.gather(*(repository.create(payload) for _ in range(20)))
    assert sum(created for _, created in results) == 1
    assert len({item.id for item, _ in results}) == 1
    async with repository.sessions() as session:
        assert await session.scalar(select(func.count()).select_from(WorkItem)) == 1


async def test_only_one_analysis_claim_wins(repository, payload):
    item, _ = await repository.create(payload)
    results = await asyncio.gather(
        *(repository.claim(item.id, Status.RECEIVED, uuid4(), 60) for _ in range(10))
    )
    assert sum(result is not None for result in results) == 1
    assert (await repository.get(item.id)).attempts == 1


async def test_lease_recovery_and_stale_result_fencing(repository, payload):
    item, _ = await repository.create(payload)
    old_token, new_token = uuid4(), uuid4()
    await repository.claim(item.id, Status.RECEIVED, old_token, 60)
    async with repository.sessions.begin() as session:
        await session.execute(
            update(WorkItem).where(WorkItem.id == item.id).values(lease_expires_at=func.now())
        )
    await repository.recover_expired()
    assert (await repository.get(item.id)).error_code == "AI_INTERRUPTED"
    await repository.claim(item.id, Status.FAILED, new_token, 60)
    assert (
        await repository.finish(item.id, old_token, analysis=VALID_ANALYSIS, provider="stub")
        is None
    )
    result = await repository.finish(item.id, new_token, analysis=VALID_ANALYSIS, provider="stub")
    assert result.status == Status.READY_FOR_REVIEW
    assert result.attempts == 2


async def test_database_rejects_invalid_state_payload(repository, payload):
    item, _ = await repository.create(payload)
    with pytest.raises(IntegrityError):
        async with repository.sessions.begin() as session:
            await session.execute(
                update(WorkItem).where(WorkItem.id == item.id).values(status=Status.COMPLETED)
            )
    assert (await repository.get(item.id)).status == Status.RECEIVED


async def test_complete_is_atomic_and_terminal(repository, payload):
    service = WorkItemService(repository, StubProvider(), Settings(ai_mode="mock"))
    item = (await service.create(payload))["item"]
    await service.analyse(item.id)
    results = await asyncio.gather(*(repository.complete(item.id) for _ in range(5)))
    assert sum(result is not None for result in results) == 1
    assert (await service.get(item.id)).status == Status.COMPLETED


async def test_fastapi_with_real_postgres(repository, payload):
    settings = Settings(ai_mode="mock")
    app = create_app(settings)
    service = WorkItemService(repository, StubProvider(), settings)
    app.dependency_overrides[get_service] = lambda: service
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post("/api/work-items", json=payload.model_dump(by_alias=True))
            assert response.status_code == 201
            item_id = response.json()["item"]["id"]
            analysed = await client.post(f"/api/work-items/{item_id}/analyse")
            assert analysed.status_code == 200
            assert analysed.json()["analysis"] == VALID_ANALYSIS
            assert (await client.get("/api/work-items?status=READY_FOR_REVIEW")).json()[
                "total"
            ] == 1
    finally:
        await app.state.engine.dispose()
