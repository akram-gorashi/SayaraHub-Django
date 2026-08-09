import os
from urllib.parse import urlparse

import websocket
from locust import HttpUser, between, task
from locust.exception import StopUser


class SayaraHubUser(HttpUser):
    wait_time = between(0.5, 2)

    def on_start(self):
        token = os.getenv("LOADTEST_ACCESS_TOKEN")
        if not token:
            response = self.client.post(
                "/api/v1/Auth/login",
                json={
                    "email": os.getenv("LOADTEST_EMAIL", "seller@sayarahub.local"),
                    "password": os.getenv("LOADTEST_PASSWORD", "SellerDemo_44"),
                },
                name="/api/v1/Auth/login [setup]",
            )
            if response.status_code != 200:
                raise StopUser()
            token = response.json()["data"]["token"]
        self.headers = {"Authorization": f"Bearer {token}"}

    @task(5)
    def filter_listings(self):
        self.client.get(
            "/api/v1/Cars",
            params={"search": "Toyota", "city": "Riyadh", "pageSize": 20},
            name="/api/v1/Cars [full-text filter]",
        )

    @task(4)
    def chat_list(self):
        self.client.get(
            "/api/v1/chats",
            params={"pageSize": 20},
            headers=self.headers,
            name="/api/v1/chats [annotated list]",
        )

    @task(3)
    def notification_cursor(self):
        self.client.get(
            "/api/v1/notifications",
            params={"pagination": "cursor", "pageSize": 25},
            headers=self.headers,
            name="/api/v1/notifications [cursor]",
        )

    @task(1)
    def websocket_reconnect(self):
        ticket_response = self.client.post(
            "/api/v1/Auth/websocket-ticket",
            headers=self.headers,
            name="/api/v1/Auth/websocket-ticket [reconnect]",
        )
        if ticket_response.status_code != 200:
            return
        ticket = ticket_response.json()["data"]["ticket"]
        parsed = urlparse(self.host)
        scheme = "wss" if parsed.scheme == "https" else "ws"
        socket = websocket.create_connection(
            f"{scheme}://{parsed.netloc}/ws/notifications/?ticket={ticket}&afterId=0",
            timeout=5,
        )
        socket.close()
