---
title: Backend FastAPI DDD Structure
created: 2026-08-11
project: NOVA
type: backend
tags: [fastapi, ddd, python, pydantic]
---

# Backend: FastAPI & Domain-Driven Design

> [!important] Core Philosophy
> FastAPI is merely the delivery mechanism (HTTP/WebSockets). The **Domain** is the heart of NOVA. Infrastructure and AI frameworks must never leak into the Domain layer.

## Directory Structure

> [!warning] Layers are roles, not folders
> The four layers below are **not** four top-level directories. They are roles that repeat
> inside every module. Slicing by layer at the top level was considered and rejected — it makes
> every feature touch four directories. See `docs/decisions/0002-vertical-slice-ddd-cqrs-lite.md`.

```text
nova_backend/
├── app/
│   ├── main.py             # FastAPI app factory, middleware, CORS
│   │
│   ├── core/               # 🔧 Shared kernel — no business rules
│   │   ├── config.py       #    Settings from environment
│   │   ├── deps.py         #    get_db_session, get_tenant_context
│   │   ├── exceptions.py   #    DomainError hierarchy (no FastAPI import)
│   │   ├── error_handlers.py  # DomainError → HTTP response
│   │   ├── schemas.py      #    ApiSchema, Page, ErrorResponse
│   │   ├── values.py       #    💎 Money, TimeRange (shared value objects)
│   │   ├── validators.py   #    💎 phone, slug, bilingual rules
│   │   └── events.py       #    publish_event + DomainEvent base
│   │
│   ├── db/                 # 🔌 Persistence kernel
│   │   ├── base.py         #    DeclarativeBase + constraint naming
│   │   ├── mixins.py       #    UUIDPK, Timestamp, TenantOwned, SoftDelete
│   │   ├── session.py      #    Async engine and sessionmaker
│   │   └── repository.py   #    BaseRepository, TenantScopedRepository
│   │
│   ├── modules/            # 📦 One folder per bounded context
│   │   ├── registry.py     #    The single wiring point
│   │   ├── identity/       #    Tenant
│   │   ├── catalog/        #    Business, Location, Service, Provider
│   │   ├── booking/        #    Booking  ← reference implementation
│   │   ├── queue/
│   │   ├── payment/
│   │   ├── billing/
│   │   ├── media/
│   │   ├── notification/
│   │   └── ai_agents/
│   │
│   ├── integrations/       # 🔌 Outbound adapters
│   │   ├── payments/       #    Moyasar
│   │   ├── storage/        #    Nextcloud WebDAV
│   │   └── whatsapp/       #    WhatsApp BSP
│   └── worker/             # 🔄 Background tasks (ARQ)
│
├── alembic/                # 🗄️ Migrations
└── tests/                  # mirrors app/modules/
```

The live map with the dependency-rule table is `nova_backend/README.md`.

> [!note] Implemented differences
> The tree above predates two changes. `discovery/` is the public, cross-tenant marketplace
> (ADR-0010), and `identity/` owns `User`, `Membership` and `Customer` as well as `Tenant`
> (ADR-0007). `core/` also holds `security.py` (bearer auth and `require_staff`),
> `throttling.py`, `idempotency.py`, and the correlation-id `context.py` and `middleware.py`
> (ADR-0006).




## Layer Rules (Strict Enforcement)

1. **Domain Layer:**
    - Can ONLY import standard Python libraries and `pydantic` (for data validation).
    - CANNOT import FastAPI, SQLAlchemy, or HTTP clients.
    - Raises Domain Exceptions (e.g., `SlotUnavailableError`), not HTTP 404s.
2. **Application Layer:**
    - Receives commands from the API layer.
    - Fetches Aggregates via Repository Interfaces (defined in Domain, implemented in Infrastructure).
    - Calls Domain methods, saves state, and publishes Domain Events.
3. **Infrastructure Layer:**
    - Implements the interfaces defined by the Domain/Application layers.
    - Handles the messy reality of Nextcloud WebDAV, Cloudflare headers, and Ollama API calls.





## 2. Anatomy of a Vertical Slice (e.g., `modules/booking/`)

- Inside a specific feature module, we still respect DDD boundaries, but they are contained within the feature folder.

```

modules/booking/
├── router.py           # 🌐 API Layer (FastAPI endpoints, dependency injection)
├── schemas.py          # 📦 Pydantic DTOs (Request/Response validation)
├── models.py           # 🗄️ Infrastructure (SQLAlchemy ORM models)
├── repository.py       # 🔌 Infrastructure (DB queries, implements interfaces)
├── service.py          # ⚙️ Application Layer (Use case orchestration/Handlers)
├── domain.py           # 💎 Domain Layer (Pure Python, Entities, Value Objects, Rules)
└── events.py           # 📡 Domain Events (BookingConfirmed, SlotReleased)

```




> [!note] Implemented differences
> Every module also has `__init__.py` (the context summary and its public surface),
> `exceptions.py` and `dependencies.py`. `tests/test_architecture.py` enforces the rule below.

### The Dependency Rule (Strict)

Even inside a vertical slice, dependencies point **inward**: `router.py` ➡️ `service.py` ➡️ `domain.py` ⬅️ `repository.py`

- **Domain** knows nothing about FastAPI, SQLAlchemy, or PydanticAI.
- **Service** coordinates the Use Case.
- **Router** handles HTTP concerns.



## 3. Code Example: A Pragmatic Slice (Cancel Booking)
	
