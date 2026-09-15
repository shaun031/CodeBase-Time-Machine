# Deterministic dependency graph

Phase 5 models the current default-branch HEAD as a directed property graph. PostgreSQL stores the
normalized graph and its evidence. NetworkX is used only while calculating paths, strongly
connected components, traversal results, and centrality.

## Nodes and edges

Nodes represent a repository, top-level modules, files, classes, interfaces, functions, methods,
constructors, enums, structs, traits, and external packages. Stable UUIDv5 identifiers are derived
from the repository, node type, and qualified name. This keeps unchanged entities addressable
across idempotent rebuilds.

Persisted edges include `CONTAINS`, `IMPORTS`, `IMPORTS_EXTERNAL`, `CALLS`, `INHERITS`,
`IMPLEMENTS`, `DEPENDS_ON`, and `CO_CHANGES_WITH`. Each edge stores a numeric weight, confidence,
resolution type, and bounded evidence. File and module `DEPENDS_ON` edges aggregate supported
symbol and import relationships. Unsupported or ambiguous references are omitted; absence of an
edge is not proof that a runtime relationship cannot exist.

Resolution follows an explicit priority: exact qualified name, same file, an imported target,
same module, then a unique repository-wide symbol. A tier with multiple valid candidates is
rejected. Candidate count is bounded by `MAX_CALL_RESOLUTION_CANDIDATES`.

## Architecture and change coupling

Files are grouped into components by top-level directory. A conservative path heuristic labels
common presentation, application, domain, data, infrastructure, and test layers and records its
confidence. Directory names outside those rules remain `unknown`.

Git coupling counts commits that change a file pair. Commits touching more than
`MAX_FILES_PER_COMMIT_FOR_COUPLING` files are excluded as noisy. The directed pair score is:

```text
co-change count / min(source file changes, target file changes)
```

The graph computes fan-in, fan-out, degree centrality, change count, author count, coupling, and a
ranking aid called hotspot score:

```text
0.45 * normalized changes + 0.35 * degree centrality + 0.20 * coupling
```

A hotspot score is a navigation signal, not a code-quality verdict. File and module cycles use
NetworkX strongly connected components; a self-loop counts only when an actual edge exists.

## Potential impact

Impact analysis traverses reverse dependencies from exactly one file or symbol. Results separate
direct and transitive dependents, callers, callees, and change-coupled files, and include bounded
evidence paths where available. The UI consistently calls these results “Potential impact” and
“Potentially affected” because static analysis cannot prove runtime behavior.

The API also supports bounded module, file, and symbol graph views, node neighborhoods, directed
paths, components, layers, cycles, coupling, and metrics. `MAX_GRAPH_RESPONSE_NODES` and
`MAX_GRAPH_DEPTH` prevent oversized interactive responses; build-time node, edge, and time limits
are recorded in graph status instead of being hidden.

## Safety and limitations

The builder reads tracked blobs from the credential-free bare Git cache. It never checks out or
executes repository code, imports modules, installs repository dependencies, or invokes build
tools. Paths pass the same repository path validation as the code explorer, and API responses do
not expose server paths or raw Git errors.

The graph covers only the current indexed HEAD. Dynamic dispatch, reflection, generated code,
runtime dependency injection, unresolved language-specific import forms, and references with
ambiguous candidates may be absent. Phase 5 contains no AI, Ollama, embeddings, RAG, or generated
explanations.
