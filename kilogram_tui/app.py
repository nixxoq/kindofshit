from __future__ import annotations

import asyncio
from datetime import datetime
import os
from pathlib import Path
from typing import cast

from textual import events
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Input, Label, ListItem, ListView, Static

from kilogram_tui.api import (
    DEFAULT_BASE_URL,
    KilogramAPI,
    KilogramAPIError,
    UnauthorizedError,
)
from kilogram_tui.models import DirectMessage, Message, PublicUser, SessionState
from kilogram_tui.state import clear_session, load_session, save_session
from kilogram_tui.ws import WebSocketListener


class UserListItem(ListItem):
    def __init__(self, user: PublicUser) -> None:
        self.user = user
        super().__init__(
            Label(f"{user.display_name} @{user.username}"), classes="list-row"
        )


class DMListItem(ListItem):
    def __init__(self, dm: DirectMessage) -> None:
        self.dm = dm
        super().__init__(
            Horizontal(
                Label(dm.title, classes="dm-title"),
                DMCloseButton(dm.id),
                classes="dm-row-content",
            ),
            classes="list-row",
        )


class DMCloseButton(Button):
    def __init__(self, dm_id: int) -> None:
        self.dm_id = dm_id
        super().__init__("×", classes="dm-close-button")

    def on_mouse_down(self, event: events.MouseDown) -> None:
        event.stop()


class MessageWidget(Container):
    def __init__(self, message: Message, current_user_id: int) -> None:
        super().__init__(classes="message-row")
        self.message = message
        self.current_user_id = current_user_id
        if message.author_id == current_user_id:
            self.add_class("own-message")

    def get_relative_time(self, dt) -> str:
        if isinstance(dt, str):
            try:
                dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
            except ValueError:
                return dt[11:16]

        dt = dt.astimezone()
        now = datetime.now().astimezone()
        days = (now.date() - dt.date()).days
        ts = dt.strftime("%H:%M")

        if days == 0:
            s = max(0, (now - dt).total_seconds())
            if s < 60:
                return "just now"
            if s < 3600:
                return f"{int(s // 60)} minute{'s' * (s >= 120)} ago"
            return f"{int(s // 3600)} hour{'s' * (s >= 7200)} ago"

        return f"yesterday at {ts}" if days == 1 else f"{dt.strftime('%b %d')} at {ts}"

    def compose(self) -> ComposeResult:
        is_me = self.message.author_id == self.current_user_id
        author = (
            "me"
            if is_me
            else f"{self.message.author.display_name} ({self.message.author.username})"
        )

        ed = (
            f" [#9e4197 italic](edited {self.get_relative_time(self.message.edited_at)})[/]"
            if self.message.edited_at
            else ""
        )
        ts = self.get_relative_time(self.message.created_at)

        with Horizontal(classes="msg-header"):
            yield Static(f"{author}{ed}", classes="msg-author")
            yield Static(f"[italic #806070]{ts}[/]", classes="msg-time")

        yield Static(self.message.content, classes="msg-content")

    def on_mouse_down(self, event: events.MouseDown) -> None:
        if event.button == 3:
            cast(KilogramTUI, self.app).show_message_context(
                self.message, int(event.screen_x or 0), int(event.screen_y or 0)
            )
            event.stop()


class MessageContextMenu(Container):
    def __init__(self, message: Message, can_edit: bool, x: int, y: int) -> None:
        self.message = message
        self.can_edit = can_edit
        super().__init__(id="message-context-menu")
        self.retarget(message, can_edit, x, y)

    def compose(self) -> ComposeResult:
        yield Button("EDIT", id="context-edit", disabled=not self.can_edit)
        yield Button("delete", id="context-delete", disabled=not self.can_edit)

    def on_mouse_down(self, event: events.MouseDown) -> None:
        event.stop()

    def retarget(self, message: Message, can_edit: bool, x: int, y: int) -> None:
        self.message = message
        self.can_edit = can_edit
        self.styles.offset = (x, y)
        for button_id in ("#context-edit", "#context-delete"):
            try:
                self.query_one(button_id, Button).disabled = not can_edit
            except Exception:
                pass


class AuthScreen(Screen):
    def auth_inputs(self) -> tuple[Input, ...]:
        return tuple(self.query(Input))

    def set_status(self, message: str) -> None:
        self.query_one("#auth-status", Static).update(message)

    async def submit_auth(self) -> None:
        raise NotImplementedError

    async def on_input_submitted(self, _: Input.Submitted) -> None:
        await self.submit_auth()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id in {"login-submit", "register-submit"}:
            await self.submit_auth()


