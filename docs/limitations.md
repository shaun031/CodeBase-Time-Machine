# Limitations

CodeBase Time Machine produces deterministic, evidence-backed analysis, but its findings are not
proof of runtime behavior or intent.

- Static analysis approximates imports, calls, inheritance, and architecture. Reflection, dynamic
  dispatch, generated code, dependency injection, and runtime configuration can be absent.
- Git history can be incomplete. Squash merges, rebases, force-pushes, and missing branches hide
  detail. Blame identifies line history, not conceptual ownership.
- Pull requests, issues, reviews, and rate-limit information depend on GitHub's public API. An
  optional token increases quota but is never exposed to the browser.
- SZZ results are candidate bug-introducing commits, not proof of causation. Structural drift is a
  difference measure, not a judgement that an architecture has degraded.
- AI answers depend on the available indexed evidence and local Ollama models. They retain cited
  evidence and limitations, and unavailable AI does not affect deterministic features.
- Safe limits bound graph size, historical work, response sizes, and timeouts. Large repositories
  can report partial or limited results rather than attempting an unsafe full analysis.

The application analyzes public GitHub repositories read-only and never executes their code,
tests, package-manager commands, or scripts.
