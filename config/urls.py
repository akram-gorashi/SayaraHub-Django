from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path
from django.views.generic import RedirectView

from config.api import api
from marketplace.views import health, health_ready, metrics


urlpatterns = [
    path("admin/", admin.site.urls),
    # Every HTTP API route is owned by the modular Django Ninja API.
    path("api/v1/", api.urls),
    path("api/schema/", RedirectView.as_view(url="/api/v1/openapi.json", permanent=False), name="api-schema"),
    path("api/docs/", RedirectView.as_view(url="/api/v1/docs/", permanent=False), name="api-docs"),
    path("health/", health),
    path("health/live", health),
    path("health/ready", health_ready),
    path("metrics", metrics),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
