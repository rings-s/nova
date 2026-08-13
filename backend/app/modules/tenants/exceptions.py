from app.core.exceptions import ConflictError, NotFoundError


class TenantNotFoundError(NotFoundError):
    code = "tenant_not_found"

    def __init__(self, tenant_id: object) -> None:
        super().__init__(f"Tenant '{tenant_id}' was not found.")


class BranchNotFoundError(NotFoundError):
    code = "branch_not_found"

    def __init__(self, branch_id: object) -> None:
        super().__init__(f"Branch '{branch_id}' was not found.")


class DuplicateSlugError(ConflictError):
    code = "duplicate_slug"

    def __init__(self, slug: str) -> None:
        super().__init__(f"Slug '{slug}' is already in use.")
