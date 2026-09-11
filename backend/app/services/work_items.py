import asyncio
import json
from uuid import UUID, uuid4

from pydantic import ValidationError

from app.ai.providers import AIProvider, ProviderError
from app.core.config import Settings
from app.core.errors import AppError
from app.repositories.work_items import WorkItemRepository
from app.schemas.work_item import Analysis, WorkItemCreate
from app.workflow.states import Status, can_transition


class WorkItemService:
    def __init__(self, repository: WorkItemRepository, provider: AIProvider, settings: Settings):
        self.repository = repository
        self.provider = provider
        self.settings = settings

    async def get(self, item_id: UUID):
        item = await self.repository.get(item_id)
        if item is None:
            raise AppError(404, "NOT_FOUND", "Work item not found.")
        return item

    async def create(self, data: WorkItemCreate):
        item, created = await self.repository.create(data)
        if item.title != data.title or item.description != data.description:
            raise AppError(
                409,
                "EXTERNAL_ID_CONFLICT",
                "This external ID already belongs to different content. The original item was preserved.",
            )
        return {"item": item, "created": created}

    async def complete(self, item_id: UUID):
        before = await self.get(item_id)
        if not can_transition(Status(before.status), Status.COMPLETED):
            raise AppError(
                409, "INVALID_TRANSITION", "Only items ready for review can be completed."
            )
        item = await self.repository.complete(item_id)
        if item is None:
            raise AppError(
                409, "STATE_CONFLICT", "This item changed in another request. Refresh it."
            )
        return item

    async def analyse(self, item_id: UUID, *, retry: bool = False):
        await self.repository.recover_expired()
        before = await self.get(item_id)
        expected = Status.FAILED if retry else Status.RECEIVED
        if before.status != expected or (retry and not before.error_code):
            raise AppError(
                409,
                "INVALID_TRANSITION",
                "Only failed AI processing can be retried."
                if retry
                else "Only received items can start analysis.",
            )
        token = uuid4()
        claimed = await self.repository.claim(
            item_id, expected, token, self.settings.analysis_lease_seconds
        )
        if claimed is None:
            raise AppError(409, "STATE_CONFLICT", "Another request already started analysis.")
        data = WorkItemCreate(
            external_id=claimed.external_id, title=claimed.title, description=claimed.description
        )
        analysis, error_code, error_message = None, None, None
        try:
            async with asyncio.timeout(self.settings.ai_timeout_seconds):
                raw = await self.provider.analyse(data, claimed.attempts)
            if isinstance(raw, str):
                raw = json.loads(raw)
            analysis = Analysis.model_validate(raw).model_dump(mode="json", by_alias=True)
        except TimeoutError:
            error_code, error_message = "AI_TIMEOUT", "Analysis timed out. You can retry this item."
        except (ValidationError, ValueError, TypeError):
            error_code, error_message = (
                "AI_INVALID_OUTPUT",
                "AI returned invalid structured data. You can retry this item.",
            )
        except ProviderError as exc:
            error_code, error_message = "AI_UNAVAILABLE", str(exc)
        except Exception:
            error_code, error_message = (
                "AI_UNAVAILABLE",
                "AI processing failed. You can retry this item.",
            )
        # Cancellation and DB failures intentionally propagate; the persisted lease recovers interruptions.
        result = await self.repository.finish(
            item_id,
            token,
            analysis=analysis,
            provider=self.provider.name,
            error_code=error_code,
            error_message=error_message,
        )
        if result is None:
            raise AppError(
                409,
                "ATTEMPT_EXPIRED",
                "This analysis attempt expired. Refresh the item before retrying.",
            )
        return result
