"""Single import point for every module's models and router.

Alembic's env.py imports this module so autogenerate sees all ORM models.
main.py imports `routers` to register every module's FastAPI router.
New module checklist: add its `models` import below and its router to `routers`.
"""

from app.modules.tenants import models as tenants_models  # noqa: F401
from app.modules.tenants.router import router as tenants_router

routers = [tenants_router]
