# Data model

The PostgreSQL schema is grouped by responsibility. Every derived record is scoped to a repository
and rebuilt idempotently from read-only Git or GitHub evidence.

- **Repository and Git:** `repositories`, `analysis_jobs`, `commits`, `commit_parents`,
  `file_changes`, and `tags` hold the default-branch cache and indexing state.
- **Current code:** `repository_files`, `code_symbols`, `code_imports`, and `file_parse_errors`
  represent the current HEAD only.
- **History:** file/symbol lineages, versions, and change events preserve historical identity.
- **GitHub context:** normalized metadata, users, pull requests, issues, labels, comments,
  review comments, commit links, issue references, and `github_sync_state`.
- **Graph:** dependency nodes/edges, architecture components/members, and `graph_index_states`.
- **AI:** evidence documents, embeddings, answer cache, and `ai_index_states`. Vectors are tied
  to their discovered model and dimension.
- **Archaeology and architecture history:** derived metrics, rewrite/copy evidence, contributors,
  snapshots, evolution events, baselines, rules, violations, and independent state tables.
- **Investigation:** reports, candidate feedback, and manual static bisect sessions.

Foreign keys cascade only derived data with their repository. Unique keys and deterministic
identities make reindexing safe to repeat.
