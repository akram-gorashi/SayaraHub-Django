# SayaraHub Django REST practice backend

This is an interview-focused reimplementation of the existing ASP.NET SayaraHub API using
Django, Django REST Framework, SimpleJWT, and PostgreSQL. It preserves the Angular app's
`/api/v1` routes, camelCase request/response fields, and `{ success, message, data }` envelope.

## Run with PostgreSQL

PowerShell:

```powershell
cd C:\Projects\SayaraHub_Full_stack\SayaraHub-Django
Copy-Item .env.example .env
docker compose up -d --build
docker compose ps
```

Git Bash:

```bash
cd /c/Projects/SayaraHub_Full_stack/SayaraHub-Django
cp .env.example .env
docker compose up -d --build
docker compose ps
```

- API: `http://localhost:8000/api/v1`
- Django Ninja Swagger (migrated endpoints): `http://localhost:8000/api/v1/docs/`
- Compatibility docs URL (redirects to Ninja): `http://localhost:8000/api/docs/`
- Migration guide: [`docs/DJANGO_NINJA_MIGRATION.md`](docs/DJANGO_NINJA_MIGRATION.md)
- Django admin: `http://localhost:8000/admin/`
- Health: `http://localhost:8000/health/ready`

Demo accounts (when `SEED_DEMO_DATA=true`):

- Seller: `seller@sayarahub.local` / `SellerDemo_44`
- Admin: `admin@sayarahub.local` / `AdminDemo_44`

To point the existing Angular frontend at Django, proxy `/api` to `http://localhost:8000`
instead of the .NET service.

## Run locally without Docker

PostgreSQL is the normal database. SQLite is intentionally available only as a fast practice/test fallback:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:DATABASE_ENGINE = "sqlite"
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

Run tests:

```powershell
$env:DATABASE_ENGINE = "sqlite"
python manage.py test
```

## What to explain in an interview

1. `User` extends `AbstractUser`, makes email the login identifier, and stores profile/privacy settings.
2. Lookup tables use protected foreign keys so a brand or transmission in use cannot be deleted.
3. Database constraints enforce one favorite per user/car, one review per reviewer/seller, one chat per buyer/car, and one main image per car.
4. Public listing queries expose only `Available` cars. Owners see their own pending/rejected listings; admins see all.
5. Serializers validate transport data and cross-field rules (for example, a model must belong to its brand).
6. Views enforce object-level ownership and use `transaction.atomic` where one request writes several records.
7. `select_related` and `prefetch_related` prevent N+1 queries; indexes support common status/city/price filters.
8. JWT access tokens keep API calls stateless. Refresh endpoints provide longer-lived session renewal.
9. Moderation changes both listing state and history and creates a persistent user notification in one transaction.
10. PostgreSQL is used in Docker/production, while tests use an isolated database.

## Feature-module layout

```text
marketplace/
  modules/
    accounts/          authentication, profiles, settings, blocking
    catalog/           master data, cars, favorites, seller tools
    messaging/         chats, contact inbox, notifications
    reviews_safety/    reviews and reports
    moderation/        administrator workflows
  models.py            Django model registry and relationships
  serializers.py       shared API contracts and command schemas
  views.py             shared endpoint implementations
  responses.py         common response envelope and pagination
```

Each feature owns its `urls.py` and exposes only its relevant views and models. The shared
model registry deliberately remains one Django app so the existing migration history and
foreign-key labels stay stable. In a larger independent service, the same boundaries can be
promoted into separate Django apps with their own migrations.

## Practice exercises

- Replace the APIView classes with DRF ViewSets and routers.
- Add an end-to-end feature-flag administration screen to the Angular application.
- Replace local media volumes with S3-compatible object storage.
- Add Grafana dashboards for the exposed Prometheus metrics.
- Add browser end-to-end tests for reconnect and offline catch-up.
- Write tests for ownership, blocked users, filters, invalid transitions, and concurrent favorites.

## Compatibility scope

Implemented: authentication, profiles, settings, master data, car CRUD/filtering, favorites,
seller cars/statistics, moderation, reviews, chats, contact inbox, vehicle history, blocking,
reports, notifications, saved searches, file uploads, Swagger, health checks, demo data,
Channels/Redis realtime, Celery/Beat delivery, a transactional outbox, dead letters,
ClamAV scanning, WebP thumbnails, Prometheus metrics, audit export, rich token sessions,
idempotent writes, cursor pagination, feature flags, and PostgreSQL full-text/trigram search.

The .NET-specific SignalR protocol is replaced by Channels WebSockets. Hangfire image
processing is replaced by Celery. Local-volume media storage is the main deliberate
practice-project simplification; see the parity matrix below.

## Realtime implementation: step by step

The original SignalR files remain untouched. Django uses a parallel native-WebSocket implementation.

1. **ASGI and Channels** — `config/asgi.py` routes HTTP to Django and `/ws/...` connections
   to Channels consumers.
2. **JWT authentication** — Angular first requests a single-use, 30-second WebSocket ticket
   from `POST /api/v1/Auth/websocket-ticket`, then connects with `?ticket=...`. The ticket is
   atomically consumed from Redis. Direct `?token=...` fallback is development-only.
3. **Redis groups** — each user joins `user_<id>` and each conversation joins `chat_<id>`.
   Redis allows API and worker processes on different containers to publish to the same group.
4. **Live notifications** — `/ws/notifications/` publishes newly committed notification rows.
5. **Live chat** — `/ws/chats/<chatId>/` checks that the user is the buyer or seller, then
   publishes persisted messages.
