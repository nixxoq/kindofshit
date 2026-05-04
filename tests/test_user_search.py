from __future__ import annotations

import httpx
import pytest
import pytest_asyncio
from tortoise import Tortoise

from app.db import close_orm, init_orm
from app.db.models import User
from app.main import create_app
from app.services.auth import create_auth_token


@pytest_asyncio.fixture
async def api_client(tmp_path):
    await init_orm(database_url=f"sqlite://{tmp_path / 'test.sqlite3'}")
    await Tortoise.generate_schemas()
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    await close_orm()


async def create_user(username: str, display_name: str) -> User:
    return await User.create(
        username=username,
        display_name=display_name,
        hashed_password="unused-in-search-tests",
        is_test_user=True,
    )


async def auth_header(user: User) -> dict[str, str]:
    token = await create_auth_token(user, name="test")
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_user_search_requires_auth(api_client: httpx.AsyncClient) -> None:
    response = await api_client.get("/api/users/search", params={"q": "alice"})

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_user_search_matches_username_and_display_name(
    api_client: httpx.AsyncClient,
) -> None:
    current_user = await create_user("alice", "Alice")
    bob = await create_user("bobby", "Builder")
    carol = await create_user("carol", "Bobby Tables")
    await create_user("dave", "No Match")

    response = await api_client.get(
        "/api/users/search",
        params={"q": "bob"},
        headers=await auth_header(current_user),
    )

    assert response.status_code == 200
    ids = {item["id"] for item in response.json()}
    assert ids == {bob.id, carol.id}


@pytest.mark.asyncio
async def test_user_search_excludes_current_user(api_client: httpx.AsyncClient) -> None:
    current_user = await create_user("alice", "Alice Current")
    other = await create_user("alice-peer", "Alice Peer")

    response = await api_client.get(
        "/api/users/search",
        params={"q": "alice"},
        headers=await auth_header(current_user),
    )

    assert response.status_code == 200
    ids = {item["id"] for item in response.json()}
    assert current_user.id not in ids
    assert other.id in ids


@pytest.mark.asyncio
async def test_user_search_respects_limit(api_client: httpx.AsyncClient) -> None:
    current_user = await create_user("current", "Current")
    for index in range(5):
        await create_user(f"target-{index}", f"Target {index}")

    response = await api_client.get(
        "/api/users/search",
        params={"q": "target", "limit": 2},
        headers=await auth_header(current_user),
    )

    assert response.status_code == 200
    assert len(response.json()) == 2


@pytest.mark.asyncio
async def test_dm_list_includes_peer_public_profile(
    api_client: httpx.AsyncClient,
) -> None:
    alice = await create_user("alice", "Alice Current")
    bob = await create_user("bob", "Bob Builder")

    open_response = await api_client.post(
        "/api/dms/open",
        json={"recipient_id": bob.id},
        headers=await auth_header(alice),
    )
    list_response = await api_client.get(
        "/api/dms",
        headers=await auth_header(alice),
    )

    assert open_response.status_code == 200
    assert open_response.json()["peer"] == {
        "id": bob.id,
        "username": "bob",
        "display_name": "Bob Builder",
    }
    assert list_response.status_code == 200
    assert list_response.json()[0]["peer"] == {
        "id": bob.id,
        "username": "bob",
        "display_name": "Bob Builder",
    }
