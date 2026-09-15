# Historical analysis

Historical analysis extends the current-code index with stable file and symbol lineage UUIDs. A
lineage represents CodeChronicle’s deterministic best match for one logical symbol across
commits. Versions record how the parser saw that symbol at a specific commit; events describe the
meaningful differences between adjacent versions.

## Indexing pipeline

The service reads commits reachable from the indexed default-branch HEAD in topological,
oldest-first order. For each commit it uses the Phase 1 changed-file rows, ignores excluded and
unrecognized paths, reads the corresponding immutable blob, and invokes the existing Tree-sitter
parser. Repository code is treated only as text. CodeChronicle never checks out or executes a
historical project, installs its dependencies, imports its modules, or invokes hooks.

File lineages follow Git rename detection. Each relevant modification, rename, addition, or
deletion creates a file version linked to its predecessor. Symbol versions point to the matching
file version.

## Symbol matching

`SymbolMatcher` applies deterministic stages and stable tie-breaking:

1. Same file lineage and qualified name.
2. Same file lineage, name, and parent scope after a modification or file rename.
3. Equal normalized bodies for rename or cross-file movement candidates.
4. High body and signature-shape similarity above the configured thresholds.
5. Conservative reintroduction matching against previously deleted symbols.

Body normalization removes whitespace, the extracted signature, and extracted documentation.
Separate SHA-256 fingerprints retain raw source, normalized body, signature, and structure. A
function that moves into a class may continue as a method when its name and body provide a strong
match. Parent lineage IDs are stored on versions.

Candidates within 0.03 confidence of a competing match are treated as ambiguous and left as
separate lineages. Versions expose match type, confidence, and evidence. Symbol rename and move
detection is heuristic unless Git directly supplies file rename information. CodeChronicle does
not claim perfect semantic history reconstruction.

## Events and time travel

The index emits `introduced`, `reintroduced`, `body_changed`, `signature_changed`,
`documentation_changed`, `renamed`, `moved`, `renamed_and_moved`, `modified`, and `deleted` events.
Labels shown by the UI are generated from stored names, paths, and commit metadata; no AI is used.

The repository History page provides category, kind, file, and author filters plus lineage search
over current and previous names. A symbol timeline opens stored or reconstructed historical source
and compares adjacent versions with a bounded unified diff. Commit pages link to affected symbol
lineages. The Code page can display a selected commit’s file content with a clear historical
banner. Blame is a bounded Git attribution view and is not presented as proof of conceptual
authorship.

## Incremental indexing and limits

Every processed commit updates the repository checkpoint in the same database transaction as its
versions and events. A retry resumes after that SHA. Re-running at the same HEAD creates no rows.
A fast-forward repository refresh automatically indexes only new commits when history already
exists. A rewrite marks history stale and causes a clean rebuild.

Safeguards are configured with `MAX_HISTORY_COMMITS`, `MAX_HISTORICAL_FILES`,
`MAX_HISTORICAL_SYMBOL_SOURCE_BYTES`, `MAX_HISTORY_INDEX_TIME_SECONDS`, `MAX_BLAME_LINES`,
`SYMBOL_MATCH_THRESHOLD`, and `SYMBOL_RENAME_MATCH_THRESHOLD`. Reaching a commit, file, or time
budget sets `history_limited` and exposes indexed and total commit counts. The UI displays this
state instead of silently implying complete coverage.

Large source files, binary content, unsupported parsers, and excluded directory segments are not
historically parsed. Recognized files without a parser may still have file lineage metadata. The
service commits one historical commit at a time so it does not retain a repository’s full source
history in memory.

## Security and known limitations

Commit parameters must be full lowercase 40-character SHAs already indexed for that repository.
Paths must be relative, normalized repository paths and cannot contain traversal, drive roots, Git
option prefixes, or command-substitution syntax. Git commands use argument arrays with `--` path
separators, bounded output, disabled external diff/text conversion, and a scrubbed environment.

Historical parsing depends on the supported Phase 2 grammars. Generated code and vendored folders
are excluded. Merge changes are interpreted against the first parent. Similar large refactors may
be split into separate lineages when evidence is weak or ambiguous; this conservative result is
preferred to a false identity claim.
