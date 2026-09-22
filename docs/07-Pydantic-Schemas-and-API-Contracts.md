---
title: Pydantic Schemas and API Contracts
created: 2026-08-11
project: NOVA
type: api
tags: [pydantic, api, schemas, fastapi]
related_code:
  - app/modules/catalog/schemas.py
  - app/modules/booking/schemas.py
  - app/modules/queue/schemas.py
  - app/modules/payment/schemas.py
  - app/modules/media/schemas.py
---

# Pydantic Schemas and API Contracts

> [!important] Purpose
> This document defines the Pydantic schemas used by FastAPI for request validation, response serialization, OpenAPI documentation, and AI tool contracts.
>
> Pydantic schemas are API boundary models. They are not the domain model and not the database model.

> [!warning] Read the schemas below as the original design
> The implemented contract differs in ways that matter for security and billing. Each section
> whose schemas changed ends with an "Implemented differences" note naming the ADR responsible.
> The `schemas.py` files are authoritative, and `/docs` is the live contract. Three rules hold
> throughout:
>
> - **Tenant-owned resources are nested under their tenant**, e.g.
>   `/api/v1/tenants/{tenant_id}/bookings`. `tenant_id` comes only from that path (ADR-0003).
> - **Every route requires `Authorization: Bearer <token>`** (ADR-0006). The exceptions are
>   `/api/v1/auth/register`, `login` and `refresh`, the signature-verified
>   `/api/v1/webhooks/moyasar`, and the public marketplace under `/api/v1/discovery/` (ADR-0010).
>   That marketplace includes a map view: `GET /api/v1/discovery/businesses` takes a
>   `bbox=west,south,east,north` viewport, and `GET /api/v1/discovery/map` returns the same search
>   as a GeoJSON FeatureCollection, unpaged and capped. An owner sets where a branch appears on it
>   with `PATCH /api/v1/tenants/{tenant_id}/catalog/locations/{location_id}/position` (ADR-0012).
> - **Caller identity is never read from a request body.** The customer is the authenticated
>   principal, and only staff may name someone else, with `on_behalf_of_customer_id` (ADR-0006).

---

## 1. Schema Placement

```text
app/modules/
  identity/schemas.py
  catalog/schemas.py
  booking/schemas.py
  queue/schemas.py
  payment/schemas.py
  media/schemas.py
  notification/schemas.py
  ai_agents/schemas.py


```

Naming conventions:

| Type                    | Suffix           | Example                 |
| ----------------------- | ---------------- | ----------------------- |
| Create Request          | `CreateRequest`  | `CreateBookingRequest`  |
| Update Request          | `UpdateRequest`  | `UpdateServiceRequest`  |
| Query / Filter          | `Filter`         | `AvailabilityFilter`    |
| API Response            | `Out`            | `BookingOut`            |
| Internal Command Result | `Result`         | `HoldSlotResult`        |
| Webhook Payload         | `WebhookPayload` | `MoyasarWebhookPayload` |

## 2. Base Schema Standards

All schemas should use Pydantic v2.

```python
from pydantic import BaseModel, ConfigDict, Field
from typing import Generic, TypeVar
from uuid import UUID

T = TypeVar("T")


class ApiSchema(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        str_strip_whitespace=True,
        populate_by_name=True,
    )


class Page(ApiSchema, Generic[T]):
    items: list[T]
    total: int | None = None
    next_cursor: str | None = None


class ErrorDetail(ApiSchema):
    code: str
    message: str
    field: str | None = None
    retryable: bool = False


class ErrorResponse(ApiSchema):
    error: ErrorDetail
```

> [!note] Implemented differences
> `ErrorDetail` also carries an optional `correlation_id`. It echoes the `X-Correlation-ID`
> response header so a user can quote a failed request (ADR-0006). `app/core/error_handlers.py`
> renders every failure in this envelope: domain errors, constraint violations, request
> validation and uncaught exceptions. The app declares it for `4XX` and `5XX` on every operation,
> so `/docs` shows this shape rather than FastAPI's `HTTPValidationError`.

## 3. Common Enums

