import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.ai.providers import ProviderError
from app.core.errors import AppError
from app.workflow.states import Status
from tests.conftest import VALID_ANALYSIS


async def test_duplicate_and_conflicting_delivery(service, payload):
    original = await service.create(payload)
    duplicate = await service.create(payload)
    assert original["created"] is True and duplicate["created"] is False
    assert duplicate["item"].id == original["item"].id
    with pytest.raises(AppError) as error:
        await service.create(payload.model_copy(update={"title": "Changed"}))
    assert error.value.code == "EXTERNAL_ID_CONFLICT"
    assert original["item"].title == payload.title


async def test_full_workflow_and_terminal_completion(service, payload):
    item = (await service.create(payload))["item"]
    with pytest.raises(AppError):
        await service.complete(item.id)
    with pytest.raises(AppError):
        await service.analyse(item.id, retry=True)
    assert (await service.analyse(item.id)).status == Status.READY_FOR_REVIEW
    assert (await service.complete(item.id)).status == Status.COMPLETED
    with pytest.raises(AppError):
        await service.analyse(item.id)
    with pytest.raises(AppError):
        await service.analyse(item.id, retry=True)


@pytest.mark.parametrize(
    "output",
    [
        None,
        "{invalid",
        {**VALID_ANALYSIS, "priority": "CRITICAL"},
        {"summary": "missing fields"},
        {**VALID_ANALYSIS, "summary": " "},
        {**VALID_ANALYSIS, "extra": "unexpected"},
    ],
)
async def test_invalid_ai_output_is_discarded(service, payload, output):
    async def analyse(*_):
        return output

    service.provider.analyse = analyse
    item = (await service.create(payload))["item"]
    result = await service.analyse(item.id)
    assert result.status == Status.FAILED
    assert result.error_code == "AI_INVALID_OUTPUT"
    assert result.analysis is None
    assert result.description == payload.description


async def test_provider_failure_then_successful_retry(service, payload):
    async def analyse(_, attempt):
        if attempt == 1:
            raise ProviderError("Provider unavailable. Retry this item.")
        return VALID_ANALYSIS

    service.provider.analyse = analyse
    item = (await service.create(payload))["item"]
    assert (await service.analyse(item.id)).error_code == "AI_UNAVAILABLE"
    retried = await service.analyse(item.id, retry=True)
    assert retried.status == Status.READY_FOR_REVIEW
    assert retried.attempts == 2 and retried.error_code is None


async def test_timeout_cancels_provider(service, payload):
    service.settings.ai_timeout_seconds = 0.01
    cancelled = asyncio.Event()

    async def analyse(*_):
        try:
            await asyncio.sleep(10)
        finally:
            cancelled.set()

    service.provider.analyse = analyse
    item = (await service.create(payload))["item"]
    result = await service.analyse(item.id)
    assert result.error_code == "AI_TIMEOUT" and cancelled.is_set()
    assert result.analysis is None


async def test_concurrent_analysis_calls_provider_once(service, payload):
    started, release = asyncio.Event(), asyncio.Event()
    calls = 0

    async def analyse(*_):
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return VALID_ANALYSIS

    service.provider.analyse = analyse
    item = (await service.create(payload))["item"]
    running = asyncio.create_task(service.analyse(item.id))
    await started.wait()
    with pytest.raises(AppError):
        await service.analyse(item.id)
    release.set()
    assert (await running).status == Status.READY_FOR_REVIEW
    assert calls == 1


async def test_interrupted_lease_is_retryable(service, payload):
    item = (await service.create(payload))["item"]
    await service.repository.claim(item.id, Status.RECEIVED, uuid4(), 60)
    item.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    assert (await service.analyse(item.id, retry=True)).status == Status.READY_FOR_REVIEW


async def test_unknown_item(service):
    with pytest.raises(AppError) as error:
        await service.get(uuid4())
    assert error.value.status_code == 404
