# TODO: don't forget to separate routes
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dependencies import get_current_auth_context
from app.db import healthcheck
from app.schemas.common import HealthResponse
from app.schemas.dm import DMResponse, OpenDMRequest
from app.schemas.message import MessageHistoryResponse, MessageResponse, SendMessageRequest
from app.schemas.account import AccountCreationRequest, AccountResponse, LoginPayload, LoginResponse
from app.services.auth import AuthenticatedContext, register as auth_register, login as auth_login
from app.services.dm import (
    create_message,
    get_dm_by_id,
    get_user_or_none,
    is_dm_participant,
    list_dms_for_user,
    list_messages,
    open_or_create_dm,
    serialize_dm,
    serialize_message,
)
from app.services.websocket import connection_manager


router = APIRouter(prefix="/api", tags=["kilogram"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    await healthcheck()
    return HealthResponse(status="ok", database="ok")


@router.post("/dms/open", response_model=DMResponse)
async def open_dm(
    payload: OpenDMRequest,
    auth: AuthenticatedContext = Depends(get_current_auth_context),
) -> DMResponse:
    if payload.recipient_id == auth.user.id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Cannot open DM with yourself")

    recipient = await get_user_or_none(payload.recipient_id)
    if recipient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recipient not found")

    dm = await open_or_create_dm(auth.user, recipient)
    return serialize_dm(dm, auth.user.id)


@router.get("/dms", response_model=list[DMResponse])
async def list_dms(auth: AuthenticatedContext = Depends(get_current_auth_context)) -> list[DMResponse]:
    dms = await list_dms_for_user(auth.user.id)
    return [serialize_dm(dm, auth.user.id) for dm in dms]


@router.get("/dms/{dm_id}/messages", response_model=MessageHistoryResponse)
async def get_message_history(
    dm_id: int,
    limit: int = Query(default=50, ge=1, le=100),
    before: int | None = Query(default=None, gt=0),
    auth: AuthenticatedContext = Depends(get_current_auth_context),
) -> MessageHistoryResponse:
    dm = await get_dm_by_id(dm_id)
    if dm is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="DM not found")
    if not is_dm_participant(dm, auth.user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a participant")
    return await list_messages(dm, limit=limit, before=before)


@router.post("/dms/{dm_id}/messages", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def send_message(
    dm_id: int,
    payload: SendMessageRequest,
    auth: AuthenticatedContext = Depends(get_current_auth_context),
) -> MessageResponse:
    dm = await get_dm_by_id(dm_id)
    if dm is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="DM not found")
    if not is_dm_participant(dm, auth.user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a participant")

    message = await create_message(dm, auth.user, payload.content)
    response = serialize_message(message)
    event_payload = {"type": "message.created", "data": response.model_dump(mode="json")}
    await connection_manager.broadcast([dm.user_low_id, dm.user_high_id], event_payload)
    return response

@router.post("/register", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: AccountCreationRequest,
) -> AccountResponse:
    result = await auth_register(payload=payload)
    
    # TODO: enums
    if "error" in result:
        if result["error"] == "user_exists":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="User with this username already exists"
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result["error"]
        )
    
    return AccountResponse(
        id=result["id"],
        created_at=result["created_at"],
        token=result["token"],
    )

@router.post("/login", status_code=status.HTTP_200_OK)
async def login(
    payload: LoginPayload,
) -> LoginResponse:
    result = await auth_login(payload=payload)
    
    # TODO: enums
    if "error" in result:
        if result["error"] == "user_not_found":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        elif result["error"] == "wrong_password":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect password"
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result["error"]
        )
    
    return result
