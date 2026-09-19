# Bug and regression investigation

The Investigate workspace accepts Python, JavaScript, Java, C, C++, and Go stack frames, exact
error messages, repository paths and lines, commit ranges, and suspected fix commits. The backend
normalizes that input, resolves paths only against indexed repository files, maps lines to current
symbols, and reads immutable Git objects for history and blame.

## Investigation modes

- **Stack Trace** resolves repository frames, searches exact error text, and builds an asynchronous
  evidence report.
- **Regression Range** validates that the known-good commit is an ancestor of the known-bad commit
  and ranks changes inside that bounded ancestry range.
- **Commit Investigation** and **SZZ Analysis** inspect a suspected fix commit. SZZ blames deleted
  parent lines or nearby parent context for addition-only fixes.
- **Line Investigation** resolves one repository-relative path and line at HEAD or an indexed
  commit, then returns blame and file-history evidence.
- **Manual static bisect** suggests a midpoint and accepts good, bad, or unknown classifications.
  It narrows the stored commit range without running repository code.

## Reading candidate scores

The main report weights direct line blame at 0.45, matching symbol history at 0.25, changes to the
failing file at 0.15, membership in a known regression range at 0.10, and an exact error-text match
at 0.05. Large and merge commits are down-ranked. The score is an investigation priority. It is not
a probability, a claim of guilt, or proof that a commit caused a bug.

SZZ is deliberately conservative. Generated and vendor paths, comment-only or whitespace-only
changes, root commits, truncated evidence, and unresolved blame are excluded or disclosed. Merge
fixes use first-parent analysis and say so. Renames follow Git-provided paths where available;
substantial rewrites, squashes, and incomplete history can still reduce accuracy.

## Safety and limits

Inputs are bounded by the Phase 9 settings in `.env.example`. Suspected secrets in failure text are
redacted before persistence. Paths and commit identifiers pass through the existing Git validation
boundary. Analysis never checks out or executes target code and never runs target tests, builds,
scripts, binaries, hooks, or package managers.

The primary APIs are:

- `POST /api/repositories/{repo}/investigations`
- `GET /api/repositories/{repo}/investigations/{id}`
- `GET /api/repositories/{repo}/investigations/{id}/candidates`
- `POST /api/repositories/{repo}/investigations/szz`
- `GET /api/repositories/{repo}/line-history`
- `POST /api/repositories/{repo}/investigations/bisect`
- `POST /api/repositories/{repo}/investigations/bisect/{id}/classify`