6. **Typing and presence** — ephemeral events go directly through Redis and are not stored.
7. **Read receipts** — the REST read endpoint and WebSocket `{"type":"read"}` command update
   PostgreSQL, then emit `messages.read`.
8. **Reconnect/catch-up** — clients reconnect with `afterId`; the consumer returns up to 100
   missed persisted messages or notifications before continuing live delivery.
9. **Transactional outbox** — every durable event is inserted into `RealtimeOutboxEvent` in
   the same transaction. An immediate post-commit attempt provides low latency.
10. **Celery retry** — Beat runs `marketplace.dispatch_realtime_outbox` every five seconds;
    the worker retries undelivered events up to ten times.

Angular alternatives are intentionally separate:

- `django-chat-realtime.service.ts`
- `django-notification-realtime.service.ts`
- `django-notification-center.service.ts`

The Django practice UI is wired to the new Django services. The original SignalR source files
remain unchanged for side-by-side interview comparison. `npm start` and `npm run start:django` use
`proxy.django.conf.json`; `proxy.dotnet.conf.json` is retained as the original API proxy reference.

WebSocket event examples:

```json
{"type":"typing","isTyping":true}
{"type":"read"}
{"type":"message.received","message":{"id":12,"chatId":3,"content":"Hello"}}
{"type":"messages.read","chatId":3,"readerId":7,"markedReadCount":2}
{"type":"notification.received","notification":{"id":9,"type":"ChatMessage"}}
```

The complete controller and production-behavior comparison is in [docs/PARITY.md](docs/PARITY.md).

## Scalable API features

### Cursor pagination

Large notification and chat-message histories support stable keyset pagination without
changing the existing page-number default:

```http
GET /api/v1/notifications?pagination=cursor&pageSize=50
GET /api/v1/chats/42/messages?pagination=cursor&pageSize=50
GET /api/v1/notifications?pagination=cursor&pageSize=50&cursor=<signed-next-cursor>
```

Use the opaque `nextCursor` returned in `data`; clients must not parse or construct it.
Signed cursors expire after 30 days and invalid/tampered values return `400`.

### Idempotent writes

Car creation, chat creation, chat messages, contact inquiries, and standalone car uploads
accept an optional `Idempotency-Key` header. Generate one UUID per logical operation and reuse
it only when retrying the same request:

```http
Idempotency-Key: 019c70eb-738d-7f7a-b583-97be5fe74ae7
```

The first completed response is replayed for identical retries. Reusing a key with a different
payload returns `409`; an operation still in progress also returns `409`. Records expire after
seven days through the daily cleanup job.

### Search, sessions, and feature flags

- PostgreSQL listing search combines weighted full-text ranking with trigram similarity over
  title, brand, and model. SQLite retains an `icontains` fallback for lightweight tests.
- The database has GIN full-text/trigram indexes; the `pg_trgm` extension is migration-managed.
- Authentication sessions retain browser, device, IP address, creation/expiry, and last
  activity. Revoking a session invalidates its access token immediately.
- `GET /api/v1/features` exposes enabled client flags. Admin-managed flags support deterministic
  percentage rollout by user (or anonymous visitor key) and are cached with save/delete
  invalidation.
- `cursor-pagination` and `postgres-full-text-search` are seeded enabled, preserving existing
  behavior while allowing controlled rollout later.

### Load testing

Install development dependencies, start the stack, and run the Locust UI:

```powershell
pip install -r requirements-dev.txt
locust -f loadtests/locustfile.py --host http://localhost:8000
```

Set `LOADTEST_EMAIL`, `LOADTEST_PASSWORD`, or `LOADTEST_ACCESS_TOKEN` to exercise authenticated
chat lists, cursor history, notification catch-up, and WebSocket reconnects.
Listing full-text filters work anonymously. A headless smoke example:

```powershell
locust -f loadtests/locustfile.py --host http://localhost:8000 `
  --headless -u 10 -r 2 -t 30s
```

### CI and container hardening

- Django CI runs Ruff, selected strict mypy checks, migration-drift detection, Django checks,
  PostgreSQL/Redis tests with coverage, OpenAPI validation, and `pip-audit`.
- Angular CI uses a clean lockfile install, blocks high-severity vulnerabilities in shipped
  dependencies, reports development-tool advisories, and performs a production build.
- API, Celery worker, and Beat containers run as the unprivileged UID/GID `10001`; no service
  needs root at runtime.

## Performance and maintenance safeguards

- Chat lists annotate the latest message and unread count in SQL, so database-query count does
  not grow with the number of conversations.
- Listing summaries prefetch only the images they serialize; feature and history rows are loaded
  only for detail responses.
- Seller and moderation statistics use conditional aggregates, including real pending/failed
  image-processing counts.
- PostgreSQL composite indexes cover listing dashboards, chat catch-up/unread reads, notification
  and contact inboxes, moderation history, reports, saved-search matching, and outbox dispatch.
- PostgreSQL connections are reused for 60 seconds and health-checked before reuse.
- Authentication, anonymous contact, and upload endpoints have additional scoped throttles.
- Celery uses late acknowledgements, worker-loss rejection, and a prefetch multiplier of one for
  safer long-running image jobs.
- A daily Beat task removes expired JWT session rows and successfully processed outbox events
  and idempotency records older than seven days; dead letters are retained for administrators.
- WhiteNoise serves hashed, gzip/Brotli-compressed static assets from the container.
- `django-cleanup` removes replaced/deleted profile images, car images, thumbnails, and vehicle
  documents after the surrounding database transaction commits.
