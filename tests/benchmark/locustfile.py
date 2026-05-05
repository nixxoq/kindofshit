import uuid
import threading
import time
import random
from locust import HttpUser, task, between, events
import websocket
import redis


class ChatUser(HttpUser):
    wait_time = between(1.0, 3.0)

    def on_start(self):
        self.user_main = f"u_{uuid.uuid4().hex[:8]}"
        self.user_partner = f"p_{uuid.uuid4().hex[:8]}"
        self.password = "pass123"
        self.token = None
        self.dm_id = None
        self.sent_messages = []

        try:
            res_p = self.client.post(
                "/api/register",
                json={
                    "username": self.user_partner,
                    "display_name": "Partner",
                    "password": self.password,
                },
                timeout=30,
            )

            p_id = None
            if res_p.status_code == 201:
                p_id = res_p.json().get("id")

            self.client.post(
                "/api/register",
                json={
                    "username": self.user_main,
                    "display_name": "Main User",
                    "password": self.password,
                },
                timeout=30,
            )

            res_l = self.client.post(
                "/api/login",
                json={"username": self.user_main, "password": self.password},
                timeout=30,
            )

            if res_l.status_code == 200:
                resp_data = res_l.json()
                self.token = resp_data["token"]
                if p_id:
                    res_dm = self.client.post(
                        "/api/dms/open",
                        json={"recipient_id": p_id},
                        headers={"Authorization": f"Bearer {self.token}"},
                        timeout=30,
                    )
                    if res_dm.status_code == 200:
                        self.dm_id = res_dm.json().get("id")

                self._connect_ws()
        except:
            pass

    def _connect_ws(self):
        ws_url = f"ws://127.0.0.1:8000/ws"
        headers = [f"Authorization: Bearer {self.token}"]
        self.ws = websocket.WebSocket()
        try:
            self.ws.connect(ws_url, header=headers, timeout=60)
            threading.Thread(target=self._recv, daemon=True).start()
        except:
            pass

    def _recv(self):
        while True:
            try:
                self.ws.recv()
            except:
                break

    @task(70)
    def send_message(self):
        if not self.token or not self.dm_id:
            return

        with self.client.post(
            f"/api/dms/{self.dm_id}/messages",
            json={"content": f"Message {uuid.uuid4().hex[:6]}"},
            headers={"Authorization": f"Bearer {self.token}"},
            catch_response=True,
        ) as resp:
            if resp.status_code == 201:
                mid = resp.json().get("id")
                if mid:
                    self.sent_messages.append(mid)
                    if len(self.sent_messages) > 10:
                        self.sent_messages.pop(0)
                resp.success()

    @task(20)
    def edit_message(self):
        if not self.token or not self.dm_id or not self.sent_messages:
            return

        msg_id = random.choice(self.sent_messages)
        self.client.patch(
            f"/api/dms/{self.dm_id}/messages/{msg_id}",
            json={"content": "Updated content text"},
            headers={"Authorization": f"Bearer {self.token}"},
        )

    @task(10)
    def delete_message(self):
        if not self.token or not self.dm_id or not self.sent_messages:
            return

        msg_id = self.sent_messages.pop(random.randrange(len(self.sent_messages)))
        self.client.delete(
            f"/api/dms/{self.dm_id}/messages/{msg_id}",
            headers={"Authorization": f"Bearer {self.token}"},
        )


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    r = redis.Redis(host="127.0.0.1", port=6379, db=0)
    r.flushdb()


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    pass
