from __future__ import annotations

import pytest

from kilogram_tui.api import KilogramAPI, websocket_url_for
from kilogram_tui.app import KilogramTUI, LoginScreen, MainScreen, RegisterScreen
from kilogram_tui.models import DirectMessage, Message
from kilogram_tui.models import SessionState
from kilogram_tui.state import clear_session, load_session, save_session


def test_session_state_roundtrip(tmp_path, monkeypatch) -> None:
    state_file = tmp_path / "session.json"
    monkeypatch.setenv("KILOGRAM_TUI_STATE", str(state_file))
    session = SessionState(
        base_url="https://kilogram.example",
        token="kgm_public.secret",
        user_id=42,
        username="alice",
    )

    save_session(session)

    assert load_session() == session
    clear_session()
    assert load_session() is None


@pytest.mark.parametrize(
    ("base_url", "ws_url"),
    [
        ("http://127.0.0.1:8000", "ws://127.0.0.1:8000/ws"),
        ("https://kilogram.example", "wss://kilogram.example/ws"),
        ("ws://kilogram.example", "ws://kilogram.example/ws"),
        ("wss://kilogram.example/api", "wss://kilogram.example/ws"),
    ],
)
def test_websocket_url_for(base_url: str, ws_url: str) -> None:
    assert websocket_url_for(base_url) == ws_url


def test_direct_message_uses_embedded_peer_title() -> None:
    dm = DirectMessage.from_json(
        {
            "id": 1,
            "peer_user_id": 2,
            "created_at": "2026-05-04T00:00:00Z",
            "peer": {
                "id": 2,
                "username": "bob",
                "display_name": "Bob Builder",
            },
        }
    )

    assert dm.title == "Bob Builder (bob)"


def assert_widget_inside(container, widget) -> None:
    container_region = container.region
    widget_region = widget.region

    assert widget_region.x >= container_region.x
    assert widget_region.y >= container_region.y
    assert widget_region.x + widget_region.width <= container_region.x + container_region.width
    assert widget_region.y + widget_region.height <= container_region.y + container_region.height


def assert_widget_horizontally_centered(screen, widget) -> None:
    screen_center = screen.size.width / 2
    widget_center = widget.region.x + widget.region.width / 2

    assert abs(widget_center - screen_center) <= 1


@pytest.mark.asyncio
async def test_api_client_builds_authorization_header() -> None:
    api = KilogramAPI("http://127.0.0.1:8000", token="kgm_public.secret")
    try:
        assert api.auth_headers() == {"Authorization": "Bearer kgm_public.secret"}
    finally:
        await api.close()


