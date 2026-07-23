from django.urls import path
from . import views

urlpatterns = [
    path("sellers/<int:seller_id>/reviews", views.SellerReviewsView.as_view()),
    path("reviews/mine", views.MyReviewsView.as_view()),
    path("reviews/<int:review_id>", views.ReviewDetailView.as_view()),
    path("reports", views.ReportsView.as_view()),
    path("reports/mine", views.ReportsView.as_view()),
]
