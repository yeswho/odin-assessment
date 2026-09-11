import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.schemas.work_item import WorkItemCreate
from app.services.work_items import WorkItemService
from app.workflow.states import Status

VALID_ANALYSIS = {
    "category": "DOCUMENT_REQUEST",
    "priority": "HIGH",
    "summary": "A payslip is missing.",
    "recommendedAction": "Request the missing payslip.",
}


class FakeRepository:
    """Workflow unit-test double. PostgreSQL guarantees are tested separately."""

    def __init__(self):
        self.items = {}
        self.lock = asyncio.Lock()

    async def create(self, data):
        async with self.lock:
            for item in self.items.values():
                if item.external_id == data.external_id:
                    return item, False
            item = SimpleNamespace(
                **data.model_dump(),
                id=uuid4(),
                status=Status.RECEIVED,
                attempts=0,
                analysis=None,
                error_code=None,
                error_message=None,
                ai_provider=None,
                attempt_token=None,
                lease_expires_at=None,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            self.items[item.id] = item
            return item, True

    async def get(self, item_id):
        return self.items.get(item_id)

    async def claim(self, item_id, expected, token, lease_seconds):
        async with self.lock:
            item = self.items[item_id]
            if item.status != expected:
                return None
            item.status = Status.ANALYSING
            item.attempts += 1
            item.attempt_token = token
            item.lease_expires_at = datetime.now(timezone.utc) + timedelta(seconds=lease_seconds)
            item.error_code = item.error_message = None
            return item

    async def finish(self, item_id, token, **values):
        item = self.items[item_id]
        if (
            item.attempt_token != token
            or item.status != Status.ANALYSING
            or item.lease_expires_at <= datetime.now(timezone.utc)
        ):
            return None
        item.analysis = values["analysis"]
        item.ai_provider = values["provider"]
        item.error_code = values.get("error_code")
        item.error_message = values.get("error_message")
        item.status = Status.READY_FOR_REVIEW if item.analysis else Status.FAILED
        item.attempt_token = item.lease_expires_at = None
        return item

    async def complete(self, item_id):
        item = self.items[item_id]
        if item.status != Status.READY_FOR_REVIEW:
            return None
        item.status = Status.COMPLETED
        return item

    async def recover_expired(self):
        for item in self.items.values():
            if item.status == Status.ANALYSING and item.lease_expires_at <= datetime.now(
                timezone.utc
            ):
                item.status = Status.FAILED
                item.error_code = "AI_INTERRUPTED"
                item.error_message = "Analysis was interrupted. Retry this item."
                item.attempt_token = item.lease_expires_at = None

    async def list(self, status, limit, offset):
        items = list(self.items.values())
        counts = {state: sum(i.status == state for i in items) for state in Status}
        filtered = [i for i in items if status is None or i.status == status]
        return {
            "items": filtered[offset : offset + limit],
            "total": len(filtered),
            "counts": counts,
            "limit": limit,
            "offset": offset,
        }


class StubProvider:
    name = "stub"

    async def analyse(self, data, attempt):
        return VALID_ANALYSIS.copy()


@pytest.fixture
def payload():
    return WorkItemCreate(
        external_id="CRM-12345",
        title="Missing income document",
        description="The applicant has not provided their latest payslip.",
    )


@pytest.fixture
def service():
    return WorkItemService(
        FakeRepository(), StubProvider(), Settings(ai_mode="mock", ai_timeout_seconds=0.2)
    )
