from ninja import Router

from marketplace import views
from marketplace.api_view_bridge import register_api_view_definitions


router = Router(tags=["Administration & Moderation"])

API_VIEW_ROUTE_DEFINITIONS = [
    ("/admin/moderation/cars", views.AdminCarsView, ["GET"], "admin_car_list"),
    ("/admin/moderation/cars/{car_id}", views.AdminCarDetailView, ["GET", "PATCH"], "admin_car_detail"),
    ("/admin/moderation/cars/{car_id}/history", views.AdminModerationHistoryView, ["GET"], "admin_car_history"),
    ("/admin/moderation/audit-logs/export", views.AdminAuditLogsExportView, ["GET"], "admin_audit_export"),
    ("/admin/moderation/audit-logs", views.AdminAuditLogsView, ["GET"], "admin_audit_list"),
    ("/admin/moderation/statistics", views.AdminStatisticsView, ["GET"], "admin_statistics"),
    ("/admin/moderation/reports", views.AdminReportsView, ["GET"], "admin_report_list"),
    ("/admin/moderation/reports/{report_id}", views.AdminReportActionView, ["PATCH"], "admin_report_action"),
    ("/admin/moderation/reviews", views.AdminReviewsView, ["GET"], "admin_review_list"),
    ("/admin/moderation/reviews/{review_id}", views.AdminReviewActionView, ["PATCH"], "admin_review_action"),
    ("/admin/moderation/notification-dead-letters", views.AdminDeadLettersView, ["GET"], "admin_dead_letters"),
    ("/admin/moderation/notification-dead-letters/{event_id}/retry", views.AdminDeadLetterRetryView, ["POST"], "admin_dead_letter_retry"),
]

register_api_view_definitions(router, API_VIEW_ROUTE_DEFINITIONS)
