"""Administrator moderation endpoints."""
from marketplace.views import (
    AdminCarDetailView, AdminCarsView, AdminReportActionView, AdminReportsView,
    AdminReviewActionView, AdminReviewsView, AdminStatisticsView,
    AdminModerationHistoryView, AdminAuditLogsView, AdminAuditLogsExportView,
    AdminDeadLettersView, AdminDeadLetterRetryView,
)
from marketplace.openapi import tag_views

tag_views(
    "Administration & Moderation",
    AdminCarDetailView, AdminCarsView, AdminReportActionView, AdminReportsView,
    AdminReviewActionView, AdminReviewsView, AdminStatisticsView,
    AdminModerationHistoryView, AdminAuditLogsView, AdminAuditLogsExportView,
    AdminDeadLettersView, AdminDeadLetterRetryView,
)

__all__ = [name for name in globals() if name.endswith("View")]