```python
from enum import StrEnum


class BookingStatus(StrEnum):
    DRAFT = "draft"
    PENDING_PAYMENT = "pending_payment"
    CONFIRMED = "confirmed"
    CHECKED_IN = "checked_in"
    IN_SERVICE = "in_service"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"


class QueueEntryStatus(StrEnum):
    WAITING = "waiting"
    CALLED = "called"
    CHECKED_IN = "checked_in"
    MISSED = "missed"
    IN_SERVICE = "in_service"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class TicketStatus(StrEnum):
    ACTIVE = "active"
    REDEEMED = "redeemed"
    EXPIRED = "expired"
    REVOKED = "revoked"


class PaymentStatus(StrEnum):
    PENDING = "pending"
    AUTHORIZED = "authorized"
    CAPTURED = "captured"
    FAILED = "failed"
    REFUNDED = "refunded"
    PARTIALLY_REFUNDED = "partially_refunded"


class MediaAssetKind(StrEnum):
    LOGO = "logo"
    COVER = "cover"
    SERVICE_IMAGE = "service_image"
    PROVIDER_IMAGE = "provider_image"
    LOCATION_IMAGE = "location_image"
    PORTFOLIO = "portfolio"
```

## 4. Catalog Schemas

```python
from datetime import datetime
from decimal import Decimal


class BusinessOut(ApiSchema):
    id: UUID
    slug: str
    name: str
    description: str | None
    logo_asset_id: UUID | None
    cover_asset_id: UUID | None
    is_active: bool


class LocationOut(ApiSchema):
    id: UUID
    business_id: UUID
    name: str
    address_line_1: str
    address_line_2: str | None
    city: str
    country: str
    latitude: float | None
    longitude: float | None
    timezone: str
    is_active: bool


class ServiceOut(ApiSchema):
    id: UUID
    location_id: UUID
    name: str
    description: str | None
    duration_minutes: int
    price: Decimal
    currency: str
    category: str | None
    is_active: bool


class ProviderOut(ApiSchema):
    id: UUID
    location_id: UUID
    name: str
    title: str | None
    image_asset_id: UUID | None
    is_active: bool
```

> [!note] Implemented differences
> Names, descriptions and titles are bilingual column pairs (`name_en`/`name_ar`,
> `description_en`/`description_ar`, `title_en`/`title_ar`), per ADR-0004. Every `Out` also
> carries `tenant_id`, `created_at` and `updated_at`. `BusinessOut` adds `is_listed`, the
> marketplace switch (ADR-0010). `LocationOut` has `slug`, `phone` and an optional `city`, and no
> address lines or `country` yet. Reads are open to anyone with tenant access, customers included,
> and every write is staff-only. See `app/modules/catalog/schemas.py`.

## 5. Availability Schemas

```python
class AvailabilityFilter(ApiSchema):
    location_id: UUID
    service_id: UUID
    provider_id: UUID | None = None
    date: datetime


class AvailabilitySlotOut(ApiSchema):
    slot_id: str
    provider_id: UUID
    location_id: UUID
    service_id: UUID
    starts_at: datetime
    ends_at: datetime
    remaining_capacity: int
```

Rules:

- `slot_id` should be a signed or deterministic identifier.
- Availability must be generated by the domain/application layer.
- AI agents may query availability but must not invent slots.

> [!note] Implemented differences
> `GET /api/v1/tenants/{tenant_id}/bookings/availability` takes a required `provider_id`, with
> `service_id`, `date_from` and `date_to`, instead of a single `date`. The customer's usual
> question, "any stylist for this service", is answered by the public
> `GET /api/v1/discovery/businesses/{slug}/services/{service_id}/availability` (ADR-0010).
> `slot_id` is an HMAC over (tenant, provider, service, start), which is how an invented slot is
> caught (ADR-0007). A slot can be held while checkout completes with
> `POST .../bookings/holds`.

## 6. Booking Schemas

