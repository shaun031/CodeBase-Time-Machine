# Architecture evolution and drift

Phase 8 builds module and top-level component snapshots from immutable Git trees and blobs. It
uses the existing language detector, Tree-sitter parsers, import resolver, and HTML/CSS static
reference extractor. It never checks out or executes repository code.

The adaptive strategy keeps source-affecting commits, the first and current commit, and tagged
commits. `interval` samples at the configured commit interval; `all` is intended for small test
repositories. Blob parse results are cached during one build. Reindexing at an unchanged HEAD is
idempotent, and a normal fast-forward appends later snapshots. Rewritten or out-of-order history
causes an atomic rebuild of derived snapshot data.

Snapshot comparisons use stable module/component keys and report node, edge, weight, layer, and
cycle changes. A cycle is a strongly connected component with at least two modules. Its stable
fingerprint is the SHA-256 hash of its sorted member keys.

Structural drift is a descriptive distance from a selected baseline:

```text
100 × (0.25 node Jaccard distance
     + 0.60 dependency-edge Jaccard distance
     + 0.15 cycle Jaccard distance)
```

A structural drift score never means that the architecture is wrong. Only an enabled explicit
rule creates a policy violation. Supported rules are `forbidden_dependency`,
`allowed_dependency`, and `forbidden_cycle`; selectors can target a layer, component, exact module,
or path prefix. Layer rules require the configured classification confidence. Violation records
store their introducing snapshot/commit and, when applicable, their resolving snapshot/commit.

The repository **Evolution** page provides the timeline slider, historical graph, commit/tag
comparison, drift score, trend chart, rule preview/editor, and active/resolved violations. Event
links open the exact commit and include associated public GitHub pull requests when that evidence
has been synchronized.

The API is rooted at `/api/repositories/{id}/architecture` and includes `history/status`,
`history/reindex`, `snapshots`, `at/{commit_sha}`, `compare`, `evolution`, `drift`, `trends`,
`baselines`, `rules`, `rules/validate`, and `violations`.

Static analysis may miss dependencies produced by runtime dispatch, dependency injection
configuration, reflection, generated code, or files excluded by the configured safety limits.
