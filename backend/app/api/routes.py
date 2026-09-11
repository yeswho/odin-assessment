from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import text

from app.core.errors import AppError
from app.schemas.work_item import (
    CreateResult,
    StatusUpdate,
    WorkItemCreate,
    WorkItemList,
    WorkItemRead,
)
from app.services.work_items import WorkItemService
from app.workflow.states import Status

router = APIRouter(prefix="/api")


def get_service(request: Request) -> WorkItemService:
    return request.app.state.service


Service = Annotated[WorkItemService, Depends(get_service)]


@router.get("/health")
async def health(request: Request):
    async with request.app.state.engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
    return {"status": "ok", "aiProvider": request.app.state.service.provider.name}


@router.post("/work-items", response_model=CreateResult, status_code=201)
async def create_item(data: WorkItemCreate, response: Response, service: Service):
    result = await service.create(data)
    response.status_code = 201 if result["created"] else 200
    return result


@router.get("/work-items", response_model=WorkItemList)
async def list_items(
    service: Service,
    status: Status | None = None,
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    await service.repository.recover_expired()
    return await service.repository.list(status, limit, offset)


@router.get("/work-items/{item_id}", response_model=WorkItemRead)
async def get_item(item_id: UUID, service: Service):
    await service.repository.recover_expired()
    return await service.get(item_id)


@router.post("/work-items/{item_id}/analyse", response_model=WorkItemRead)
async def analyse_item(item_id: UUID, service: Service):
    return await service.analyse(item_id)


@router.post("/work-items/{item_id}/retry", response_model=WorkItemRead)
async def retry_item(item_id: UUID, service: Service):
    return await service.analyse(item_id, retry=True)


@router.patch("/work-items/{item_id}/status", response_model=WorkItemRead)
async def update_status(item_id: UUID, data: StatusUpdate, service: Service):
    if data.status != Status.COMPLETED:
        raise AppError(
            422,
            "INVALID_STATUS",
            "This endpoint only accepts COMPLETED. Use analyse or retry for AI processing.",
        )
    return await service.complete(item_id)
