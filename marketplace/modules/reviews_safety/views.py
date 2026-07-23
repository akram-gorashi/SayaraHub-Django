"""Seller reviews and user-reporting endpoints."""
from marketplace.views import MyReviewsView, ReportsView, ReviewDetailView, SellerReviewsView
from marketplace.openapi import tag_views

tag_views("Reviews & Safety", MyReviewsView, ReportsView, ReviewDetailView, SellerReviewsView)

__all__ = [name for name in globals() if name.endswith("View")]