- Here is how a single feature (Canceling a Booking) flows through the vertical slice.

	### A. Domain Layer [domain.py]
	
	- _Pure business rules. No frameworks._
	
	``` python
	from pydantic import BaseModel
	from datetime import datetime
	
	class CancellationPolicy(BaseModel):
	    free_cancellation_hours: int = 24
	
	class Booking:
	    def __init__(self, id: str, start_time: datetime, status: str):
	        self.id = id
	        self.start_time = start_time
	        self.status = status
	
	    def cancel(self, policy: CancellationPolicy, now: datetime):
	        if self.status != "CONFIRMED":
	            raise ValueError("Only confirmed bookings can be cancelled.")
	        
	        hours_until_start = (self.start_time - now).total_seconds() / 3600
	        if hours_until_start < policy.free_cancellation_hours:
	            raise ValueError("Too late for free cancellation.")
	            
	        self.status = "CANCELLED"
	        
	        
	```
	


	### B. Application / Service Layer (`service.py`)
	
	- _Orchestrates the use case. Fetches data, calls domain, saves state._
	
	
	```python
	from .domain import Booking, CancellationPolicy
	from .repository import BookingRepository
	from core.events import publish_event
	from .events import BookingCancelled
	
	class CancelBookingService:
	    def __init__(self, repo: BookingRepository):
	        self.repo = repo
	
	    async def execute(self, booking_id: str, user_id: str):
	        booking = await self.repo.get_by_id(booking_id)
	        policy = CancellationPolicy(free_cancellation_hours=24)
	        
	        # Call pure domain logic
	        booking.cancel(policy, now=datetime.utcnow())
	        
	        # Save state
	        await self.repo.save(booking)
	        
	        # Emit event for WhatsApp/Notifications
	        await publish_event(BookingCancelled(booking_id=booking.id))
	```
	
	
	
	
	
	### C. API Layer (`router.py`)
	
	
	- _Handles HTTP, Auth, and Pydantic Schemas._
	
	
	``` python
	from fastapi import APIRouter, Depends, HTTPException
	from .schemas import CancelBookingResponse
	from .service import CancelBookingService
	from core.database import get_db
	
	router = APIRouter(tags=["Bookings"])
	
	@router.post("/bookings/{booking_id}/cancel", response_model=CancelBookingResponse)
	async def cancel_booking(
	    booking_id: str, 
	    db: AsyncSession = Depends(get_db)
	):
	    repo = BookingRepository(db)
	    service = CancelBookingService(repo)
	    
	    try:
	        await service.execute(booking_id, user_id="current_user")
	        return {"success": True, "message": "Booking cancelled."}
	    except ValueError as e:
	        raise HTTPException(status_code=400, detail=str(e))
	```
	
	
	
	
	
	
	> [!warning] This example is illustrative, not the implemented pattern
> The real cancel flow differs in ways that are rules, not style:
>
> - **Domain errors are `DomainError` subclasses** carrying `status_code` and `code`, never
>   `ValueError`. Routers neither catch them nor raise `HTTPException`: `core/error_handlers.py`
>   renders every error in the `{"error": {...}}` envelope (ADR-0006).
> - **`publish_event(session, event)`** writes the event to the outbox inside the caller's
>   transaction, and the worker delivers it (docs/08 section 16). Services `flush()`; the router
>   commits.
> - **The route is `POST /api/v1/tenants/{tenant_id}/bookings/{booking_id}/cancel`.** It checks
>   the caller may see that booking, grants the late-cancellation waiver only to a staff
>   principal, and returns `BookingOut`.
> - **Times are timezone-aware**: `datetime.now(UTC)`, never `utcnow()` (docs/06 section 8).
>
> The current version is `cancel_booking` in `app/modules/booking/router.py`.

## 4. AI & Nextcloud Integration in Slices
	
	### PydanticAI Integration (`modules/ai_agents/`)
	
	The AI module acts as a **Consumer** of the domain slices. It does not contain business logic itself.
	
	- `booking_agent.py` defines the PydanticAI agent running on the local RTX 5090 (Ollama).
	- `tools.py` imports the `CancelBookingService` or `BookingRepository` and wraps them as PydanticAI `@tool` functions.
	- _Rule:_ The AI agent is never allowed to instantiate a SQLAlchemy session directly. It must call the Application Service.
	
	### Nextcloud Media Integration (`modules/catalog/`)
	
	When a business uploads a portfolio image:
	
	1. `router.py` generates a temporary WebDAV signed URL using `core/nextcloud.py`.
	2. The SvelteKit frontend uploads the file directly to Nextcloud (bypassing the FastAPI server to save RAM/Bandwidth).
	3. Nextcloud triggers a webhook to `modules/catalog/router.py`.
	4. The `CatalogService` updates the `Business` aggregate in Postgres with the new Nextcloud file path.
	
	
	


> [!note] Implemented differences
> Both integrations are laid out differently:
>
> - **Agents** live in `ai_agents/service.py` (the tools, the allowlist and `AgentDeps`) and
>   `runtime.py` (the guarded PydanticAI import). They are served at
>   `/api/v1/tenants/{tenant_id}/ai/*` (docs/10).
> - **Media** is its own `media` module, not part of `catalog`, and there is no Nextcloud webhook.
>   The client confirms an upload with `POST .../media/uploads/{asset_id}/complete`, which checks
>   the bytes with Nextcloud through `app/integrations/storage/nextcloud.py` before marking the
>   asset ready (ADR-0007).

## 5. Why this structure wins for NOVA

1. **Speed:** Developers open _one_ folder to fix a bug in the Queue system.
2. **Safety:** Domain rules for Payments cannot accidentally be bypassed by the AI Agent, because the AI Agent must use the Payment Slice's public service interface.
3. **Scalability:** If the `queue` module eventually needs to be extracted into a separate Go/Rust microservice due to high WebSocket load, the entire `modules/queue/` folder can be lifted and shifted with minimal refactoring.