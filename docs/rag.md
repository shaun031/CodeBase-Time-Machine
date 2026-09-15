# Evidence retrieval and grounded answers

Phase 6 treats Git, static analysis, GitHub context, symbol history, and the dependency graph as the
source of truth. Ollama explains retrieved evidence; it does not create repository facts.

The embedding job creates normalized documents for commits and changed paths, current and
historical symbols, symbol changes, bounded diff chunks, pull requests, issues, individual
comments, review comments, architecture components, and dependency metrics. It filters secret-like
paths such as `.env*`, private keys, `credentials.json`, and `secrets.*`. Binary artifacts and
unbounded raw objects are excluded.

Retrieval follows an explainable order:

1. Resolve an explicit symbol, selected line range, commit, pull request, issue, or file.
2. Expand deterministic links through symbol events, blame commits, commit/PR membership, and
   PR/issue references.
3. Add exact lexical matches for identifiers, issue numbers, PR numbers, SHAs, and error strings.
4. Add cosine-similarity candidates only from vectors with the configured model and dimension.
5. Fuse duplicate results, preserving direct evidence above semantic matches, then enforce the
   context character budget.

Evidence sufficiency is calculated from relationship quality before generation. A symbol change
linked to its commit, PR, and issue is strong. A lone commit or code record is weak. No useful
direct evidence is insufficient. Answer confidence cannot exceed this level.

Repository evidence is serialized inside explicit delimiters and labeled as untrusted data in the
system prompt. Issue text, PR descriptions, code comments, and source can contain prompt-like text;
the model is instructed never to follow it. Generated JSON is validated, retried once if malformed,
and all fabricated evidence IDs are removed. User-visible answer sentences are reconstructed from
claims that retain at least one valid citation. Hidden prompts and chain-of-thought are neither
returned nor stored.

Set `AI_DEBUG=true` during local development and send `debug: true` to the Ask endpoint to receive
safe counts, resolved target metadata, retrieval timing, intent, and context size. The diagnostics
exclude system prompts, full sensitive queries, vectors, credentials, and local absolute paths.
The search endpoint `/api/repositories/{id}/ai/search?q=...&top_k=10` returns ranked evidence but
never returns embedding values.
