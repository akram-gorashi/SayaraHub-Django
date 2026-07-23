# SayaraHub Django REST practice backend

This is an interview-focused reimplementation of the existing ASP.NET SayaraHub API using
Django, Django REST Framework, SimpleJWT, and PostgreSQL. It preserves the Angular app's
`/api/v1` routes, camelCase request/response fields, and `{ success, message, data }` envelope.

## Run with PostgreSQL

```powershell
cd SayaraHub-Django
Copy-Item .env.example .env
docker compose up --build
```

- API: `http://localhost:8000/api/v1`
- Swagger: `http://localhost:8000/api/docs/`
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
3. Database constraints enforce one favorite per user/car, one review per reviewer/seller, and one chat per buyer/car.
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
- Add refresh-token blacklisting and session/device management.
- Add Channels + Redis for live chat and notifications.
- Move notifications to a Celery outbox task.
- Add S3-compatible image storage and thumbnail processing.
- Write tests for ownership, blocked users, filters, invalid transitions, and concurrent favorites.

## Compatibility scope

Implemented: authentication, profiles, settings, master data, car CRUD/filtering, favorites,
seller cars/statistics, moderation, reviews, chats, contact inbox, vehicle history, blocking,
reports, notifications, saved searches, file uploads, Swagger, health checks, and demo data.

The .NET-specific SignalR protocol is replaced by Channels WebSockets. Hangfire image
processing, Redis device-session metadata, Prometheus/Grafana, dead-letter administration,
and audit CSV export remain optional practice extensions.

## Realtime implementation: step by step

The original SignalR files remain untouched. Django uses a parallel native-WebSocket implementation.

1. **ASGI and Channels** — `config/asgi.py` routes HTTP to Django and `/ws/...` connections
   to Channels consumers.
2. **JWT authentication** — `marketplace/realtime/middleware.py` validates the access token
   supplied as `?token=...`. Invalid sockets close with code `4401` or `4403`.
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
- Existing `chat-realtime.service.ts` and `notification-center.service.ts` continue using SignalR.

To experiment with Django realtime, inject the `Django...` service in a practice component/store.
This explicit opt-in prevents the Django exercise from changing the production SignalR behavior.

WebSocket event examples:

```json
{"type":"typing","isTyping":true}
{"type":"read"}
{"type":"message.received","message":{"id":12,"chatId":3,"content":"Hello"}}
{"type":"messages.read","chatId":3,"readerId":7,"markedReadCount":2}
{"type":"notification.received","notification":{"id":9,"type":"ChatMessage"}}
```
