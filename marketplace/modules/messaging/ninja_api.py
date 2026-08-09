from ninja import Router

from marketplace import views
from marketplace.api_view_bridge import register_api_view_definitions


router = Router(tags=["Messaging & Notifications"])

API_VIEW_ROUTE_DEFINITIONS = [
    ("/cars/{car_id}/chats", views.CreateChatView, ["POST"], "chat_create"),
    ("/chats", views.ChatsView, ["GET"], "chat_list"),
    ("/chats/{chat_id}/messages", views.ChatMessagesView, ["GET", "POST"], "chat_messages"),
    ("/chats/{chat_id}/read", views.ChatReadView, ["PATCH"], "chat_read"),
    ("/cars/{car_id}/contact-messages", views.ContactCreateView, ["POST"], "contact_create"),
    ("/seller/contact-messages", views.ContactInboxView, ["GET"], "contact_inbox"),
    ("/seller/contact-messages/{contact_id}/read", views.ContactDetailView, ["PATCH"], "contact_read"),
    ("/seller/contact-messages/{contact_id}", views.ContactDetailView, ["GET", "DELETE"], "contact_detail"),
    ("/notifications", views.NotificationsView, ["GET"], "notification_list"),
    ("/notifications/unread-count", views.NotificationUnreadView, ["GET"], "notification_unread_count"),
    ("/notifications/read-all", views.NotificationReadAllView, ["PATCH"], "notification_read_all"),
    ("/notifications/preferences", views.NotificationPreferencesView, ["GET", "PUT"], "notification_preferences"),
    ("/notifications/{notification_id}/read", views.NotificationActionView, ["PATCH"], "notification_read"),
    ("/notifications/{notification_id}", views.NotificationActionView, ["DELETE"], "notification_delete"),
]

register_api_view_definitions(router, API_VIEW_ROUTE_DEFINITIONS)
