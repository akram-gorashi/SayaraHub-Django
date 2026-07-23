from django.urls import path
from . import views

urlpatterns = [
    path("admin/moderation/cars", views.AdminCarsView.as_view()),
    path("admin/moderation/cars/<int:car_id>", views.AdminCarDetailView.as_view()),
    path("admin/moderation/cars/<int:car_id>/history", views.AdminModerationHistoryView.as_view()),
    path("admin/moderation/audit-logs", views.AdminAuditLogsView.as_view()),
    path("admin/moderation/audit-logs/export", views.AdminAuditLogsExportView.as_view()),
    path("admin/moderation/statistics", views.AdminStatisticsView.as_view()),
    path("admin/moderation/reports", views.AdminReportsView.as_view()),
    path("admin/moderation/reports/<int:report_id>", views.AdminReportActionView.as_view()),
    path("admin/moderation/reviews", views.AdminReviewsView.as_view()),
    path("admin/moderation/reviews/<int:review_id>", views.AdminReviewActionView.as_view()),
    path("admin/moderation/notification-dead-letters", views.AdminDeadLettersView.as_view()),
    path("admin/moderation/notification-dead-letters/<uuid:event_id>/retry", views.AdminDeadLetterRetryView.as_view()),
]
