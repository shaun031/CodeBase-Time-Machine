# Performance and bounds

Measurements depend on repository shape, disk, PostgreSQL, and local Ollama hardware. The project
therefore records safe job duration fields (`task`, `repository_id`, `job_id`, and
`duration_seconds`) in structured development logs instead of claiming universal benchmarks.

The default user experience is bounded: API lists paginate, graph responses use a capped node
count and begin at module level, source/diff payloads are limited, and heavy detail queries only
run when their panel is opened. TanStack Query retains stable data briefly and polls only active
indexes. Evidence embedding reuses content hashes and keeps retrieval context bounded.

For a larger repository, review the Overview health panel first. A `limited` state means the
configured safe limit was reached; the available partial result remains usable. Increase limits
only after measuring memory, database, and browser impact on the development machine.
