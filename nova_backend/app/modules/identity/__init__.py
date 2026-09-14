"""Bounded context: IDENTITY — who everyone is.

Owns the tenant: the isolation root that every other module hangs off, plus the
two kinds of person in the system.

Aggregates      Tenant, User, Membership, Customer
Tables          tenants, users, memberships, customers
Depends on      (nothing — this is the root context)
Status          implemented

User vs Customer, because the distinction causes most of the confusion here:

    User      an account that can sign in. Staff, owners, and self-service
              customers have one. Carries credentials.
    Customer  a person a salon books. Tenant-scoped, carries consent and a
              phone number, and may have no account at all (a walk-in
              reception typed in). Linked to a User by `user_id` when the
              person books themselves.

The same human at two salons is one User and two Customers — consent given to
one business must never leak to another.

Public surface — what other modules may import:
    from app.modules.identity.service import TenantService, CustomerService, MembershipService
    from app.modules.identity.domain import MembershipRole, may_manage_role
    from app.modules.identity.exceptions import TenantNotFoundError, CustomerNotFoundError

`MembershipRole` lives in domain.py rather than models.py so schemas, routers
and the pure authority rule can all reach it without importing SQLAlchemy.

Internal — do not import from other modules:
    models.py, repository.py, dependencies.py, router.py

Why Location is not here: identity answers "who", catalog answers
"where and what is sold". A branch is a catalog concern.
"""
