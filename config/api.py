from ninja import NinjaAPI
from ninja.errors import HttpError, ValidationError

from marketplace.modules.accounts.ninja_api import router as accounts_router
from marketplace.modules.catalog.ninja_api import router as catalog_router
from marketplace.modules.messaging.ninja_api import router as messaging_router
from marketplace.modules.moderation.ninja_api import router as moderation_router
from marketplace.modules.reviews_safety.ninja_api import router as reviews_router


api = NinjaAPI(
    title="SayaraHub API",
    version="1.0.0",
    description="Typed Django Ninja endpoints. Remaining v1 endpoints continue to use DRF during migration.",
    docs_url="/docs/",
    urls_namespace="sayarahub_ninja",
)


@api.exception_handler(ValidationError)
def validation_error(request, exc):
    """Keep validation failures inside the API's established response envelope."""
    return api.create_response(
        request,
        {"success": False, "message": "Validation failed", "data": exc.errors},
        status=422,
    )


@api.exception_handler(HttpError)
def http_error(request, exc):
    return api.create_response(
        request,
        {"success": False, "message": exc.message, "data": None},
        status=exc.status_code,
    )


api.add_router("", accounts_router)
api.add_router("", catalog_router)
api.add_router("", messaging_router)
api.add_router("", reviews_router)
api.add_router("", moderation_router)
