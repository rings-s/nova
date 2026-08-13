# Data Model

Current schema (migration `82b108bd4e78_create_tenants_and_branches.py`):

```
tenants
├── id            uuid, pk
├── name_en       varchar(200), not null
├── name_ar       varchar(200), not null
├── slug          varchar(200), not null, unique
├── phone         varchar(20), not null
├── default_currency  varchar(3), not null, default 'SAR'
├── created_at    timestamptz, not null
└── updated_at    timestamptz, not null

branches
├── id            uuid, pk
├── tenant_id     uuid, fk → tenants.id, on delete cascade, indexed
├── name_en       varchar(200), not null
├── name_ar       varchar(200), not null
├── slug          varchar(200), not null   (unique together with tenant_id)
├── phone         varchar(20), not null
├── timezone      varchar(50), not null, default 'Asia/Riyadh'
├── created_at    timestamptz, not null
└── updated_at    timestamptz, not null

unique (tenant_id, slug)
```

See [[tenants-and-branches|../domain/tenants-and-branches]] for the business rules behind these
fields, and [[0004-bilingual-field-strategy|../decisions/0004-bilingual-field-strategy]] for why
`name_en`/`name_ar` are columns rather than a translations table.

Naming convention for constraints/indexes is defined once in `backend/app/db/base.py`
(`NAMING_CONVENTION`) so Alembic autogenerate produces stable, predictable names
(`pk_tenants`, `uq_branches_tenant_id`, `fk_branches_tenant_id_tenants`, ...).