class LoginScreen(AuthScreen):
    def compose(self) -> ComposeResult:
        with Container(id="auth-stage"):
            yield Label("Login", id="auth-title")
            with Vertical(id="auth-panel", classes="login-panel"):
                yield Input(placeholder="username", id="login-username")
                yield Input(placeholder="password", password=True, id="login-password")
                yield Button("login", id="login-submit")
                yield Button("register", id="login-register")
                yield Static("", id="auth-status")

    async def submit_auth(self) -> None:
        username = self.query_one("#login-username", Input).value.strip()
        password = self.query_one("#login-password", Input).value
        if not username or not password:
            self.set_status("username and password required")
            return
        self.set_status("logging in")
        await cast(KilogramTUI, self.app).login(username, password)

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "login-register":
            self.app.switch_screen(RegisterScreen())
            return
        await super().on_button_pressed(event)


class RegisterScreen(AuthScreen):
    def compose(self) -> ComposeResult:
        with Container(id="auth-stage"):
            yield Label("Register menu", id="auth-title")
            with Vertical(id="auth-panel", classes="register-panel"):
                yield Static("k1LLOgr4m", id="brand")
                yield Input(placeholder="username", id="register-username")
                yield Input(placeholder="display_name", id="register-display-name")
                yield Input(
                    placeholder="password", password=True, id="register-password"
                )
                yield Button("register", id="register-submit")
                yield Button("login", id="register-login")
                yield Static("", id="auth-status")

    async def submit_auth(self) -> None:
        username = self.query_one("#register-username", Input).value.strip()
        display_name = self.query_one("#register-display-name", Input).value.strip()
        password = self.query_one("#register-password", Input).value
        if not username or not display_name or not password:
            self.set_status("all fields required")
            return
        self.set_status("registering")
        await cast(KilogramTUI, self.app).register(username, display_name, password)

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "register-login":
            self.app.switch_screen(LoginScreen())
            return
        await super().on_button_pressed(event)


class MainScreen(Screen):
    BINDINGS = [("escape", "close_context", "Close menu")]

    def compose(self) -> ComposeResult:
        with Vertical(id="main-root"):
            with Horizontal(id="main-header"):
                yield Label("Main Menu", id="main-title")
                yield Button("Logout", id="logout-button")
            with Horizontal(id="main-frame"):
                with Vertical(id="left-column"):
                    yield ListView(id="dm-list")
                    with Vertical(id="search-panel"):
                        yield Input(placeholder="search users", id="user-search")
                        yield ListView(id="user-results")
                with Vertical(id="chat-column"):
                    yield Static("", id="chat-title")
                    with VerticalScroll(id="messages"):
                        with Vertical(id="message-list"):
                            yield Static("select or search a chat", id="empty-chat")
                    with Horizontal(id="composer-row"):
                        yield Input(placeholder="message", id="composer")
                        yield Button("send", id="send-message")
                    yield Static("", id="status")

    async def on_mount(self) -> None:
        await cast(KilogramTUI, self.app).refresh_dms()

    def set_status(self, message: str) -> None:
        self.query_one("#status", Static).update(message)

    def on_mouse_down(self, event: events.MouseDown) -> None:
        if event.button != 3:
            cast(KilogramTUI, self.app).close_message_context()

    def action_close_context(self) -> None:
        cast(KilogramTUI, self.app).close_message_context()

    async def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "user-search":
            return
        query = event.value.strip()
        if len(query) < 1:
            await cast(KilogramTUI, self.app).render_user_results([])
            return
        await cast(KilogramTUI, self.app).search_users(query)

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "composer":
            await cast(KilogramTUI, self.app).submit_composer()
        elif event.input.id == "user-search":
            await cast(KilogramTUI, self.app).open_first_search_result()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        app = cast(KilogramTUI, self.app)
        if event.button.id == "send-message":
            await app.submit_composer()
        elif event.button.id == "logout-button":
            await app.logout()
        elif isinstance(event.button, DMCloseButton):
            await app.close_dm(event.button.dm_id)
            event.stop()
        elif event.button.id == "load-older":
            await app.load_older_messages()
        elif event.button.id == "context-edit":
            app.begin_editing_context_message()
        elif event.button.id == "context-delete":
            await app.delete_context_message()

    async def on_list_view_selected(self, event: ListView.Selected) -> None:
        app = cast(KilogramTUI, self.app)
        if isinstance(event.item, DMListItem):
            await app.select_dm(event.item.dm)
        elif isinstance(event.item, UserListItem):
            await app.open_user_dm(event.item.user)


