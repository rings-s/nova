"""The single place every module is wired into the app.

Two consumers:
  - `alembic/env.py` imports this so autogenerate sees every ORM model.
  - `app/main.py` imports `routers` to mount every module's endpoints.

Adding a module means adding two lines here and nothing else — that is the
point of the vertical-slice layout.

Import order matters for SQLAlchemy relationship resolution: a module must be
imported after the modules it holds ForeignKeys into (catalog -> identity,
discovery -> catalog).
"""

# Cross-cutting tables that belong to no single module. Imported for their
# side effect of registering with Base.metadata so Alembic sees them.
from app.core import idempotency as _idempotency  # noqa: F401
from app.db import outbox as _outbox  # noqa: F401
from app.modules.ai_agents.router import router as ai_router

# analytics owns no tables, so only its router is imported (ADR-0011).
from app.modules.analytics.router import router as analytics_router
from app.modules.billing import models as billing_models  # noqa: F401
from app.modules.billing.router import router as billing_router
from app.modules.booking import models as booking_models  # noqa: F401
from app.modules.booking.router import router as booking_router
from app.modules.booking.router import schedule_router
from app.modules.catalog import models as catalog_models  # noqa: F401
from app.modules.catalog.router import router as catalog_router
from app.modules.discovery import models as discovery_models  # noqa: F401
from app.modules.discovery.router import router as discovery_router
from app.modules.identity import models as identity_models  # noqa: F401
from app.modules.identity.auth_router import router as auth_router
from app.modules.identity.router import customers_router, memberships_router
from app.modules.identity.router import router as identity_router
from app.modules.notification import models as notification_models  # noqa: F401
from app.modules.notification.router import router as notification_router
from app.modules.payment import models as payment_models  # noqa: F401
from app.modules.payment.router import router as payment_router
from app.modules.payment.router import webhook_router
from app.modules.queue import models as queue_models  # noqa: F401
from app.modules.queue.router import router as queue_router
from app.modules.queue.router import ticket_router

routers = [
    auth_router,
    identity_router,
    customers_router,
    memberships_router,
    catalog_router,
    discovery_router,
    booking_router,
    schedule_router,
    queue_router,
    ticket_router,
    payment_router,
    webhook_router,
    notification_router,
    billing_router,
    analytics_router,
    ai_router,
]
