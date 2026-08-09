from math import ceil
from django.core import signing
from django.db.models import Q
from django.utils.dateparse import parse_datetime
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler


def ok(data=None, message="Success", status=200):
    return Response({"success": True, "message": message, "data": data}, status=status)


def fail(message, data=None, status=400):
    return Response({"success": False, "message": message, "data": data}, status=status)


def page(request, queryset, serializer_class):
    try:
        number = max(1, int(request.query_params.get("pageNumber", 1)))
        size = min(100, max(1, int(request.query_params.get("pageSize", 10))))
    except ValueError:
        number, size = 1, 10
    total = queryset.count()
    items = serializer_class(queryset[(number - 1) * size:number * size], many=True, context={"request": request}).data
    pages = ceil(total / size) if total else 0
    return {
        "items": items, "pageNumber": number, "pageSize": size, "totalCount": total,
        "totalPages": pages, "hasPreviousPage": number > 1, "hasNextPage": number < pages,
    }


def cursor_requested(request):
    return request.query_params.get("pagination") == "cursor" or "cursor" in request.query_params


def cursor_page(request, queryset, serializer_class, timestamp_field):
    try:
        size = min(100, max(1, int(request.query_params.get("pageSize", 25))))
    except ValueError:
        size = 25

    token = request.query_params.get("cursor")
    if token:
        try:
            cursor = signing.loads(token, salt=f"sayarahub.cursor.{timestamp_field}", max_age=2_592_000)
            timestamp = parse_datetime(cursor["timestamp"])
            object_id = int(cursor["id"])
            if timestamp is None:
                raise ValueError
        except (signing.BadSignature, KeyError, TypeError, ValueError):
            raise ValidationError({"cursor": "The cursor is invalid or has expired."})
        queryset = queryset.filter(
            Q(**{f"{timestamp_field}__lt": timestamp})
            | Q(**{timestamp_field: timestamp, "id__lt": object_id})
        )

    rows = list(queryset.order_by(f"-{timestamp_field}", "-id")[: size + 1])
    has_next = len(rows) > size
    rows = rows[:size]
    next_cursor = None
    if has_next and rows:
        last = rows[-1]
        next_cursor = signing.dumps(
            {"timestamp": getattr(last, timestamp_field).isoformat(), "id": last.id},
            salt=f"sayarahub.cursor.{timestamp_field}",
            compress=True,
        )
    items = serializer_class(rows, many=True, context={"request": request}).data
    return {
        "items": items,
        "pageSize": size,
        "nextCursor": next_cursor,
        "hasNextPage": has_next,
        "paginationMode": "cursor",
    }


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        return response
    details = response.data
    message = "Validation failed" if response.status_code == 400 else str(getattr(exc, "detail", "Request failed"))
    response.data = {"success": False, "message": message, "data": details}
    return response
