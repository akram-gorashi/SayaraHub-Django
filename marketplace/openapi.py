from drf_spectacular.utils import extend_schema, extend_schema_view


HTTP_METHODS = ("get", "post", "put", "patch", "delete")


def tag_views(tag, *view_classes):
    """Assign one Swagger/OpenAPI tag to every implemented method on each view."""
    for view_class in view_classes:
        methods = {
            method: extend_schema(tags=[tag])
            for method in HTTP_METHODS
            if method in view_class.__dict__
        }
        if methods:
            extend_schema_view(**methods)(view_class)