async def test_auth_flow_switches_login_and_register(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("KILOGRAM_TUI_STATE", str(tmp_path / "missing.json"))
    app = KilogramTUI()

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.click("#login-register")
        await pilot.pause()

        assert isinstance(app.screen, RegisterScreen)


async def test_login_auth_panel_contains_controls(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("KILOGRAM_TUI_STATE", str(tmp_path / "missing.json"))
    app = KilogramTUI()

    async with app.run_test(size=(121, 35)) as pilot:
        await pilot.pause()

        assert isinstance(app.screen, LoginScreen)
        panel = app.screen.query_one("#auth-panel")
        assert_widget_horizontally_centered(app.screen, panel)
        for selector in (
            "#login-username",
            "#login-password",
            "#login-submit",
            "#login-register",
            "#auth-status",
        ):
            assert_widget_inside(panel, app.screen.query_one(selector))


async def test_register_auth_panel_contains_controls(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("KILOGRAM_TUI_STATE", str(tmp_path / "missing.json"))
    app = KilogramTUI()

    async with app.run_test(size=(121, 35)) as pilot:
        app.switch_screen(RegisterScreen())
        await pilot.pause()

        panel = app.screen.query_one("#auth-panel")
        assert_widget_horizontally_centered(app.screen, panel)
        for selector in (
            "#brand",
            "#register-username",
            "#register-display-name",
            "#register-password",
            "#register-submit",
            "#register-login",
            "#auth-status",
        ):
            assert_widget_inside(panel, app.screen.query_one(selector))


class FakeAPI:
    async def list_dms(self):
        return []

    async def close(self) -> None:
        return None


async def test_message_context_menu_marks_foreign_actions_disabled(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("KILOGRAM_TUI_STATE", str(tmp_path / "missing.json"))
    app = KilogramTUI()

    async with app.run_test(size=(120, 40)) as pilot:
        app.session = SessionState("http://127.0.0.1:8000", "token", 1, "alice")
        app.api = FakeAPI()
        await app.push_screen(MainScreen())
        await pilot.pause()

        assert str(app.screen.query_one("#logout-button").label) == "Logout"
        app.show_message_context(
            Message(10, 20, 2, "hello", "2026-05-04T00:00:00Z"),
            4,
            4,
        )
        await pilot.pause()

        assert app.screen.query_one("#context-edit").disabled is True
        assert app.screen.query_one("#context-delete").disabled is True
        assert_widget_inside(app.screen.query_one("#message-context-menu"), app.screen.query_one("#context-edit"))
        assert_widget_inside(app.screen.query_one("#message-context-menu"), app.screen.query_one("#context-delete"))


async def test_reopening_message_context_menu_keeps_single_menu(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("KILOGRAM_TUI_STATE", str(tmp_path / "missing.json"))
    app = KilogramTUI()

    async with app.run_test(size=(120, 40)) as pilot:
        app.session = SessionState("http://127.0.0.1:8000", "token", 1, "alice")
        app.api = FakeAPI()
        await app.push_screen(MainScreen())
        await pilot.pause()

        first_message = Message(10, 20, 1, "first", "2026-05-04T00:00:00Z")
        second_message = Message(11, 20, 1, "second", "2026-05-04T00:00:00Z")
        app.show_message_context(first_message, 4, 4)
        await pilot.pause()
        app.show_message_context(second_message, 8, 8)
        await pilot.pause()

        menus = list(app.screen.query("#message-context-menu"))
        assert len(menus) == 1
        assert app.context_menu is menus[0]
        assert app.context_menu.message == second_message


async def test_message_rerender_keeps_single_dom_node_per_message(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("KILOGRAM_TUI_STATE", str(tmp_path / "missing.json"))
    app = KilogramTUI()

    async with app.run_test(size=(120, 40)) as pilot:
        app.session = SessionState("http://127.0.0.1:8000", "token", 1, "alice")
        app.api = FakeAPI()
        await app.push_screen(MainScreen())
        await pilot.pause()

        app.active_dm = DirectMessage(
            id=20,
            peer_user_id=2,
            created_at="2026-05-04T00:00:00Z",
        )
        first_message = Message(10, 20, 1, "first", "2026-05-04T00:00:00Z")
        sent_message = Message(11, 20, 1, "sent", "2026-05-04T00:00:01Z")
        app.messages = [first_message]
        await app.render_messages()
        await pilot.pause()

        await app.apply_message_created(sent_message)
        await app.apply_message_created(sent_message)
        await pilot.pause()

        rows = list(app.screen.query(".message-row"))
        row_messages = {row.message.id: row.message for row in rows}
        assert len(rows) == 2
        assert row_messages == {
            first_message.id: first_message,
            sent_message.id: sent_message,
        }


async def test_logout_clears_session_and_returns_to_login(monkeypatch, tmp_path) -> None:
    state_file = tmp_path / "session.json"
    monkeypatch.setenv("KILOGRAM_TUI_STATE", str(state_file))
    session = SessionState("http://127.0.0.1:8000", "token", 1, "alice")
    app = KilogramTUI()

    async with app.run_test(size=(120, 40)) as pilot:
        save_session(session)
        app.session = session
        app.api = FakeAPI()
        await app.push_screen(MainScreen())
        await pilot.pause()

        await app.logout()
        await pilot.pause()

        assert load_session() is None
        assert app.session is None
        assert isinstance(app.screen, LoginScreen)


async def test_inline_edit_uses_context_message(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("KILOGRAM_TUI_STATE", str(tmp_path / "missing.json"))
    app = KilogramTUI()

    async with app.run_test(size=(120, 40)) as pilot:
        app.session = SessionState("http://127.0.0.1:8000", "token", 1, "alice")
        app.api = FakeAPI()
        await app.push_screen(MainScreen())
        await pilot.pause()

        message = Message(10, 20, 1, "draft me", "2026-05-04T00:00:00Z")
        app.show_message_context(message, 4, 4)
        app.begin_editing_context_message()
        await pilot.pause()

        assert app.editing_message == message
        assert app.screen.query_one("#composer").value == "draft me"
