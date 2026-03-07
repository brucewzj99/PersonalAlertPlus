# Database Migration Guidelines

Follow these rules for all SQL migration work in this repository:

1. Never edit or replace an existing migration file after it has been committed.
2. Every schema change must be additive: create a new migration file with the next numeric prefix.
3. Use idempotent SQL where possible (`IF NOT EXISTS`, `DROP ... IF EXISTS`) so migrations are safe across environments.
4. Keep table names schema-qualified (`public.table_name`) for consistency.
5. Document the intent at the top of each new migration and keep each migration focused on one change set.

Naming convention:

- `NNN-short-description.sql` (e.g. `010-schema-hygiene-and-few-shot-fix.sql`)

Execution order:

- Run migrations strictly by numeric prefix.
