# Software archaeology

Phase 7 derives provenance and temporal metrics from the Git, current-code, symbol-history, GitHub-context, and dependency-graph indexes. The index never executes repository code and does not require Ollama.

## Evidence and dates

The canonical date is the Git **committer date**. Symbol ancestry is the existing Phase 3 lineage and retains each version's match type, confidence, and matching metadata. File ancestry uses Git rename-aware file lineages. Merge commits are omitted from touch and churn totals when ordinary commits provide the same history, which avoids counting branch changes twice.

Git blame is computed once during archaeology indexing for current files within `MAX_BLAME_LINES`; the cached result includes the oldest, newest, median, and mean line age. Generated, vendor, build, and dependency directories follow the Phase 2 exclusion rules. Raw contributor email addresses are never returned. A SHA-256 hash of the normalized Git email keeps distinct Git identities separate without guessing that a Git name and GitHub login belong to one person.

## Metrics

Churn is `lines added + lines deleted`. A high value means frequently changed; it is not a quality or defect prediction.

Volatility is bounded to 0–1:

```text
0.35 * min(changes in configured recent window / 6, 1)
+ 0.30 * min(total changes / 12, 1)
+ 0.20 * min(major rewrites / 3, 1)
+ 0.15 * min(contributors / 5, 1)
```

Stability is also bounded to 0–1 and combines elapsed time, frequency, and recent activity rather than simply inverting volatility:

```text
0.50 * days_since_change / (days_since_change + 180)
+ 0.30 * 1 / (1 + total_changes / 4)
+ 0.20 * (1 - min(changes in configured recent window / 6, 1))
```

Classifications have explicit rules: deleted entities are `deleted`; a rewritten entity changed in the recent window is `recently_rewritten`; code younger than 90 days is `new_code`; code at least one year old with no recent changes and at most two total changes is `stable_legacy`; volatility of at least 0.65 is `frequently_changed`; old code with recent activity is `long_lived_active`; code without recent activity is `recently_inactive`; remaining entities are `active`.

The historical knowledge score for one target is normalized among its contributors:

```text
0.65 * commits touching target
+ 0.25 * exp(-days since latest touch / 365)
+ 0.10 * introduction bonus
```

Knowledge concentration reports the largest touch share and normalized Shannon entropy. It is labelled concentrated when the largest share is at least 60% or normalized entropy is below 0.45. These values describe repository-history evidence and do not establish expertise, legal ownership, employment, or organizational risk.

## Rewrite and related-code detection

Symbol source is tokenized after comments and formatting are removed. A major rewrite requires a meaningful body, replacement of at least four lines or 40% of the body, and token similarity below `SYMBOL_REWRITE_SIMILARITY_THRESHOLD`. Documentation-only and small edits do not meet the rule.

Related-code detection first buckets candidates by language, symbol kind, and token count, then performs detailed token-sequence similarity. Exact surviving matches are `exact_copy`; exact matches whose source disappeared first are `known_move`; non-exact matches are conservatively labelled `probable_copy` or `probable_move`. Similarity is evidence of related code, not proof of copying. Embeddings are not used as proof.

## Indexing and limits

`POST /api/repositories/{id}/archaeology/reindex` starts `archaeology_index` through the configured local-thread or Celery executor. `GET /api/repositories/{id}/archaeology/status` reports progress, counts, indexed SHA, staleness, and safe errors. The build uses existing records and the local bare Git cache; it never reclones. A changed head or rewritten history marks the result stale and a rebuild removes references to vanished commits.

The bounded settings are `ARCHAEOLOGY_RECENT_DAYS`, `MAX_ARCHAEOLOGY_FILES`, `MAX_ARCHAEOLOGY_SYMBOLS`, `MAX_COPY_CANDIDATES_PER_SYMBOL`, `MAX_REWRITE_COMPARISONS`, `MAX_ARCHAEOLOGY_SEARCH_RESULTS`, and `MAX_ARCHAEOLOGY_BUILD_SECONDS`. Native Windows local mode works without Docker, Redis, Celery, or Ollama.

## Limitations

Git history may be incomplete. Squash merges can hide intermediate development, and force pushes can remove evidence. Git author identity may differ from GitHub identity. A contributor touching code does not prove expertise. Similarity does not prove copying. High churn does not prove poor quality. Old code is not necessarily bad, and new code is not necessarily unstable.
