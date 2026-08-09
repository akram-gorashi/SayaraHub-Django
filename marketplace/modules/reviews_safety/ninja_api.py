from ninja import Router

from marketplace import views
from marketplace.api_view_bridge import register_api_view_definitions


router = Router(tags=["Reviews & Safety"])

API_VIEW_ROUTE_DEFINITIONS = [
    ("/sellers/{seller_id}/reviews", views.SellerReviewsView, ["GET", "POST"], "seller_reviews"),
    ("/reviews/mine", views.MyReviewsView, ["GET"], "review_mine"),
    ("/reviews/{review_id}", views.ReviewDetailView, ["PUT", "DELETE"], "review_detail"),
    ("/reports", views.ReportsView, ["GET", "POST"], "report_list_create"),
    ("/reports/mine", views.ReportsView, ["GET"], "report_mine"),
]

register_api_view_definitions(router, API_VIEW_ROUTE_DEFINITIONS)
