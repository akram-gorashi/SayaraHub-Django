import json

from django.core.management.base import BaseCommand, CommandError

from config.api import api


REQUIRED_API_PATHS = {
    "/api/v1/Auth/login",
    "/api/v1/Cars",
    "/api/v1/MasterData",
    "/api/v1/admin/moderation/cars",
    "/api/v1/chats",
    "/api/v1/notifications",
    "/api/v1/users/me",
}


class Command(BaseCommand):
    help = "Validate that the Django Ninja OpenAPI schema is serializable and covers every API module."

    def handle(self, *args, **options):
        schema = api.get_openapi_schema(path_prefix="/api/v1")
        json.dumps(schema)
        paths = schema.get("paths", {})
        missing_paths = sorted(REQUIRED_API_PATHS - paths.keys())
        if missing_paths:
            raise CommandError(f"Ninja OpenAPI schema is missing paths: {', '.join(missing_paths)}")
        if len(paths) < 90:
            raise CommandError(f"Expected at least 90 API paths, found {len(paths)}")
        operation_count = sum(
            method in {"get", "post", "put", "patch", "delete"}
            for path_item in paths.values()
            for method in path_item
        )
        self.stdout.write(self.style.SUCCESS(f"Ninja OpenAPI is valid: {len(paths)} paths, {operation_count} operations."))
