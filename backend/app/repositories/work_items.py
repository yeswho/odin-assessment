from datetime import timedelta
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.work_item import WorkItem
from app.schemas.work_item import WorkItemCreate
from app.workflow.states import Status


class WorkItemRepository:
    """Every mutation commits before returning; no transaction spans an LLM call."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]):
        self.sessions = sessions

    async def create(self, data: WorkItemCreate) -> tuple[WorkItem, bool]:
        async with self.sessions.begin() as session:
            statement = (
                insert(WorkItem)
                .values(**data.model_dump())
                .on_conflict_do_nothing(index_elements=[WorkItem.external_id])
                .returning(WorkItem)
            )
            item = (await session.scalars(statement)).one_or_none()
            if item is not None:
                return item, True
            # A new statement sees the winner's committed row under READ COMMITTED.
            item = (
                await session.scalars(
                    select(WorkItem).where(WorkItem.external_id == data.external_id)
                )
            ).one()
            return item, False

    async def get(self, item_id: UUID) -> WorkItem | None:
        async with self.sessions() as session:
            return await session.get(WorkItem, item_id)

    async def list(self, status: Status | None, limit: int, offset: int):
        async with self.sessions() as session:
            query = select(WorkItem)
            count_query = select(func.count()).select_from(WorkItem)
            if status:
                query = query.where(WorkItem.status == status)
                count_query = count_query.where(WorkItem.status == status)
            items = list(
                (
                    await session.scalars(
                        query.order_by(WorkItem.created_at.desc(), WorkItem.id.desc())
                        .limit(limit)
                        .offset(offset)
                    )
                ).all()
            )
            total = await session.scalar(count_query)
            groups = await session.execute(
                select(WorkItem.status, func.count()).group_by(WorkItem.status)
            )
            counts = {state: 0 for state in Status}
            counts.update(dict(groups.all()))
            return {
                "items": items,
                "total": total,
                "counts": counts,
                "limit": limit,
                "offset": offset,
            }

    async def claim(
        self, item_id: UUID, expected: Status, token: UUID, lease_seconds: int
    ) -> WorkItem | None:
        async with self.sessions.begin() as session:
            statement = (
                update(WorkItem)
                .where(WorkItem.id == item_id, WorkItem.status == expected)
                .values(
                    status=Status.ANALYSING,
                    attempts=WorkItem.attempts + 1,
                    attempt_token=token,
                    lease_expires_at=func.now() + timedelta(seconds=lease_seconds),
                    error_code=None,
                    error_message=None,
                    ai_provider=None,
                    updated_at=func.now(),
                )
                .returning(WorkItem)
            )
            return (await session.scalars(statement)).one_or_none()

    async def finish(
        self,
        item_id: UUID,
        token: UUID,
        *,
        analysis: dict | None,
        provider: str,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> WorkItem | None:
        async with self.sessions.begin() as session:
            statement = (
                update(WorkItem)
                .where(
                    WorkItem.id == item_id,
                    WorkItem.status == Status.ANALYSING,
                    WorkItem.attempt_token == token,
                    WorkItem.lease_expires_at > func.now(),
                )
                .values(
                    status=Status.READY_FOR_REVIEW if analysis else Status.FAILED,
                    analysis=analysis,
                    ai_provider=provider,
                    error_code=error_code,
                    error_message=error_message,
                    attempt_token=None,
                    lease_expires_at=None,
                    updated_at=func.now(),
                )
                .returning(WorkItem)
            )
            return (await session.scalars(statement)).one_or_none()

    async def complete(self, item_id: UUID) -> WorkItem | None:
        async with self.sessions.begin() as session:
            statement = (
                update(WorkItem)
                .where(WorkItem.id == item_id, WorkItem.status == Status.READY_FOR_REVIEW)
                .values(status=Status.COMPLETED, updated_at=func.now())
                .returning(WorkItem)
            )
            return (await session.scalars(statement)).one_or_none()

    async def recover_expired(self):
        async with self.sessions.begin() as session:
            await session.execute(
                update(WorkItem)
                .where(WorkItem.status == Status.ANALYSING, WorkItem.lease_expires_at <= func.now())
                .values(
                    status=Status.FAILED,
                    error_code="AI_INTERRUPTED",
                    error_message="Analysis was interrupted. You can retry this item.",
                    attempt_token=None,
                    lease_expires_at=None,
                    updated_at=func.now(),
                )
            )
