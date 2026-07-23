"""Chat, inquiry, and notification endpoints."""
from marketplace.views import (
    ChatMessagesView, ChatReadView, ChatsView, ContactCreateView, ContactDetailView,
    ContactInboxView, CreateChatView, NotificationActionView, NotificationReadAllView,
    NotificationsView, NotificationUnreadView, NotificationPreferencesView,
)
from marketplace.openapi import tag_views

tag_views(
    "Messaging & Notifications",
    ChatMessagesView, ChatReadView, ChatsView, ContactCreateView, ContactDetailView,
    ContactInboxView, CreateChatView, NotificationActionView, NotificationReadAllView,
    NotificationsView, NotificationUnreadView, NotificationPreferencesView,
)

__all__ = [name for name in globals() if name.endswith("View")]
