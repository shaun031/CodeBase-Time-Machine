# Current-snapshot static analysis

Codebase Time Machine analyzes only the current default-branch HEAD. It never checks out or executes the
repository. Git supplies the authoritative tracked-file list and immutable source blobs.

## Pipeline

1. Git history indexing determines and persists the current HEAD SHA.
2. `git ls-tree -r -z -l <head>` enumerates tracked objects with blob SHAs and byte sizes.
3. Path segments, modes, extensions, size limits, and binary signatures determine eligibility.
4. Supported UTF-8-compatible source bytes are parsed with Tree-sitter under a per-file limit.
5. Symbols and imports are normalized in memory; no AST is persisted.
6. File, symbol, import, and parse-error records are written in batches.
7. Local imports are conservatively resolved after all file IDs are stable.
8. The repository becomes ready only after both Git and current-code indexing complete.

One malformed or unsupported file does not fail the repository. Unsupported text appears with
`parse_status=unsupported`; binary, oversized, excluded, parsed, and failed states are explicit.

## Parsers and normalized symbols

`ParserRegistry` exposes one `LanguageParser` interface. Language modules configure their grammar,
symbol nodes, and import forms for Python, JavaScript, TypeScript, TSX, Java, C, C++, Go, and PHP.
Adding another grammar requires a parser module, registry entry, and extension mapping.

Normalized kinds include function, class, method, constructor, interface, enum, struct, trait, and
module. Records contain name, qualified name, signature, one-based start/end lines and columns,
parent symbol, visibility/modifiers when apparent, nearby documentation, and small JSON metadata.
This is structural syntax analysis, not compiler-grade semantic analysis.

Import extraction recognizes common Python `import/from`, ECMAScript `import/require`, Java
`import`, C/C++ include, Go import, and PHP use forms. Relative JavaScript/TypeScript paths, Python
module paths, local includes, and simple Java/PHP paths resolve when one unambiguous tracked target
exists. Package imports remain unresolved.

## Incremental behavior

Each file record stores its Git blob SHA and indexed HEAD SHA. If path and blob are unchanged,
symbols/imports are reused. A same-blob move reuses the file record and updates its path. Changed or
new blobs are parsed; deleted paths cascade-delete their dependent records. Imports are resolved
again because surrounding paths may have changed.

## Security and limits

All public paths must be relative POSIX repository paths. Absolute paths, Windows drive paths,
backslashes used for traversal, empty segments, `.` and `..` are rejected. Application code derives
the storage path from a repository UUID and `REPOSITORY_STORAGE_PATH`; API input never selects a
filesystem location. Symlink blobs are listed but never followed.

Excluded directories: `.git`, `node_modules`, `vendor`, `dist`, `build`, `.next`, `coverage`,
`target`, `bin`, `obj`, `__pycache__`, `.venv`, and `venv`. Known binary/media/archive/compiled
extensions and NUL/control-heavy content are not parsed or returned as source.

The primary limits are `MAX_REPOSITORY_FILES`, `MAX_SOURCE_FILE_SIZE_BYTES`, and
`MAX_PARSE_TIME_PER_FILE_SECONDS`. Content requests use the same source-size bound and reject binary
files. Optional line ranges avoid returning irrelevant content.

**Codebase Time Machine never executes analyzed code.** It never runs package managers, builds, scripts,
tests, repository binaries, or imports target Python modules.

## Limitations

- Extension detection can misclassify ambiguous headers or uncommon generated formats.
- Tree-sitter recovers from many syntax errors, so a parsed file may have nonzero syntax errors.
- Regex-assisted import normalization intentionally handles common forms rather than every grammar
  construct or build-system alias.
- Qualified names describe syntactic nesting and do not resolve overloads, inheritance, dynamic
  dispatch, macros, or runtime metaprogramming.
- Analysis covers current HEAD only; symbol evolution and historical snapshots begin in Phase 3.
