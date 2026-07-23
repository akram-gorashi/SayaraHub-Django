"""Account, authentication, profile, privacy, and blocking endpoints."""
from marketplace.views import (
    AuthLoginView, AuthRefreshView, AuthRegisterView, AuthRevokeAllView, AuthRevokeView,
    AuthSessionsView, AuthSessionDetailView, AuthRevokeOtherSessionsView, WebSocketTicketView,
    BlockedUsersView, BlockUserView, ChangePasswordView, CloseAccountView,
    PublicUserView, SettingsView, UserImageView, UserMeView,
)
from marketplace.openapi import tag_views

tag_views(
    "Accounts",
    AuthLoginView, AuthRefreshView, AuthRegisterView, AuthRevokeAllView, AuthRevokeView,
    AuthSessionsView, AuthSessionDetailView, AuthRevokeOtherSessionsView, WebSocketTicketView,
    BlockedUsersView, BlockUserView, ChangePasswordView, CloseAccountView,
    PublicUserView, SettingsView, UserImageView, UserMeView,
)

__all__ = [name for name in globals() if name.endswith("View")]
