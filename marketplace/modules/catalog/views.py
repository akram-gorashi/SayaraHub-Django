"""Vehicle catalog, lookup data, seller dashboard, draft, and saved-search endpoints."""
from marketplace.views import (
    BrandModelsView, CarDetailView, CarListCreateView, CarUploadView, FavoriteActionView, FavoritesView,
    ListingDraftView, MasterDataListView, MyCarsView, RelatedCarsView, SavedSearchDetailView,
    SavedSearchListView, SellerCarsPublicView, SellerCarStatusView, SellerDashboardView,
    VehicleHistoryDetailView, VehicleHistoryListView, SellerCarDetailView, SellerCarImagesView,
    SellerCarImageRetryView,
)
from marketplace.openapi import tag_views

tag_views(
    "Catalog & Listings",
    BrandModelsView, CarDetailView, CarListCreateView, CarUploadView, FavoriteActionView, FavoritesView,
    ListingDraftView, MasterDataListView, MyCarsView, RelatedCarsView, SavedSearchDetailView,
    SavedSearchListView, SellerCarsPublicView, SellerCarStatusView, SellerDashboardView,
    VehicleHistoryDetailView, VehicleHistoryListView, SellerCarDetailView, SellerCarImagesView,
    SellerCarImageRetryView,
)

__all__ = [name for name in globals() if name.endswith("View")]
