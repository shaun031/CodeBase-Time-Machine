# Security boundaries

Public GitHub repositories are untrusted data, never application instructions.
The application performs read-only remote Git operations. It does not execute target
source, scripts, tests, Makefiles, Dockerfiles, hooks, package managers, Maven or Gradle.
Installing this application's own declared dependencies and generating disposable test
history are separate development actions, not analyzed-repository execution.

## Implemented through Phase 2

- Only HTTPS on the exact `github.com` authority is accepted. Credentials, ports,
  subdomains, IPs, SSH/file/custom protocols, escaped path tricks, unexpected segments,
  queries and fragments are rejected. Owner/name are normalized to lowercase and an
  optional `.git` suffix is removed. The network URL is reconstructed, not forwarded.
- Each run verifies public access without authentication. `GITHUB_TOKEN` is never used.
  Git cannot prompt, read the user's credential helpers, global/system configuration,
  netrc home, inherited askpass, proxy settings or external Git environment variables.
- DNS results must be public addresses. The selected address is pinned through
  `http.curloptResolve`; TLS verification is retained and redirects are disabled.
- Bare clones prevent checkout filters and hooks. Hook paths point to an isolated empty
  directory. External diff drivers and text conversion are disabled, submodule recursion
  is off, and the allowed transfer protocol is HTTPS only. Git configuration is generated
  locally; remote repository text cannot replace it.
- Every subprocess uses an argument array, never a shell string. No endpoint accepts a
  Git subcommand, arbitrary revision expression, pathspec, or filesystem destination.
  Commit routes require full hex SHAs found in the repository's persisted history.
- Cache locations derive solely from internal UUIDs. Cleanup validates containment and
  rejects symlinks/junctions. Failed clones are temporary; oversized fetched caches are
  removed. Git output, command durations, commit counts, file counts and disk usage are bounded.
- Errors exclude raw Git stderr, traceback data and cache paths. Author names are shown;
  author emails are kept in persistence only. React renders diff/message text without HTML.
- Compose ports bind to loopback, CORS uses explicit origins, and `.env`/cache files are ignored.
- Current-code discovery uses Git's tracked tree rather than recursive filesystem traversal.
  Source is read by validated blob SHA. Symlink entries are never followed.
- File APIs reject absolute paths, Windows drive paths, backslash traversal, `.` and `..` segments.
  Binary and oversized content is never returned by the source endpoint.
- Tree-sitter receives source bytes only. No target language runtime, package manager, compiler,
  build command, repository hook, or repository-supplied parser plugin is invoked.

The application never pushes, commits, merges, rebases, deletes remote branches, or creates
remote tags. Fetch may update its own private cache refs; upstream repositories are unchanged.
Test fixture scripts do create commits/merges/tags only inside a fresh disposable test directory.

## Local trust and future work

This is a trusted local developer tool without user authentication. Do not expose it on a
shared network. Local users who can tamper with caches or the Git executable are outside
the boundary. Keep Git patched; metadata parsers do not eliminate Git implementation bugs.
Disk polling can temporarily overshoot; strict quotas, filesystem race hardening, global
cache eviction and isolation are future work. No credentials are accepted to bypass a
private-repository error. Cached public history is not revalidated on every read if its
remote later changes visibility. No repository code execution is permitted in future phases.
