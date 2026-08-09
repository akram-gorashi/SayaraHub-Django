# Django Ninja migration

All SayaraHub HTTP API URLs are now owned by modular Django Ninja routers. Existing paths, lowercase aliases,
Angular response envelopes, JWT behavior, multipart parsing, throttling, and side effects remain unchanged.

The master-data endpoints are native Ninja operations. The remaining operations currently use the centralized
`marketplace.api_view_bridge` dispatch adapter around their proven APIView bodies. This removes the old Django URL
fallback while allowing each implementation to be rewritten behind a stable Angular contract. The bridge is
explicit migration debt; DRF dependencies must remain installed until its final registration is removed.

## How the new request path works

1. Django matches `api/v1/` to the `NinjaAPI` instance in `config/urls.py`.
2. The catalog `Router` matches the HTTP method and typed path in `marketplace/modules/catalog/ninja_api.py`.
3. `PaginationQuery` reads, converts, and validates `pageNumber`, `pageSize`, and `name` with Pydantic.
4. The operation uses the normal Django ORM. Django models and migrations do not change.
5. The declared response schema validates and serializes the result and supplies its OpenAPI contract.
6. Other module routers currently dispatch through the compatibility bridge, which preserves their existing
   authentication, parsing, serializer, throttle, and response behavior.

Interactive Ninja documentation is at `/api/v1/docs/`. The compatibility URL `/api/docs/` redirects there.

## Converting the remaining modules

Replace bridge registrations one module at a time: define request and response `Schema` classes, implement native
router functions, port authentication/authorization and throttles explicitly, preserve the response envelope,
and run contract tests. Remove each APIView only after its Ninja replacement covers successful requests,
validation failures, authorization, pagination, file uploads, idempotency, and side effects. Remove DRF,
drf-spectacular, the bridge, and the old URL modules only after the final registration has been replaced.