class KilogramTUI(App):
    CSS_PATH = Path(__file__).with_name("styles.tcss")
    TITLE = "Kilogram"

    def __init__(self) -> None:
        super().__init__()
        self.api: KilogramAPI | None = None
        self.session: SessionState | None = None
        self.dms: dict[int, DirectMessage] = {}
        self.hidden_dm_ids: set[int] = set()
        self.search_results: list[PublicUser] = []
        self.active_dm: DirectMessage | None = None
        self.messages: list[Message] = []
        self.next_before: int | None = None
        self.editing_message: Message | None = None
        self.context_menu: MessageContextMenu | None = None
        self.render_messages_lock = asyncio.Lock()
        self.ws_listener: WebSocketListener | None = None
        self.ws_task: asyncio.Task | None = None

    async def on_mount(self) -> None:
        session = load_session()
        if session is None:
            self.api = KilogramAPI(os.getenv("KILOGRAM_API_URL", DEFAULT_BASE_URL))
            await self.push_screen(LoginScreen())
            return

        self.session = session
        self.hidden_dm_ids = set(session.hidden_dm_ids)
        self.api = KilogramAPI(session.base_url, session.token)
        try:
            await self.api.list_dms()
        except UnauthorizedError:
            clear_session()
            self.session = None
            self.api = KilogramAPI(os.getenv("KILOGRAM_API_URL", DEFAULT_BASE_URL))
            await self.push_screen(LoginScreen())
            return
        except KilogramAPIError:
            pass
        await self.push_screen(MainScreen())
        self.start_ws()

    async def on_unmount(self) -> None:
        await self.shutdown_network()

    async def shutdown_network(self) -> None:
        await self.stop_ws()
        if self.api is not None:
            await self.api.close()

    async def stop_ws(self) -> None:
        if self.ws_listener is not None:
            self.ws_listener.stop()
        if self.ws_task is not None:
            self.ws_task.cancel()
            try:
                await self.ws_task
            except asyncio.CancelledError:
                pass
        self.ws_listener = None
        self.ws_task = None

    async def login(self, username: str, password: str) -> None:
        assert self.api is not None
        try:
            session = await self.api.login(username, password)
        except KilogramAPIError as exc:
            cast(AuthScreen, self.screen).set_status(str(exc))
            return
        self.set_authenticated(session)

    async def register(self, username: str, display_name: str, password: str) -> None:
        assert self.api is not None
        try:
            session = await self.api.register(username, display_name, password)
        except KilogramAPIError as exc:
            cast(AuthScreen, self.screen).set_status(str(exc))
            return
        self.set_authenticated(session)

    def set_authenticated(self, session: SessionState) -> None:
        self.session = session
        self.hidden_dm_ids = set(session.hidden_dm_ids)
        save_session(session)
        self.switch_screen(MainScreen())
        self.start_ws()

    def start_ws(self) -> None:
        if self.api is None or self.session is None:
            return
        if self.ws_listener is not None:
            self.ws_listener.stop()
        self.ws_listener = WebSocketListener(
            self.api.ws_url,
            self.session.token,
            self.handle_ws_event,
            self.handle_ws_status,
        )
        self.ws_task = asyncio.create_task(self.ws_listener.run())

    async def logout(self) -> None:
        await self.stop_ws()
        if self.api is not None:
            await self.api.close()
        clear_session()
        self.session = None
        self.dms.clear()
        self.hidden_dm_ids.clear()
        self.search_results.clear()
        self.active_dm = None
        self.messages.clear()
        self.next_before = None
        self.editing_message = None
        self.context_menu = None
        self.api = KilogramAPI(os.getenv("KILOGRAM_API_URL", DEFAULT_BASE_URL))
        self.switch_screen(LoginScreen())

    async def handle_ws_status(self, status: str) -> None:
        if isinstance(self.screen, MainScreen):
            self.screen.set_status(f"ws {status}")

    async def handle_ws_event(self, event: dict) -> None:
        event_type = event.get("type")
        data = event.get("data", {})
        if event_type == "message.created":
            await self.handle_message_created_event(Message.from_json(data))
        elif event_type == "message.updated":
            await self.apply_message_updated(Message.from_json(data))
        elif event_type == "message.deleted":
            await self.apply_message_deleted(
                int(data["dm_id"]), int(data["message_id"])
            )

    async def handle_message_created_event(self, message: Message) -> None:
        if message.dm_id not in self.dms:
            await self.refresh_dms()
            if isinstance(self.screen, MainScreen):
                self.screen.set_status("new message")
        if message.dm_id in self.hidden_dm_ids:
            self.hidden_dm_ids.discard(message.dm_id)
            self.persist_hidden_dm_ids()
            await self.render_dms()

        if self.active_dm is not None and message.dm_id == self.active_dm.id:
            await self.apply_message_created(message)

    async def with_unauthorized_handling(self, action) -> None:
        try:
            await action()
        except UnauthorizedError:
            clear_session()
            self.session = None
            self.switch_screen(LoginScreen())
        except KilogramAPIError as exc:
            if isinstance(self.screen, MainScreen):
                self.screen.set_status(str(exc))

    async def refresh_dms(self) -> None:
        async def action() -> None:
            assert self.api is not None
            dms = await self.api.list_dms()
            refreshed_dms: dict[int, DirectMessage] = {}
            for dm in dms:
                existing = self.dms.get(dm.id)
                refreshed_dms[dm.id] = DirectMessage(
                    id=dm.id,
                    peer_user_id=dm.peer_user_id,
                    created_at=dm.created_at,
                    peer=dm.peer or (existing.peer if existing else None),
                )
            self.dms = refreshed_dms
            await self.render_dms()

        await self.with_unauthorized_handling(action)

    async def render_dms(self) -> None:
        if not isinstance(self.screen, MainScreen):
            return
        dm_list = self.screen.query_one("#dm-list", ListView)
        await dm_list.clear()
        for dm in self.dms.values():
            if dm.id in self.hidden_dm_ids:
                continue
            await dm_list.append(DMListItem(dm))

    async def search_users(self, query: str) -> None:
        async def action() -> None:
            assert self.api is not None
            self.search_results = await self.api.search_users(query)
            await self.render_user_results(self.search_results)

        await self.with_unauthorized_handling(action)

    async def render_user_results(self, users: list[PublicUser]) -> None:
        if not isinstance(self.screen, MainScreen):
            return
        results = self.screen.query_one("#user-results", ListView)
        await results.clear()
        for user in users:
            await results.append(UserListItem(user))

    async def open_first_search_result(self) -> None:
        if self.search_results:
            await self.open_user_dm(self.search_results[0])

    async def open_user_dm(self, user: PublicUser) -> None:
        async def action() -> None:
            assert self.api is not None
            dm = await self.api.open_dm(user.id, peer=user)
            self.dms[dm.id] = dm
            if dm.id in self.hidden_dm_ids:
                self.hidden_dm_ids.discard(dm.id)
                self.persist_hidden_dm_ids()
            await self.render_dms()
            await self.select_dm(dm)

        await self.with_unauthorized_handling(action)

    async def close_dm(self, dm_id: int) -> None:
        self.hidden_dm_ids.add(dm_id)
        self.persist_hidden_dm_ids()
        if self.active_dm is not None and self.active_dm.id == dm_id:
            self.active_dm = None
            self.messages.clear()
            self.next_before = None
            self.editing_message = None
            self.close_message_context()
            await self.render_messages()
        await self.render_dms()

    def persist_hidden_dm_ids(self) -> None:
        if self.session is None:
            return
        self.session = SessionState(
            base_url=self.session.base_url,
            token=self.session.token,
            user_id=self.session.user_id,
            username=self.session.username,
            hidden_dm_ids=frozenset(self.hidden_dm_ids),
        )
        save_session(self.session)

    async def select_dm(self, dm: DirectMessage) -> None:
        self.active_dm = dm
        self.editing_message = None
        self.close_message_context()

        async def action() -> None:
            assert self.api is not None
            page = await self.api.message_history(dm.id)
            self.messages = list(reversed(page.items))
            self.next_before = page.next_before
            await self.render_messages()

        await self.with_unauthorized_handling(action)

    async def load_older_messages(self) -> None:
        if self.active_dm is None or self.next_before is None:
            return

        async def action() -> None:
            assert self.api is not None
            page = await self.api.message_history(
                self.active_dm.id,
                before=self.next_before,
            )
            older_messages = list(reversed(page.items))
            existing_ids = {message.id for message in self.messages}
            self.messages = [
                message for message in older_messages if message.id not in existing_ids
            ] + self.messages
            self.next_before = page.next_before
            await self.render_messages()

        await self.with_unauthorized_handling(action)

    async def render_messages(self) -> None:
        async with self.render_messages_lock:
            if not isinstance(self.screen, MainScreen) or self.session is None:
                return
            title = self.active_dm.title if self.active_dm is not None else ""
            self.screen.query_one("#chat-title", Static).update(title)
            message_list = self.screen.query_one("#message-list", Vertical)
            await message_list.remove_children()
            if self.next_before is not None:
                await message_list.mount(Button("load older", id="load-older"))
            if not self.messages:
                await message_list.mount(Static("no messages", id="empty-chat"))
                return
            for message in self.messages:
                await message_list.mount(MessageWidget(message, self.session.user_id))
            messages = self.screen.query_one("#messages", VerticalScroll)
            messages.scroll_end(animate=False)

    async def submit_composer(self) -> None:
        if not isinstance(self.screen, MainScreen) or self.active_dm is None:
            return
        composer = self.screen.query_one("#composer", Input)
        content = composer.value.strip()
        if not content:
            return

        async def action() -> None:
            assert self.api is not None
            if self.editing_message is not None:
                message = await self.api.edit_message(
                    self.active_dm.id,
                    self.editing_message.id,
                    content,
                )
                await self.apply_message_updated(message)
                self.editing_message = None
                composer.placeholder = "message"
            else:
                message = await self.api.send_message(self.active_dm.id, content)
                await self.apply_message_created(message)
            composer.value = ""

        await self.with_unauthorized_handling(action)

    async def apply_message_created(self, message: Message) -> None:
        if self.active_dm is None or message.dm_id != self.active_dm.id:
            return
        self.upsert_message(message)
        await self.render_messages()

    async def apply_message_updated(self, message: Message) -> None:
        if self.active_dm is None or message.dm_id != self.active_dm.id:
            return
        self.upsert_message(message)
        await self.render_messages()

    async def apply_message_deleted(self, dm_id: int, message_id: int) -> None:
        if self.active_dm is None or dm_id != self.active_dm.id:
            return
        self.messages = [
            message for message in self.messages if message.id != message_id
        ]
        await self.render_messages()

    def upsert_message(self, message: Message) -> None:
        for index, existing in enumerate(self.messages):
            if existing.id == message.id:
                self.messages[index] = message
                return
        self.messages.append(message)

    def show_message_context(self, message: Message, x: int, y: int) -> None:
        can_edit = (
            self.session is not None and message.author_id == self.session.user_id
        )
        x, y = self.clamp_context_menu_position(x, y)
        menu = self.context_menu
        if menu is None:
            existing_menus = list(self.screen.query("#message-context-menu"))
            menu = cast(
                MessageContextMenu | None, existing_menus[0] if existing_menus else None
            )

        if menu is not None:
            menu.retarget(message, can_edit, x, y)
            self.context_menu = menu
            return

        menu = MessageContextMenu(message, can_edit, x, y)
        self.context_menu = menu
        self.screen.mount(menu)

    def clamp_context_menu_position(self, x: int, y: int) -> tuple[int, int]:
        menu_width = 18
        menu_height = 10
        screen_width = self.screen.size.width
        screen_height = self.screen.size.height
        clamped_x = max(0, min(x, max(0, screen_width - menu_width)))
        clamped_y = max(0, min(y, max(0, screen_height - menu_height)))
        return clamped_x, clamped_y

    def close_message_context(self) -> None:
        existing_menus = list(self.screen.query("#message-context-menu"))
        self.context_menu = None
        for menu in existing_menus:
            menu.remove()

    def begin_editing_context_message(self) -> None:
        if self.context_menu is None or not isinstance(self.screen, MainScreen):
            return
        self.editing_message = self.context_menu.message
        composer = self.screen.query_one("#composer", Input)
        composer.value = self.editing_message.content
        composer.placeholder = "editing message"
        composer.focus()
        self.close_message_context()

    async def delete_context_message(self) -> None:
        if self.context_menu is None or self.active_dm is None:
            return
        message = self.context_menu.message
        self.close_message_context()

        async def action() -> None:
            assert self.api is not None
            await self.api.delete_message(self.active_dm.id, message.id)
            await self.apply_message_deleted(self.active_dm.id, message.id)

        await self.with_unauthorized_handling(action)


def main() -> None:
    KilogramTUI().run()
