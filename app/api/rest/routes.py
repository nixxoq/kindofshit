from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from tortoise.expressions import Q

from app.api.dependencies import get_current_auth_context
from app.db import healthcheck
from app.db.models import User
from app.utils import (
    AuthError,
    MessageError,
    WSEventType,
    MSG_LIMIT_DEFAULT,
    MSG_LIMIT_MAX,
)
from app.schemas.common import HealthResponse
from app.schemas.dm import DMResponse, OpenDMRequest
from app.schemas.message import (
    MessageHistoryResponse,
    MessageResponse,
    SendMessageRequest,
    EditMessageRequest,
)
from app.schemas.account import (
    AccountCreationRequest,
    AccountResponse,
    LoginPayload,
    LoginResponse,
    UserPublicResponse,
)
from app.services.auth import (
    AuthenticatedContext,
    register as auth_register,
    login as auth_login,
)
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
    edit_message,
    delete_message,
)
from app.services.websocket import connection_manager

router = APIRouter(prefix="/api", tags=["kilogram"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    await healthcheck()
    return HealthResponse(status="ok", database="ok")


@router.post(
    "/register", response_model=AccountResponse, status_code=status.HTTP_201_CREATED
)
async def register(payload: AccountCreationRequest) -> AccountResponse:
    result = await auth_register(payload=payload)

    if "error" in result:
        if result["error"] == AuthError.USER_EXISTS:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="User already exists"
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=result["error"]
        )

    return AccountResponse(**result)


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginPayload) -> LoginResponse:
    result = await auth_login(payload=payload)

    if "error" in result:
        if result["error"] == AuthError.USER_NOT_FOUND:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
            )
        if result["error"] == AuthError.WRONG_PASSWORD:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid password"
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=result["error"]
        )

    return LoginResponse(**result)


@router.get("/users/search", response_model=list[UserPublicResponse])
async def search_users(
    q: str = Query(min_length=1, max_length=128),
    limit: int = Query(default=10, ge=1, le=20),
    auth: AuthenticatedContext = Depends(get_current_auth_context),
) -> list[UserPublicResponse]:
    users = (
        await User.filter(Q(username__icontains=q) | Q(display_name__icontains=q))
        .exclude(id=auth.user.id)
        .order_by("username")
        .limit(limit)
        .all()
    )
    return [
        UserPublicResponse(
            id=user.id,
            username=user.username,
            display_name=user.display_name,
        )
        for user in users
    ]


@router.post("/dms/open", response_model=DMResponse)
async def open_dm(
    payload: OpenDMRequest,
    auth: AuthenticatedContext = Depends(get_current_auth_context),
) -> DMResponse:
    if payload.recipient_id == auth.user.id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Self DM forbidden"
        )
    recipient = await get_user_or_none(payload.recipient_id)

    if recipient is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Recipient not found"
        )

    dm = await open_or_create_dm(auth.user, recipient)
    return await serialize_dm(dm, auth.user.id)


@router.get("/dms", response_model=list[DMResponse])
async def list_dms(
    auth: AuthenticatedContext = Depends(get_current_auth_context),
) -> list[DMResponse]:
    dms = await list_dms_for_user(auth.user.id)
    return [await serialize_dm(dm, auth.user.id) for dm in dms]


@router.get("/dms/{dm_id}/messages", response_model=MessageHistoryResponse)
async def get_message_history(
    dm_id: int,
    limit: int = Query(default=MSG_LIMIT_DEFAULT, ge=1, le=MSG_LIMIT_MAX),
    before: int | None = Query(default=None, gt=0),
    auth: AuthenticatedContext = Depends(get_current_auth_context),
) -> MessageHistoryResponse:
    dm = await get_dm_by_id(dm_id)

    if not dm or not is_dm_participant(dm, auth.user.id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="DM not found"
        )

    return await list_messages(dm, limit=limit, before=before)


@router.post(
    "/dms/{dm_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def send_message(
    dm_id: int,
    payload: SendMessageRequest,
    auth: AuthenticatedContext = Depends(get_current_auth_context),
) -> MessageResponse:
    dm = await get_dm_by_id(dm_id)

    if not dm or not is_dm_participant(dm, auth.user.id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="DM not found"
        )

    message = await create_message(dm, auth.user, payload.content)
    response = serialize_message(message, auth.user)
    event = {
        "type": WSEventType.MESSAGE_CREATED,
        "data": response.model_dump(mode="json"),
    }

    await connection_manager.broadcast([dm.user_low_id, dm.user_high_id], event)
    return response


@router.patch("/dms/{dm_id}/messages/{message_id}", response_model=MessageResponse)
async def update_message(
    dm_id: int,
    message_id: int,
    payload: EditMessageRequest,
    auth: AuthenticatedContext = Depends(get_current_auth_context),
) -> MessageResponse:
    dm = await get_dm_by_id(dm_id)

    if not dm or not is_dm_participant(dm, auth.user.id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="DM not found"
        )

    result = await edit_message(dm, auth.user, message_id, payload.content)

    if "error" in result:
        status_code = (
            status.HTTP_404_NOT_FOUND
            if result["error"] == MessageError.MESSAGE_NOT_FOUND
            else status.HTTP_403_FORBIDDEN
        )
        raise HTTPException(status_code=status_code, detail=result["error"])

    response_data = result["message"]
    event = {
        "type": WSEventType.MESSAGE_UPDATED,
        "data": response_data.model_dump(mode="json"),
    }

    await connection_manager.broadcast([dm.user_low_id, dm.user_high_id], event)
    return response_data


@router.delete(
    "/dms/{dm_id}/messages/{message_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def remove_message(
    dm_id: int,
    message_id: int,
    auth: AuthenticatedContext = Depends(get_current_auth_context),
):
    dm = await get_dm_by_id(dm_id)
    if not dm or not is_dm_participant(dm, auth.user.id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="DM not found"
        )

    result = await delete_message(dm, auth.user, message_id)

    if "error" in result:
        status_code = (
            status.HTTP_404_NOT_FOUND
            if result["error"] == MessageError.MESSAGE_NOT_FOUND
            else status.HTTP_403_FORBIDDEN
        )
        raise HTTPException(status_code=status_code, detail=result["error"])

    event = {
        "type": WSEventType.MESSAGE_DELETED,
        "data": {"message_id": message_id, "dm_id": dm_id},
    }

    await connection_manager.broadcast([dm.user_low_id, dm.user_high_id], event)
    return None
