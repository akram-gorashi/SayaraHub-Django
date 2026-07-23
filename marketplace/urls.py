from django.urls import include, path


urlpatterns = [
    path("", include("marketplace.modules.accounts.urls")),
    path("", include("marketplace.modules.catalog.urls")),
    path("", include("marketplace.modules.messaging.urls")),
    path("", include("marketplace.modules.reviews_safety.urls")),
    path("", include("marketplace.modules.moderation.urls")),
]
