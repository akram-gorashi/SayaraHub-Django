from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.db.models import Q
from django.utils import timezone
from django.db import transaction
import asyncio
import json
import time
from marketplace import models
from marketplace.serializers import MessageSerializer, NotificationSerializer


@database_sync_to_async
def can_access_chat(user_id, chat_id):
    return models.Chat.objects.filter(id=chat_id).filter(Q(buyer_id=user_id) | Q(seller_id=user_id)).exists()


@database_sync_to_async
def missed_messages(chat_id, after_id):
    items = models.Message.objects.select_related("sender").filter(chat_id=chat_id, id__gt=after_id)[:100]
    return MessageSerializer(items, many=True).data


@database_sync_to_async
def missed_notifications(user_id, after_id):
    items = models.Notification.objects.filter(user_id=user_id, id__gt=after_id).order_by("id")[:100]
    return NotificationSerializer(items, many=True).data


@database_sync_to_async
def mark_chat_read(chat_id, user_id):
    return models.Message.objects.filter(chat_id=chat_id, is_read=False).exclude(sender_id=user_id).update(is_read=True)


@database_sync_to_async
@transaction.atomic
def change_presence(user_id, delta):
    presence, _ = models.UserRealtimePresence.objects.select_for_update().get_or_create(user_id=user_id)
    presence.connection_count = max(0, presence.connection_count + delta)
    if presence.connection_count == 0:
        presence.last_seen_at = timezone.now()
    presence.save(update_fields=["connection_count", "last_seen_at"])
    return presence.connection_count > 0, presence.last_seen_at, presence.connection_count


@database_sync_to_async
def touch_presence(user_id):
    models.UserRealtimePresence.objects.filter(user_id=user_id).update(updated_at=timezone.now())


class NotificationConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        if not self.scope["user"].is_authenticated:
            await self.close(code=4401)
            return
        self.group_name = f"user_{self.scope['user'].id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        query = self.scope["query_string"].decode()
        after = next((part.split("=", 1)[1] for part in query.split("&") if part.startswith("afterId=")), "0")
        for item in await missed_notifications(self.scope["user"].id, int(after or 0)):
            await self.send_json({"type": "notification.received", "notification": item, "catchUp": True})

    async def disconnect(self, code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def realtime_event(self, event):
        await self.send_json(event["payload"])


class ChatConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.chat_id = self.scope["url_route"]["kwargs"]["chat_id"]
        user = self.scope["user"]
        if not user.is_authenticated or not await can_access_chat(user.id, self.chat_id):
            await self.close(code=4403)
            return
        online, last_seen, count = await change_presence(user.id, 1)
        if count > 50:
            await change_presence(user.id, -1)
            await self.close(code=4429)
            return
        self.presence_registered = True
        self.group_name = f"chat_{self.chat_id}"
        self.typing_task = None
        self.presence_heartbeat_task = asyncio.create_task(self.presence_heartbeat())
        self.last_client_event_at = 0.0
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        query = self.scope["query_string"].decode()
        after = next((part.split("=", 1)[1] for part in query.split("&") if part.startswith("afterId=")), "0")
        for item in await missed_messages(self.chat_id, int(after or 0)):
            await self.send_json({"type": "message.received", "message": item, "catchUp": True})
        await self.channel_layer.group_send(self.group_name, {
            "type": "realtime.event",
            "payload": {"type": "presence.changed", "userId": user.id, "isOnline": online, "lastSeenAt": last_seen.isoformat() if last_seen else None},
        })

    async def disconnect(self, code):
        if hasattr(self, "group_name"):
            if self.typing_task:
                self.typing_task.cancel()
            if self.presence_heartbeat_task:
                self.presence_heartbeat_task.cancel()
            await self.channel_layer.group_discard(self.group_name, self.channel_name)
            user = self.scope["user"]
            online, last_seen, _ = await change_presence(user.id, -1)
            await self.channel_layer.group_send(self.group_name, {
                "type": "realtime.event",
                "payload": {"type": "presence.changed", "userId": user.id, "isOnline": online, "lastSeenAt": last_seen.isoformat() if last_seen else None},
            })

    async def receive_json(self, content):
        if len(json.dumps(content)) > 4096:
            await self.close(code=4409)
            return
        event_type = content.get("type")
        if event_type == "typing":
            now = time.monotonic()
            if now - self.last_client_event_at < 0.05:
                return
            self.last_client_event_at = now
            if self.typing_task:
                self.typing_task.cancel()
                self.typing_task = None
            await self.channel_layer.group_send(self.group_name, {
                "type": "realtime.event",
                "payload": {
                    "type": "typing.changed", "chatId": self.chat_id,
                    "userId": self.scope["user"].id, "isTyping": bool(content.get("isTyping")),
                },
            })
            if content.get("isTyping"):
                self.typing_task = asyncio.create_task(self.clear_typing_after_timeout())
        elif event_type == "read":
            count = await mark_chat_read(self.chat_id, self.scope["user"].id)
            await self.channel_layer.group_send(self.group_name, {
                "type": "realtime.event",
                "payload": {
                    "type": "messages.read", "chatId": self.chat_id,
                    "readerId": self.scope["user"].id, "markedReadCount": count,
                },
            })

    async def realtime_event(self, event):
        await self.send_json(event["payload"])

    async def clear_typing_after_timeout(self):
        try:
            await asyncio.sleep(3)
            await self.channel_layer.group_send(self.group_name, {
                "type": "realtime.event",
                "payload": {
                    "type": "typing.changed", "chatId": self.chat_id,
                    "userId": self.scope["user"].id, "isTyping": False,
                },
            })
        except asyncio.CancelledError:
            pass

    async def presence_heartbeat(self):
        try:
            while True:
                await asyncio.sleep(30)
                await touch_presence(self.scope["user"].id)
        except asyncio.CancelledError:
            pass
