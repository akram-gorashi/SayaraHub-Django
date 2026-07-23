from asgiref.sync import async_to_sync
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.test import TransactionTestCase, override_settings
from django.core.management import call_command
from django.core.cache import cache
from rest_framework_simplejwt.tokens import RefreshToken
from marketplace import models
from marketplace.realtime.middleware import JwtAuthMiddleware
from marketplace.realtime.routing import websocket_urlpatterns


IN_MEMORY_CHANNELS = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
}
IN_MEMORY_CACHE = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}


@override_settings(CHANNEL_LAYERS=IN_MEMORY_CHANNELS, CACHES=IN_MEMORY_CACHE)
class RealtimeTests(TransactionTestCase):
    def setUp(self):
        self.user = models.User.objects.create_user(
            email="socket@example.com", password="StrongPass_123!", full_name="Socket User"
        )

    def test_notification_socket_authenticates_and_catches_up(self):
        notification = models.Notification.objects.create(
            user=self.user, type="Test", title="Realtime", message="Delivered after reconnect"
        )
        ticket = "one-time-notification-ticket"
        cache.set(f"ws-ticket:{ticket}", self.user.id, timeout=30)
        application = JwtAuthMiddleware(URLRouter(websocket_urlpatterns))

        async def scenario():
            socket = WebsocketCommunicator(
                application, f"/ws/notifications/?ticket={ticket}&afterId=0"
            )
            connected, _ = await socket.connect()
            self.assertTrue(connected)
            event = await socket.receive_json_from()
            self.assertEqual(event["type"], "notification.received")
            self.assertEqual(event["notification"]["id"], notification.id)
            self.assertTrue(event["catchUp"])
            await socket.disconnect()

            replay = WebsocketCommunicator(
                application, f"/ws/notifications/?ticket={ticket}&afterId=0"
            )
            connected_again, _ = await replay.connect()
            self.assertFalse(connected_again)

        async_to_sync(scenario)()

    def test_chat_socket_catches_up_and_emits_typing_and_read_receipt(self):
        call_command("seed_demo", verbosity=0)
        car = models.Car.objects.get(title="2024 Toyota Camry")
        chat = models.Chat.objects.create(car=car, buyer=self.user, seller=car.seller)
        message = models.Message.objects.create(chat=chat, sender=car.seller, content="Still interested?")
        token = str(RefreshToken.for_user(self.user).access_token)
        application = JwtAuthMiddleware(URLRouter(websocket_urlpatterns))

        async def receive_type(socket, event_type):
            for _ in range(5):
                event = await socket.receive_json_from()
                if event["type"] == event_type:
                    return event
            self.fail(f"Did not receive {event_type}")

        async def scenario():
            socket = WebsocketCommunicator(
                application, f"/ws/chats/{chat.id}/?token={token}&afterId=0"
            )
            connected, _ = await socket.connect()
            self.assertTrue(connected)
            caught_up = await receive_type(socket, "message.received")
            self.assertEqual(caught_up["message"]["id"], message.id)

            await socket.send_json_to({"type": "typing", "isTyping": True})
            typing = await receive_type(socket, "typing.changed")
            self.assertTrue(typing["isTyping"])

            await socket.send_json_to({"type": "read"})
            receipt = await receive_type(socket, "messages.read")
            self.assertEqual(receipt["readerId"], self.user.id)
            self.assertEqual(receipt["markedReadCount"], 1)
            await socket.disconnect()

        async_to_sync(scenario)()
        message.refresh_from_db()
        self.assertTrue(message.is_read)
