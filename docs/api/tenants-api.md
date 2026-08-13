# Tenants API

All routes mounted under `/api/v1` (see `backend/app/main.py`). Router:
`backend/app/modules/tenants/router.py`. Full interactive docs at `/docs` (FastAPI's built-in
Swagger UI) when the backend is running.

| Method | Path | Purpose | Success | Errors |
|---|---|---|---|---|
| POST | `/tenants` | Create a tenant | 201, `TenantRead` | 422 validation, 409 duplicate slug |
| GET | `/tenants` | List tenants (paginated) | 200, `list[TenantRead]` | — |
| GET | `/tenants/{tenant_id}` | Get one tenant | 200, `TenantRead` | 404 |
| POST | `/tenants/{tenant_id}/branches` | Create a branch | 201, `BranchRead` | 422, 409 duplicate slug within tenant |
| GET | `/tenants/{tenant_id}/branches` | List a tenant's branches (paginated) | 200, `list[BranchRead]` | — |
| GET | `/tenants/{tenant_id}/branches/{branch_id}` | Get one branch | 200, `BranchRead` | 404 |

## Request bodies

`TenantCreate`: `name_en`, `name_ar`, `phone`, `default_currency` (optional, default `SAR`).
`BranchCreate`: `name_en`, `name_ar`, `phone`, `timezone` (optional, default `Asia/Riyadh`).
See `backend/app/modules/tenants/schemas.py` for exact types/constraints.

## Pagination

`GET` list endpoints accept `limit` (1–100, default 20) and `offset` (default 0) query params —
see `backend/app/core/pagination.py`.

## Errors

Domain errors serialize as `{"code": "...", "message": "..."}` via
`backend/app/core/error_handlers.py`. Codes used today: `validation_error`, `duplicate_slug`,
`tenant_not_found`, `branch_not_found`, `tenant_mismatch`.

## Not yet built

Update/delete for tenants and branches.
