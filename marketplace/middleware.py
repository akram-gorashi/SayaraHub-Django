import time
import uuid
from prometheus_client import Counter, Histogram


REQUESTS = Counter(
    "sayarahub_http_requests_total", "HTTP requests", ("method", "status")
)
DURATION = Histogram(
    "sayarahub_http_request_duration_seconds", "HTTP request duration", ("method",)
)


class RequestMetricsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
        request.correlation_id = correlation_id
        started = time.monotonic()
        response = self.get_response(request)
        DURATION.labels(request.method).observe(time.monotonic() - started)
        REQUESTS.labels(request.method, response.status_code).inc()
        response["X-Correlation-ID"] = correlation_id
        response["X-Content-Type-Options"] = "nosniff"
        response["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response
