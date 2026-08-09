from math import ceil
from django.db.models import Manager, QuerySet
from ninja import Field, Query, Router, Schema
from ninja.errors import HttpError

from marketplace import models, views
from marketplace.api_view_bridge import register_api_view, register_api_view_definitions


router = Router(tags=["Catalog & Listings"])


class PaginationQuery(Schema):
    page_number: int = Field(1, alias="pageNumber", ge=1)
    page_size: int = Field(10, alias="pageSize", ge=1, le=100)
    name: str | None = None


class MasterDataItem(Schema):
    id: int
    name: str


class CarModelItem(MasterDataItem):
    carBrandId: int
    carBrandName: str


class MasterDataPage(Schema):
    items: list[MasterDataItem]
    pageNumber: int
    pageSize: int
    totalCount: int
    totalPages: int
    hasPreviousPage: bool
    hasNextPage: bool


class CarModelPage(Schema):
    items: list[CarModelItem]
    pageNumber: int
    pageSize: int
    totalCount: int
    totalPages: int
    hasPreviousPage: bool
    hasNextPage: bool


class MasterDataCollections(Schema):
    bodyTypes: MasterDataPage
    carBrands: MasterDataPage
    carModels: CarModelPage
    carConditions: MasterDataPage
    features: MasterDataPage
    fuelTypes: MasterDataPage
    transmissions: MasterDataPage


class MasterDataPageEnvelope(Schema):
    success: bool = True
    message: str = "Success"
    data: MasterDataPage


class CarModelPageEnvelope(Schema):
    success: bool = True
    message: str = "Success"
    data: CarModelPage


class MasterDataCollectionsEnvelope(Schema):
    success: bool = True
    message: str = "Success"
    data: MasterDataCollections


MASTER_MANAGERS: dict[str, Manager] = {
    "body-types": models.BodyType.objects,
    "car-brands": models.CarBrand.objects,
    "car-models": models.CarModel.objects,
    "car-conditions": models.CarCondition.objects,
    "features": models.Feature.objects,
    "fuel-types": models.FuelType.objects,
    "transmissions": models.Transmission.objects,
}


def _page(queryset: QuerySet, query: PaginationQuery, *, car_models: bool = False) -> dict:
    total = queryset.count()
    start = (query.page_number - 1) * query.page_size
    rows = queryset[start : start + query.page_size]
    if car_models:
        items = [
            {
                "id": item.id,
                "name": item.name,
                "carBrandId": item.brand_id,
                "carBrandName": item.brand.name,
            }
            for item in rows
        ]
    else:
        items = [{"id": item.id, "name": item.name} for item in rows]
    total_pages = ceil(total / query.page_size) if total else 0
    return {
        "items": items,
        "pageNumber": query.page_number,
        "pageSize": query.page_size,
        "totalCount": total,
        "totalPages": total_pages,
        "hasPreviousPage": query.page_number > 1,
        "hasNextPage": query.page_number < total_pages,
    }


def _queryset(kind: str, name: str | None = None) -> QuerySet:
    manager = MASTER_MANAGERS.get(kind)
    if manager is None:
        raise HttpError(404, f"Unknown master-data kind: {kind}")
    queryset = manager.all()
    if kind == "car-models":
        queryset = queryset.select_related("brand")
    if name:
        queryset = queryset.filter(name__icontains=name)
    return queryset


@router.get("/MasterData", response=MasterDataCollectionsEnvelope, operation_id="list_all_master_data")
@router.get("/masterdata", response=MasterDataCollectionsEnvelope, include_in_schema=False)
def list_all_master_data(request, query: Query[PaginationQuery]):
    keys = {
        "bodyTypes": "body-types",
        "carBrands": "car-brands",
        "carModels": "car-models",
        "carConditions": "car-conditions",
        "features": "features",
        "fuelTypes": "fuel-types",
        "transmissions": "transmissions",
    }
    data = {
        output: _page(_queryset(kind), query, car_models=kind == "car-models")
        for output, kind in keys.items()
    }
    return {"success": True, "message": "Success", "data": data}


