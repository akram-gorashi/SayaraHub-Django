from math import ceil
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


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        return response
    details = response.data
    message = "Validation failed" if response.status_code == 400 else str(getattr(exc, "detail", "Request failed"))
    response.data = {"success": False, "message": message, "data": details}
    return response
