from django.urls import path
from . import views

urlpatterns = [
    path("cars/<int:car_id>/chats", views.CreateChatView.as_view()),
    path("chats", views.ChatsView.as_view()),
    path("chats/<int:chat_id>/messages", views.ChatMessagesView.as_view()),
    path("chats/<int:chat_id>/read", views.ChatReadView.as_view()),
    path("cars/<int:car_id>/contact-messages", views.ContactCreateView.as_view()),
    path("seller/contact-messages", views.ContactInboxView.as_view()),
    path("seller/contact-messages/<int:contact_id>", views.ContactDetailView.as_view()),
    path("seller/contact-messages/<int:contact_id>/read", views.ContactDetailView.as_view()),
    path("notifications", views.NotificationsView.as_view()),
    path("notifications/unread-count", views.NotificationUnreadView.as_view()),
    path("notifications/read-all", views.NotificationReadAllView.as_view()),
    path("notifications/preferences", views.NotificationPreferencesView.as_view()),
    path("notifications/<int:notification_id>/read", views.NotificationActionView.as_view()),
    path("notifications/<int:notification_id>", views.NotificationActionView.as_view()),
]
