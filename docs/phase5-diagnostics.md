# Phase 5 diagnostic report

This report records the observed Phase 5 behavior before corrective code changes. The primary evidence comes from the indexed Tourism repository `1ed1e682-a26d-4556-ad51-f1b66f26830d`, its local bare Git repository, and the persisted dependency graph.

## Repository and history evidence

- The repository is a complete, non-shallow clone with two commits and one author.
- The initial commit changes 4,077 files. The current head commit changes one file.
- Each currently indexed source file has exactly one matching historical change and one author. The displayed `Changes = 1` and `Authors = 1` values are therefore accurate repository characteristics rather than ingestion failures.
- Representative paths checked directly with Git were `README.md`, `frontend/admin-login.html`, `frontend/pages/admin/admin.css`, `frontend/pages/admin/admin.js`, `frontend/js/auth.js`, and `frontend/pages/tourist/checkout.html`. Each has one historical change and one author.

## Persisted graph evidence before fixes

The ready graph contains 176 nodes and 859 relationships:

| Node type | Count |
| --- | ---: |
| Repository | 1 |
| Module | 8 |
| File | 31 |
| Function | 136 |

| Relationship type | Count |
| --- | ---: |
| `CONTAINS` | 175 |
| `CALLS` | 249 |
| `CO_CHANGES_WITH` | 435 |
| `IMPORTS` | 0 |
| `REFERENCES` | 0 |
| `DEPENDS_ON` | 0 |

All 249 dependency relationships are symbol-to-symbol `CALLS` edges. All 435 file-to-file relationships are one-off co-change edges. There are no module-to-module relationships. The UI receives zero module edges; it is not discarding module UUIDs or failing to transform a nonempty module response.

## Finding classification

1. **White minimap square — CODE BUG.** The React Flow minimap uses its default light background and mask without project theme styles.
2. **Empty coupling results — MIXED / NEEDS FIX.** This repository has no repeated co-change pairs after reliable filtering, so an empty default result is legitimate. The implementation incorrectly classifies the 4,077-file initial commit from only its currently indexed path intersection, producing 435 low-evidence pairs before the API's `min_co_changes = 2` filter hides them. Large-commit detection must use the commit's actual changed-file count, and the API/UI need diagnostics explaining the empty state.
3. **Zero module fan-in and fan-out — MIXED / NEEDS FIX.** Zero is correct for the relationships currently persisted. The graph omits deterministic local HTML-to-CSS and HTML-to-JavaScript references, however, and module history metrics are not aggregated from member files.
4. **Identical hotspot scores — MIXED / NEEDS FIX.** All current files genuinely have the same change count and author count. The current normalization assigns the maximum change-frequency value when `min == max`, making every file start with a `0.45` hotspot score. The tie behavior is undocumented, score components are not exposed, and missing file dependencies prevent degree centrality from differentiating connected files.
5. **859 total relationships with disconnected modules — MIXED / NEEDS FIX.** The number combines containment, symbol calls, and 435 one-off co-change relationships. It does not mean 859 module dependencies. The Architecture header needs distinct total and dependency counts, and reliable file dependencies must be aggregated to module level.
6. **Shallow history suspicion — EXPECTED REPOSITORY CHARACTERISTIC.** Git reports `--is-shallow-repository=false`; the repository itself contains only two commits.
7. **Missing HTML/CSS relationships — CODE BUG.** A safe local scan found 26 resolvable repository-local HTML references. Examples include `frontend/admin-login.html` referencing `frontend/pages/admin/admin.css` and `frontend/pages/admin/admin.js`. These references are absent from the graph. External CDN URLs were observed and must remain unfetched and excluded from local graph resolution.

## Coupling diagnostics before fixes

- Commits examined: 2
- Commits treated as usable by the current implementation: 2
- Large commits excluded: 0
- Candidate pairs generated: 435
- Pairs surviving the default API filter (`min_co_changes=2`, `min_score=0.2`): 0

The correct classification for the 4,077-file initial commit is excluded. That leaves one usable one-file commit, zero candidate pairs, and an explainable empty coupling result.

## Metric definitions to preserve and clarify

- Fan-in and fan-out count valid dependency relationships at the same graph level. Containment and co-change relationships do not count as dependency fan-in or fan-out.
- File change count is the number of distinct matching commits; file author count is the number of distinct matching commit authors.
- Module history metrics should aggregate distinct commits and authors across current member files.
- The existing hotspot weights remain: change frequency `0.45`, degree centrality `0.35`, and coupling `0.20`.
- When every node at a level has the same positive change count, normalization should use a documented neutral value rather than treating every value as the maximum. An all-zero level should normalize to zero.

Post-fix counts, validation results, and reindex evidence will be appended after implementation.

## Post-fix reindex evidence

The Tourism repository was reindexed at HEAD `f0535fbd0d299609584065e362cbb20c78792ce0`. The graph completed with status `ready`, was not limited or stale, and produced 176 nodes and 477 total relationships:

| Relationship type | Count |
| --- | ---: |
| `CONTAINS` | 175 |
| `CALLS` | 249 |
| `REFERENCES` | 26 |
| `DEPENDS_ON` | 27 |
| `CO_CHANGES_WITH` | 0 |

The 27 aggregate dependencies comprise 26 file-to-file edges and one module-to-module edge. The module edge is `frontend -> frontend/pages/admin`, supported by two local file dependencies. The module metrics now report `frontend` fan-out 1 and `frontend/pages/admin` fan-in 1. Other zero module fan values reflect dependencies that stay within their module boundary.

Coupling diagnostics now report two commits examined, one usable commit, one large commit excluded, zero candidate pairs, and zero pairs after filtering. The empty result is therefore expected and is explained in the UI.

All 31 file histories remain at one change and one author, matching Git. Their change-frequency input now receives the documented neutral value `0.5`. Dependency centrality differentiates connected files: for example, `frontend/admin-login.html` has fan-out 2 and hotspot `0.248333`, while `frontend/js/auth.js` has fan-in/out 0 and hotspot `0.225`. The API exposes each weighted contribution.

## Validation

- Backend static checks: Ruff and mypy pass.
- Complete backend suite with PostgreSQL integration enabled: 166 passed, 1 skipped.
- Phase 5 PostgreSQL integration fixture: passed. It covers HTML/CSS resolution, module aggregation, level-specific fan metrics, large-commit exclusion, exact coupling diagnostics, idempotent rebuilds, and the absence of invented traditional-JavaScript file dependencies.
- In the requested four-commit A/B/C fixture, raw shared commits are A-B `3`, A-C `2`, and B-C `1`. Under the documented formula, normalized scores are `1.0`, `1.0`, and `0.5`: A-B has more evidence than A-C, while both have perfect coupling relative to the less frequently changed file. The implementation preserves this mathematical result instead of changing the formula to force unequal normalized scores.
- Frontend typecheck and ESLint: pass.
- Frontend component/API suite: 35 passed.
- Frontend production build: pass.
- Live graph endpoints for status, metrics, coupling, module graph, and file graph returned HTTP 200 after reindex.
- A second live reindex remained at 176 nodes and 477 relationships, preserved all module node IDs, and returned the same single module dependency edge.
- The database revision and Alembic head both resolve to `0007_graph_timestamp_constraints`.
