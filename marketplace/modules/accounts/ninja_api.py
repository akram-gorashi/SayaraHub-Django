from ninja import Router

from marketplace import views
from marketplace.api_view_bridge import register_api_view, register_api_view_definitions


router = Router(tags=["Accounts"])


API_VIEW_ROUTE_DEFINITIONS = [
    ("/Auth/register", views.AuthRegisterView, ["POST"], "auth_register"),
    ("/Auth/login", views.AuthLoginView, ["POST"], "auth_login"),
    ("/Auth/refresh", views.AuthRefreshView, ["POST"], "auth_refresh"),
    ("/Auth/revoke", views.AuthRevokeView, ["POST"], "auth_revoke"),
    ("/Auth/revoke-all", views.AuthRevokeAllView, ["POST"], "auth_revoke_all"),
    ("/Auth/sessions", views.AuthSessionsView, ["GET"], "auth_sessions"),
    ("/Auth/sessions/revoke-others", views.AuthRevokeOtherSessionsView, ["POST"], "auth_revoke_others"),
    ("/Auth/sessions/{session_id}", views.AuthSessionDetailView, ["DELETE"], "auth_session_revoke"),
    ("/Auth/websocket-ticket", views.WebSocketTicketView, ["POST"], "auth_websocket_ticket"),
    ("/users/me", views.UserMeView, ["GET", "PUT"], "user_me"),
    ("/users/me/password", views.ChangePasswordView, ["PUT"], "user_password"),
    ("/users/me/image", views.UserImageView, ["POST", "DELETE"], "user_image"),
    ("/users/me/blocked", views.BlockedUsersView, ["GET"], "user_blocked_list"),
    ("/users/{user_id}/block", views.BlockUserView, ["POST", "DELETE"], "user_block_action"),
    ("/users/{user_id}", views.PublicUserView, ["GET"], "user_public_profile"),
    ("/settings", views.SettingsView, ["GET", "PUT"], "user_settings"),
    ("/settings/account", views.CloseAccountView, ["DELETE"], "user_close_account"),
    ("/features", views.FeatureFlagsView, ["GET"], "feature_flags"),
]

register_api_view_definitions(router, API_VIEW_ROUTE_DEFINITIONS)

# Preserve the lowercase authentication aliases used by some clients.
for path, view_class, methods, operation_id in API_VIEW_ROUTE_DEFINITIONS[:9]:
    register_api_view(
        router,
        path.replace("/Auth/", "/auth/"),
        view_class,
        methods,
        operation_id=f"{operation_id}_lowercase",
    )
