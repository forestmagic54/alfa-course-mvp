# Project rules

## Architecture and stack

- Requirements: `docs/.todo/TASKS.md`; HTTP contract: `docs/openapi.yaml` (`/api/v1`); target database schema: `docs/database_schema.dbml`.
- Target stack: Python 3.12, Poetry, FastAPI, async SQLAlchemy + PostgreSQL, Alembic, JWT.
- Package `src`: `api/<resource>/{routes,schemas}.py` for HTTP and validation; `services` for business operations; `db/{models,crud,session,alembic}` for ORM, SQL, sessions and migrations; `config` for settings and versioned reference data.
- `src/__main__.py` provides `create_app` and `lifespan`; `context.py` assembles services/clients; `services/recommendation_stubs.py` provides replaceable local ML/LLM stubs.
- Use one database session per request and one transaction per business operation. Map HTTP errors at the API boundary. 
- Use type hints; add docstrings only where they clarify non-obvious behavior.
- Before writing, changing, or running tests, read `tests/AGENTS.md` for test rules.

## Prohibitions

- Before expanding the agreed task, ask clarifying questions, confirm understanding and obtain the user's approval before writing code.
- The LLM client task must not create database tables, ORM mappings or migrations. The backend team owns `mvp.user_material_studies`; its implementation has not been pulled into this checkout. Treat the supplied schema as context, not authorization to implement it.
- Do not add features outside `docs/.todo/TASKS.md` or change OpenAPI without approval; explicitly flag unspecified behavior.
- Do not restore the dump structure over the target database.
- Do not place SQL outside CRUD, call `commit` inside CRUD, or store a shared mutable session in the application context.
- Do not require external ML/LLM services, keys or GPUs to start the application; do not present generated assumptions as facts about courses, prices or access.
