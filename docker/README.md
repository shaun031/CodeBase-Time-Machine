# Local containers

Compose owns PostgreSQL 17 with pgvector, Redis, FastAPI, Celery, and Next.js.
The backend runs Alembic migrations before serving; the worker waits for backend
health. Both share configuration and the repository cache volume. Rebuild/restart
the worker after Phase 1 task changes. Git is installed in the backend image.

All published ports bind to loopback. Redis remains ephemeral; use the indexing
page's Resume / requeue job action after losing queue messages. PostgreSQL and
repository cache volumes persist across `docker compose down`. Ollama runs on
the host in a future phase and is never contacted in Phase 1.
