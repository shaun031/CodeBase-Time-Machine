# Development roadmap

Phase 8 is complete: deterministic architecture snapshots, comparison, dependency and cycle
events, drift baselines, explicit policy rules, violation intervals, trends, APIs, and the
Architecture Time Machine are implemented. SZZ and regression
localization, stack-trace analysis, runtime tracing, and repository execution remain outside this
phase.

| Phase | Scope | Status |
| --- | --- | --- |
| 0 | Foundation: local services, schema, API shell, frontend, checks | Complete |
| 1 | Public repository ingestion and default-branch Git history | Complete |
| 2 | Current-snapshot code explorer and Tree-sitter static analysis | Complete |
| 3 | Historical symbol tracking and time travel | Complete |
| 4 | GitHub pull requests, issues, discussions, and historical context | Complete |
| 5 | Dependency graph and impact analysis | Complete |
| 6 | Ollama, embeddings, grounded RAG, and “Why does this exist?” | Complete |
| 7 | Advanced software archaeology | Complete |
| 8 | Architecture evolution | Complete |
| 9 | Bug and regression investigation | Future |
| 10 | Local performance, polish, demo, and reliability | Future |

Phase 3 adds deterministic history and conservative symbol identity across commits. It does not
infer architecture drift, analyze bug-introducing changes, or introduce AI services. Rename and
move matches remain explicit heuristics with confidence evidence unless Git directly reports a
file rename.

Phase 4 adds a read-only GitHub enrichment index. It preserves explicit PR commit membership,
merge-commit links, closing issue references, and weak mentions as different evidence classes.
GitHub failures remain isolated from Git, code, and symbol history. No AI, embeddings, write
operations, authentication flow, or private-repository access is included.

Phase 5 builds a deterministic dependency graph for the current HEAD. It uses persisted imports,
symbols, repository structure, and Git history; uncertain symbol references are omitted instead of
being guessed. It adds bounded architecture, cycle, metric, coupling, path, and potential-impact
queries without executing repository code or introducing AI services.

Phase 6 adds an optional local Ollama explanation layer. It normalizes evidence from Phases 1–5,
stores model-identified vectors in PostgreSQL, retrieves deterministic relationships before lexical
and semantic candidates, and requires cited structured answers. Ollama failures affect only AI
features. Phase 6 does not add cloud providers, private repository access, code modification,
architecture evolution, or regression attribution.