```python

class CustomerContact(ApiSchema):
    full_name: str
    phone: str
    email: str | None = None
    preferred_language: str = "ar"


class CreateBookingRequest(ApiSchema):
    business_id: UUID
    location_id: UUID
    service_id: UUID
    provider_id: UUID | None = None
    starts_at: datetime
    customer: CustomerContact
    notes: str | None = Field(default=None, max_length=1000)
    source: str = "pwa"


class BookingOut(ApiSchema):
    id: UUID
    tenant_id: UUID
    business_id: UUID
    location_id: UUID
    service_id: UUID
    provider_id: UUID
    customer_id: UUID
    starts_at: datetime
    ends_at: datetime
    status: BookingStatus
    source: str


class CancelBookingRequest(ApiSchema):
    reason: str | None = Field(default=None, max_length=500)


class RescheduleBookingRequest(ApiSchema):
    new_starts_at: datetime
    provider_id: UUID | None = None\



```

Expected API behavior:

```json
POST /api/v1/bookings
GET /api/v1/bookings/{booking_id}
POST /api/v1/bookings/{booking_id}/cancel
POST /api/v1/bookings/{booking_id}/reschedule
POST /api/v1/bookings/{booking_id}/check-in
```

> [!note] Implemented differences
>
> - **Paths** are `/api/v1/tenants/{tenant_id}/bookings/...`. Beyond the five above there are
>   `holds`, and staff-only `confirm`, `start`, `complete`, `no-show` and
>   `calendar/{provider_id}`. `check-in` is staff-only too. A customer may `cancel` or
>   `reschedule` only their own booking.
> - **`CreateBookingRequest` has no `customer` or `customer_id`.** The customer is the
>   authenticated principal, and staff booking for someone send `on_behalf_of_customer_id`
>   (ADR-0006). There is no `business_id` either: it is read from the location. `provider_id` is
>   required, and the request adds `hold_token`, `slot_id` and `referral_token`.
> - **`source` is optional and uses the attribution vocabulary**: `direct_link`, `whatsapp`,
>   `walk_in`, `reception` or `ai_agent`, and `pwa` no longer exists. A client can never declare
>   `marketplace`; it is derived server-side from a verified `referral_token` (ADR-0008,
>   ADR-0010).
> - **`BookingOut`** adds `price`, `currency`, `cancellation_reason` and `notes`, and its `source`
>   is a `BookingSource`.

## 7. Queue and Ticket Schemas

```python
class JoinQueueRequest(ApiSchema):
    location_id: UUID
    service_id: UUID
    provider_id: UUID | None = None
    party_size: int = Field(default=1, ge=1, le=20)
    customer: CustomerContact


class QueueEntryOut(ApiSchema):
    id: UUID
    queue_id: UUID
    location_id: UUID
    service_id: UUID
    provider_id: UUID | None
    status: QueueEntryStatus
    position: int
    estimated_wait_minutes: int | None


class TicketOut(ApiSchema):
    id: UUID
    ticket_code: str
    qr_payload: str
    status: TicketStatus
    expires_at: datetime
    ticket_page_url: str


class CheckInTicketRequest(ApiSchema):
    ticket_id: UUID
    qr_token: str
```

QR rules:

- `qr_payload` must be a signed token.
- `qr_payload` must not contain customer name, phone, or email.
- `ticket_page_url` should point to the PWA ticket page.
- Ticket validation must check tenant, status, expiry, and signature.

> [!note] Implemented differences
> A customer joins with `POST /api/v1/tenants/{tenant_id}/queues/{queue_id}/entries`, so
> `JoinQueueRequest` has no `location_id`. It has no `customer` either: the customer is the
> principal, and staff use `on_behalf_of_customer_id` (ADR-0006). It adds `booking_id`, so an
> arriving appointment joins the same timeline as the walk-ins (ADR-0007). `QueueEntryOut` adds
> `customer_id`, `source`, `party_size`, `booking_id`, `joined_at`, `called_at` and
> `place_in_line`. `position` is a join counter that never renumbers, and `place_in_line` is
> where the customer actually stands. `CheckInTicketRequest` is one `qr_payload`
> (`<ticket_id>.<token>.<signature>`), because a scanner reads one string (ADR-0007).
> `TicketOut.qr_payload` is returned once, at issue, since only a hash of the token is stored.

## 8. Payment Schemas

