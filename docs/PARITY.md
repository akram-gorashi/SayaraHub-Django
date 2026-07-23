# SayaraHub .NET → Django parity

This matrix compares the ASP.NET controllers and production behaviors with the Django practice API.

| Capability | Django status | Implementation |
|---|---|---|
| Register, login, refresh, revoke, revoke all | Equivalent | SimpleJWT, rotated refresh cookies and blacklist |
| Session list/revoke/revoke others | Equivalent API | SimpleJWT outstanding-token records; device labels are generic |
| User profile, password and image | Equivalent | DRF ownership checks and validated image uploads |
| Privacy/settings/account closure | Equivalent | Private profile, hidden phone, messaging controls and token revocation |
| Master data | Equivalent | Protected lookup tables and paginated endpoints |
| Car listing CRUD/filtering | Equivalent | PostgreSQL filters, multipart images and moderation reset |
| Standalone upload | Equivalent API | Validated local media storage |
| Related/seller/mine/favorites | Equivalent | Ownership and unique database constraints |
| Unique listing views | Equivalent | Visitor cookie/user key plus unique `(car, visitor)` constraint |
| Seller detail/statistics/images/retry/draft | Equivalent | Celery image state and persistent JSON draft |
| Image processing | Equivalent workflow | ClamAV, decoder validation, metadata-stripping WebP conversion and thumbnails via Celery |
| Reviews | Equivalent | One review per reviewer/seller and admin moderation |
| Vehicle history/documents | Equivalent | Public reads, owner writes and document uploads |
| Chats/messages/read receipts | Equivalent | PostgreSQL REST source of truth plus Channels delivery |
| Typing/presence | Equivalent behavior | Ephemeral Redis events, multi-connection count and stale cleanup |
| Contact inquiries | Equivalent | Public submission, seller inbox and live notification |
| Blocking/reporting | Equivalent | Bidirectional messaging enforcement and admin resolution |
| Notifications/preferences | Equivalent | Persistent rows, per-type opt-out, WebSocket delivery and optional SMTP |
| Saved searches | Equivalent | CRUD plus new-listing, price-drop and sold alerts |
| Listing/review/report moderation | Equivalent | State transitions, history, audit records and notifications |
| Audit query/export | Equivalent API | Filtered paginated JSON and CSV |
| Durable notification delivery | Equivalent pattern | Transactional realtime outbox, locked dispatch, Celery retry and dead letters |
| Dead-letter list/retry | Equivalent API | Admin-only endpoints |
| Realtime protocol | Functional equivalent | Django Channels/native WebSocket replaces SignalR protocol |
| Redis | Equivalent role | Channel layer, tickets, throttling and Celery broker |
| Hangfire jobs | Functional equivalent | Celery worker and Beat |
| Health/readiness | Equivalent | Database and Redis readiness checks |
| Metrics/correlation/security headers | Equivalent baseline | Prometheus endpoint and request middleware |
| Swagger | Equivalent | drf-spectacular with feature tags and concrete request bodies |

## Intentional implementation differences

- Django uses native WebSockets rather than implementing Microsoft’s SignalR wire protocol.
- Session/device metadata is derived from SimpleJWT token records; detailed browser/IP activity
  can be added by replacing it with a dedicated session model.
- Media storage is local-volume based. The storage interface can be switched to S3 without
  changing API contracts.
- The .NET observability deployment contains prebuilt Grafana dashboards; Django exposes
  Prometheus metrics but does not duplicate those dashboard JSON files.

These are infrastructure substitutions or documented extensions, not missing Angular-facing
business endpoints.
