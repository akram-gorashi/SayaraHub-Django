"""Django Ninja registration bridge for APIView implementations awaiting native rewrites.

All public URL matching is owned by Django Ninja. This bridge preserves the mature request parsing,
authentication, throttling, serializers, and response behavior of an existing APIView until that
operation is rewritten. Keeping the adapter centralized makes remaining migration work explicit.
"""

from collections.abc import Iterable
from functools import wraps
from inspect import Parameter, Signature
from uuid import UUID

from ninja import Router


ApiViewRouteDefinition = tuple[str, type, Iterable[str], str]


def register_api_view_definitions(
    router: Router,
    route_definitions: Iterable[ApiViewRouteDefinition],
) -> None:
    """Register a collection of named APIView route definitions."""
    for path, view_class, methods, operation_id in route_definitions:
        register_api_view(router, path, view_class, methods, operation_id=operation_id)


def register_api_view(
    router: Router,
    path: str,
    view_class,
    methods: Iterable[str],
    *,
    operation_id: str,
) -> None:
    """Register an APIView as a Ninja operation while preserving its HTTP contract."""
    django_view = view_class.as_view()

    @wraps(django_view)
    def dispatch_api_view(request, **path_parameters):
        return django_view(request, **path_parameters)

    parameters = [Parameter("request", Parameter.POSITIONAL_OR_KEYWORD)]
    for field_name in _extract_path_parameter_names(path):
        annotation = UUID if field_name == "event_id" else str if field_name == "session_id" else int
        parameters.append(Parameter(field_name, Parameter.POSITIONAL_OR_KEYWORD, annotation=annotation))
    dispatch_api_view.__signature__ = Signature(parameters)  # type: ignore[attr-defined]

    router.api_operation(
        [method.upper() for method in methods],
        path,
        response=None,
        auth=None,
        operation_id=operation_id,
    )(dispatch_api_view)


def _extract_path_parameter_names(path: str) -> list[str]:
    return [segment[1:-1] for segment in path.split("/") if segment.startswith("{") and segment.endswith("}")]