```python
class CreatePaymentIntentRequest(ApiSchema):
    booking_id: UUID
    amount: Decimal
    currency: str = "SAR"
    return_url: str
    metadata: dict[str, str] | None = None


class PaymentOut(ApiSchema):
    id: UUID
    booking_id: UUID | None
    amount: Decimal
    currency: str
    status: PaymentStatus
    gateway: str
    gateway_payment_id: str | None
    created_at: datetime


class MoyasarWebhookPayload(ApiSchema):
    id: str
    event: str
    status: str
    amount: Decimal | None = None
    currency: str | None = None
    metadata: dict[str, str] | None = None
```

Payment rules:

- Webhook payload must be treated as untrusted until signature verification.
- Payment capture must be idempotent.
- Booking confirmation may depend on payment policy.
- Refunds must be stored as separate payment events or records.

> [!note] Implemented differences
> `CreatePaymentIntentRequest.amount` and `currency` are optional staff overrides. Left unset,
> the amount comes from the booking's price and the deposit policy, so a client cannot choose
> what it owes. `PaymentOut` adds `webhook_verified`, `refunded_amount`, `failure_code` and
> `captured_at`. `MoyasarWebhookPayload` follows Moyasar's real envelope (`id`, `type`,
> `secret_token`, `data`), and the signature is verified against the raw body before anything is
> read (ADR-0007). A refund is staff-only, idempotency-keyed and stored as its own record:
> `POST /api/v1/tenants/{tenant_id}/payments/{payment_id}/refund`.

## 9. Nextcloud Media Schemas

```python
class RequestMediaUploadRequest(ApiSchema):
    business_id: UUID
    location_id: UUID | None = None
    kind: MediaAssetKind
    file_name: str
    content_type: str
    size_bytes: int = Field(gt=0, le=100 * 1024 * 1024)


class MediaUploadResponse(ApiSchema):
    asset_id: UUID
    upload_url: str
    webdav_path: str
    expires_at: datetime


class MediaAssetOut(ApiSchema):
    id: UUID
    business_id: UUID
    location_id: UUID | None
    kind: MediaAssetKind
    file_name: str
    content_type: str
    size_bytes: int
    public_url: str | None
    thumbnail_url: str | None
    created_at: datetime
```

Nextcloud path convention:

```json
	/nova-media/{tenant_id}/{business_id}/{kind}/{asset_id}/{file_name}
```

Rules:

- PostgreSQL stores metadata only.
- Binary files live in Nextcloud.
- Public URLs should be generated through a controlled media proxy or signed URL.
- Business owners must not be able to access another tenant's media folder.

> [!note] Implemented differences
> Upload takes three steps (ADR-0007):
>
> 1. `POST .../media/uploads` returns the URL and a signed `upload_token`.
> 2. The browser PUTs the bytes to Nextcloud.
> 3. `POST .../media/uploads/{asset_id}/complete` verifies them against storage before the asset
>    is ready.
>
> `MediaAssetOut` has no `public_url` or `thumbnail_url`. Following the signed-URL rule above,
> `GET .../media/{asset_id}/link` generates a share link on demand and nothing is stored. It adds
> `is_ready` and `is_public`.

## 10. AI Chat Schemas

```python
class AiChatRequest(ApiSchema):
    session_id: str
    tenant_id: UUID | None = None
    customer_id: UUID | None = None
    business_id: UUID | None = None
    channel: str = "pwa"
    locale: str = "ar"
    message: str = Field(max_length=4000)


class AiChatResponse(ApiSchema):
    session_id: str
    reply: str
    suggested_actions: list[str] = []
    requires_human_handoff: bool = False
    related_booking_id: UUID | None = None
    related_ticket_url: str | None = None
```

> [!note] Implemented differences
> `AiChatRequest` has no `tenant_id`. The tenant is the authenticated path parameter, so a caller
> cannot name the tenant an agent reads (docs/10 section 11). Its `customer_id` is staff-only,
> the same rule as booking. The endpoint is
> `POST /api/v1/tenants/{tenant_id}/ai/chat?agent=<name>`, and `GET .../ai/agents` lists what the
> deployment can run. Owner-only agents (`billing_agent`, `insights_agent`) refuse non-staff
> callers with 403 (docs/10 section 4). `AiChatResponse` adds `degraded` and `confidence`, so a
> fallback reply can be told apart from a confident one.
