from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from marketplace.views import health, health_ready


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include("marketplace.urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("health/", health),
    path("health/live", health),
    path("health/ready", health_ready),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
