# Phase 5 verification

Verified on 2026-09-12 on Windows with Python 3.13.2, Node 22.20.0, Docker Desktop,
PostgreSQL 17 with pgvector, and the native local-task execution mode.

## Automated checks

| Check | Observed result |
| --- | --- |
| Backend pytest without opt-in services | 149 passed, 14 skipped |
| PostgreSQL integration suite | 13 passed against isolated, fully migrated schemas |
| Graph unit coverage | Resolution priority and ambiguity, SCC cycles, impact traversal, grouping, layers, inheritance, and external-package normalization passed |
| Graph refresh integration | Removed A→B, added A→C, retained an unaffected node ID, and produced identical results on repeated builds |
| Ruff lint and format | Passed for all backend application, test, and script files |
| mypy | Passed for 91 application source files |
| Frontend Vitest | 33 passed across 2 files |
| ESLint, Prettier, and TypeScript | Passed |
| Next.js production build | Passed, including the Architecture route |
| Alembic live migration | `0007_graph_timestamp_constraints (head)` with no pending schema operations |

The only automated warnings are two upstream FastAPI/Starlette test-client deprecations. The
application, migrations, graph algorithms, and parsers produce no test warnings. Combining the
normal and integration runs covers 162 tests; the remaining skip is the deliberately opt-in live
GitHub network test.

Integration tests create a random PostgreSQL schema, apply every Alembic migration, exercise real
local Git repositories, and remove the schema afterward. `127.0.0.1` is used for the Windows host
database connection to avoid environment-specific IPv6 `localhost` resolution delays.

## Live repository verification

The native backend rebuilt `shaun031/Tourism-Management` at commit
`f0535fbd0d299609584065e362cbb20c78792ce0`. Graph status reported `ready`, current rather than
stale, with no configured limit reached:

- 176 normalized nodes and 859 evidence-bearing edges.
- 8 module nodes, 31 file nodes, and 136 symbol nodes.
- 2 inferred components: `frontend` as a presentation layer and `root` as unknown.
- 0 file/module strongly connected dependency components.

The graph count is larger than the static dependency count because change coupling, containment,
and aggregation are distinct edge types. This repository has a small history dominated by an
initial multi-file commit, so the UI uses the API's default requirement of at least two shared
commits before displaying a coupling pair.

## Runtime and browser checks

- The backend was launched with the documented `backend\npm run dev` command and
  `GET /api/health` returned HTTP 200.
- The frontend was launched with the documented `frontend\npm run dev` command and served the
  Architecture route at HTTP 200.
- The graph status, module graph, file drill-down, metrics, architecture, cycles, coupling,
  reindex, node-detail, impact, and path services returned typed responses.
- A live graph rebuild completed through the asynchronous API while the repository stayed ready.
- The browser displayed graph counts, component/layer cards, eight module nodes, React Flow zoom,
  pan and minimap controls, and a 30-file drill-down after selecting `frontend`.
- The Hotspots view explained its ranking and rendered results; Cycles displayed the verified
  empty state; Change Coupling rendered with the documented evidence threshold.
- Browser console inspection found no application errors or hydration warnings.

## Expected limits

Analysis covers the current indexed default-branch HEAD and derives a deterministic static
approximation. Dynamic dispatch, reflection, generated code, runtime dependency injection, and
ambiguous references may be absent. The application never executes analyzed repository content.
Phase 5 adds no AI, Ollama, embeddings, RAG, or generated explanations.
