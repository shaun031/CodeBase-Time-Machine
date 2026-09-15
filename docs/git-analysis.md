# Git ingestion design

`GitService` owns Git operations. `GitRunner` is its private subprocess layer;
routes and worker orchestration do not construct Git commands. The fixture generator
is intentionally separate test tooling and can write only a new disposable repository.

## Clone and fetch

Public access is checked using unauthenticated `ls-remote --symref` against a URL
constructed from validated owner/name. Empty repositories are valid with zero commits.
Remote HEAD supplies the default branch; `main`/`master` are not assumed. DNS results
must be globally routable and the chosen address is pinned to the Git HTTPS connection.
HTTP redirects, proxies, credential helpers, inherited Git configuration, and prompts
are disabled. Git's certificate validation remains enabled.

A full-history, single-branch **bare** clone is first created at `{UUID}/repo.tmp`,
then renamed to `{UUID}/repo`. There is no checkout or submodule recursion. Failed
temporary clones are removed after validating containment and rejecting links/junctions.
Fetch uses the canonical URL rather than trusting the stored remote configuration,
updates `refs/heads/ctm-index`, and updates/prunes tags. The fetched ref determines
the indexed head, accounting for changes between initial verification and transfer.

Git commands have timeouts and bounded stdout; stderr is drained without retention.
Timeout/output/disk-limit cancellation kills the process tree. Initial clones and
fetches have disk-usage monitoring and a final size check. A failed oversized fetch
removes its cache safely so it cannot leave an indefinitely oversized directory.
Disk polling is not an OS quota and concurrent local tampering is outside the trusted
developer-machine model. No process-wide unlimited capture or shell evaluation is used.

## Parsing and semantics

Reachable SHAs are enumerated in oldest-first topological order, bounded by MAX_COMMITS.
Only this small SHA list is retained; full commit metadata is read one commit at a time.
Metadata uses NUL separators and preserves multiline Unicode messages. Raw and numstat
file changes use NUL-separated paths, not whitespace splitting. Paths with tabs/newlines
are supported. Invalid UTF-8 is shown as escaped bytes; embedded NUL text is sanitized
for PostgreSQL. Changes have deterministic per-commit order.

Rename detection uses `-M`. Root commits compare against the empty tree; merges compare
against the first parent and preserve *all* ordered parent SHAs separately. Binary file
line counts are null and excluded from insertion/deletion totals. There are no full
source snapshots or stored patches. Diffs are generated only when requested, with
external drivers/text conversion disabled and explicit truncation at the raw byte cap.

The commit list is newest committed date first, with SHA as a deterministic tie-breaker.
It is paginated (maximum 100 items). This display order differs intentionally from
topological ingestion order. Timestamps are timezone-aware; the UI formats absolute dates.

## Persistence and recovery

Commits have unique `(repository_id, sha)`. Parents and changes have unique commit/order
keys; tags have unique repository/name. Inserts are grouped in transactions of up to
100 commits or around 2,000 child rows; a single unusually large commit remains atomic.
Every commit and its child rows commit together. Retry skips fully persisted commits.
Progress is the measured count of processed commits; finalization has no percentage.

Canonical-identity transaction advisory locks serialize submission across API processes.
A partial unique index permits one queued/running job per repository. A separate session
advisory lock serializes worker runs across batch commits and disappears on process death.
Completed or failed job deliveries are no-ops; failed indexing is retried with a new job.
Queued/running jobs may be republished with the same ID for manual recovery. Celery uses
late acknowledgments and rejects tasks on worker loss. Database job state is authoritative.

Publishing follows database commit so the worker can see its job. If publication fails
and the job is still queued, both records are marked failed with a safe error. If publication
was accepted and processing already started, that work is not overwritten. A crash in the
commit/publish gap needs the explicit resume/requeue action; no automatic scheduler exists.

Refresh fetches the latest default branch and tests whether the last indexed SHA remains
an ancestor. New SHAs are indexed; on success, unreachable old commit rows are removed
with their child rows and tags are replaced atomically. A history-rewritten indicator
records a non-ancestor transition. Failed runs retain reusable committed batches; history
APIs require ready state so partially reconciled history is not presented as complete.

## Reference behavior

Git formats and safety options follow the official [diff-tree documentation](https://git-scm.com/docs/git-diff-tree)
and [Git configuration documentation](https://git-scm.com/docs/git-config).