@router.get(
    "/MasterData/car-brands/{brand_id}/models",
    response=CarModelPageEnvelope,
    operation_id="list_car_models_by_brand",
)
@router.get(
    "/masterdata/car-brands/{brand_id}/models",
    response=CarModelPageEnvelope,
    include_in_schema=False,
)
def list_car_models_by_brand(request, brand_id: int, query: Query[PaginationQuery]):
    queryset = models.CarModel.objects.select_related("brand").filter(brand_id=brand_id)
    return {"success": True, "message": "Success", "data": _page(queryset, query, car_models=True)}


@router.get(
    "/MasterData/{kind}",
    response={200: MasterDataPageEnvelope | CarModelPageEnvelope},
    operation_id="list_master_data_category",
)
@router.get(
    "/masterdata/{kind}",
    response={200: MasterDataPageEnvelope | CarModelPageEnvelope},
    include_in_schema=False,
)
def list_master_data_category(request, kind: str, query: Query[PaginationQuery]):
    data = _page(_queryset(kind, query.name), query, car_models=kind == "car-models")
    return {"success": True, "message": "Success", "data": data}


API_VIEW_ROUTE_DEFINITIONS = [
    ("/Cars", views.CarListCreateView, ["GET", "POST"], "car_list_create"),
    ("/Cars/filter", views.CarListCreateView, ["GET"], "car_filter"),
    ("/Cars/mine", views.MyCarsView, ["GET"], "car_mine"),
    ("/Cars/favorites", views.FavoritesView, ["GET"], "car_favorites"),
    ("/Cars/upload", views.CarUploadView, ["POST"], "car_upload"),
    ("/Cars/seller/{seller_id}", views.SellerCarsPublicView, ["GET"], "car_seller_list"),
    ("/Cars/{car_id}/related", views.RelatedCarsView, ["GET"], "car_related"),
    ("/Cars/{car_id}/favorite", views.FavoriteActionView, ["POST", "DELETE"], "car_favorite_action"),
    ("/Cars/{car_id}", views.CarDetailView, ["GET", "PUT", "DELETE"], "car_detail"),
    ("/cars/{car_id}/history", views.VehicleHistoryListView, ["GET", "POST"], "vehicle_history_list"),
    ("/vehicle-history/{history_id}", views.VehicleHistoryDetailView, ["PUT", "DELETE"], "vehicle_history_detail"),
    ("/seller/cars", views.MyCarsView, ["GET"], "seller_car_list"),
    ("/seller/cars/{car_id}/images/{image_id}/retry", views.SellerCarImageRetryView, ["POST"], "seller_image_retry"),
    ("/seller/cars/{car_id}/images", views.SellerCarImagesView, ["GET"], "seller_car_images"),
    ("/seller/cars/{car_id}/status", views.SellerCarStatusView, ["PATCH"], "seller_car_status"),
    ("/seller/cars/{car_id}", views.SellerCarDetailView, ["GET"], "seller_car_detail"),
    ("/seller/statistics", views.SellerDashboardView, ["GET"], "seller_statistics"),
    ("/seller/listing-draft", views.ListingDraftView, ["GET", "PUT", "DELETE"], "seller_listing_draft"),
    ("/saved-searches", views.SavedSearchListView, ["GET", "POST"], "saved_search_list"),
    ("/saved-searches/{search_id}", views.SavedSearchDetailView, ["PUT", "DELETE"], "saved_search_detail"),
]

register_api_view_definitions(router, API_VIEW_ROUTE_DEFINITIONS)

# Preserve lowercase car aliases without duplicating them in handwritten code.
for path, view_class, methods, operation_id in API_VIEW_ROUTE_DEFINITIONS[:9]:
    register_api_view(
        router,
        path.replace("/Cars", "/cars", 1),
        view_class,
        methods,
        operation_id=f"{operation_id}_lowercase",
    )
