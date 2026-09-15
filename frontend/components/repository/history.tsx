"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import {
  useHistoryEvents,
  useHistoryReindex,
  useHistoryStatus,
  useRepository,
} from "@/hooks/use-repository";
import { api, errorMessage } from "@/lib/api";
import { dateLabel } from "@/lib/repository";
import { QueryError } from "./workspace";
import { RepositoryNav } from "./repository-nav";

const filters = [
  "All",
  "Introduced",
  "Modified",
  "Renamed",
  "Moved",
  "Deleted",
];
const categories: Record<string, string[]> = {
  Introduced: ["introduced", "reintroduced"],
  Modified: [
    "modified",
    "body_changed",
    "signature_changed",
    "documentation_changed",
  ],
  Renamed: ["renamed", "renamed_and_moved"],
  Moved: ["moved", "renamed_and_moved"],
  Deleted: ["deleted"],
};

export function HistoryExplorer({ repoId }: { repoId: string }) {
  const repository = useRepository(repoId);
  const status = useHistoryStatus(repoId);
  const reindex = useHistoryReindex();
  const [filter, setFilter] = useState("All");
  const [search, setSearch] = useState("");
  const [symbolKind, setSymbolKind] = useState("");
  const [filePath, setFilePath] = useState("");
  const [author, setAuthor] = useState("");
  const [page, setPage] = useState(1);
  const ready = ["ready", "limited"].includes(status.data?.status ?? "");
  const events = useHistoryEvents(
    repoId,
    { symbolKind, filePath: filePath.trim(), author: author.trim(), page },
    ready,
  );
  const lineages = useQuery({
    queryKey: ["lineage-search", repoId, search],
    queryFn: () => api.searchLineages(repoId, search),
    enabled: ready && search.trim().length >= 2,
  });
  const visibleEvents = useMemo(() => {
    const accepted = categories[filter];
    return accepted
      ? events.data?.items.filter((item) => accepted.includes(item.event_type))
      : events.data?.items;
  }, [events.data, filter]);

  if (repository.isError)
    return (
      <QueryError error={repository.error} retry={() => repository.refetch()} />
    );
  if (!repository.data || status.isPending)
    return <p role="status">Loading historical index…</p>;
  if (status.isError)
    return <QueryError error={status.error} retry={() => status.refetch()} />;

  return (
    <>
      <p className="mono eyebrow">DETERMINISTIC CODE LINEAGE</p>
      <h1 className="repo-title">{repository.data.full_name}</h1>
      <RepositoryNav repoId={repoId} active="History" />

      {!ready ? (
        <section className="history-panel history-empty">
          <h2>
            {status.data?.status === "failed"
              ? "Historical analysis failed"
              : status.data?.status === "stale"
                ? "Historical analysis is stale"
                : status.data?.status === "indexing" ||
                    status.data?.status === "queued"
                  ? "Building symbol history"
                  : "Build the historical code index"}
          </h2>
          <p className="muted">
            CodeChronicle reads Git objects and parses only changed source
            files. Repository code is never executed.
          </p>
          {status.data?.progress != null && (
            <div
              className="history-progress"
              aria-label="Historical indexing progress"
            >
              <span style={{ width: `${status.data.progress}%` }} />
            </div>
          )}
          <p className="muted">
            {status.data?.current_step?.replaceAll("_", " ") ||
              status.data?.status}
          </p>
          {!["indexing", "queued"].includes(status.data?.status ?? "") && (
            <button
              onClick={() =>
                reindex.mutate(repoId, { onSuccess: () => status.refetch() })
              }
              disabled={reindex.isPending}
            >
              {reindex.isPending ? "Starting…" : "Index repository history"}
            </button>
          )}
          {reindex.isError && (
            <p className="error-message" role="alert">
              {errorMessage(reindex.error)}
            </p>
          )}
        </section>
      ) : (
        <>
          {status.data?.history_limited && (
            <p className="notice" role="status">
              Historical analysis is limited to {status.data.indexed_commits} of{" "}
              {status.data.total_commits} commits by the configured safety
              limits.
            </p>
          )}
          {status.data?.history_stale && (
            <p className="notice" role="status">
              Git history changed. Reindex history before relying on this
              timeline.
            </p>
          )}
          <section className="history-summary">
            <div>
              <small>Commits analyzed</small>
              <strong>{status.data?.indexed_commits ?? 0}</strong>
            </div>
            <div>
              <small>Symbol lineages</small>
              <strong>{status.data?.lineages ?? 0}</strong>
            </div>
            <div>
              <small>Versions</small>
              <strong>{status.data?.versions ?? 0}</strong>
            </div>
            <div>
              <small>Events</small>
              <strong>{status.data?.events ?? 0}</strong>
            </div>
          </section>
          <div className="history-toolbar">
            <div className="history-filters" aria-label="History filters">
              {filters.map((item) => (
                <button
                  key={item}
                  className={filter === item ? "active" : ""}
                  onClick={() => setFilter(item)}
                >
                  {item}
                </button>
              ))}
            </div>
            <label>
              <span className="sr-only">Search historical symbols</span>
              <input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search current or previous names…"
              />
            </label>
            <label>
              <span className="sr-only">Filter by symbol kind</span>
              <select
                aria-label="Filter by symbol kind"
                value={symbolKind}
                onChange={(event) => {
                  setSymbolKind(event.target.value);
                  setPage(1);
                }}
              >
                <option value="">All symbol kinds</option>
                <option value="function">Functions</option>
                <option value="class">Classes</option>
                <option value="method">Methods</option>
                <option value="interface">Interfaces</option>
                <option value="struct">Structs</option>
              </select>
            </label>
            <label>
              <span className="sr-only">Filter by file path</span>
              <input
                value={filePath}
                onChange={(event) => {
                  setFilePath(event.target.value);
                  setPage(1);
                }}
                placeholder="File path…"
              />
            </label>
            <label>
              <span className="sr-only">Filter by author</span>
              <input
                value={author}
                onChange={(event) => {
                  setAuthor(event.target.value);
                  setPage(1);
                }}
                placeholder="Author…"
              />
            </label>
            <button
              onClick={() =>
                reindex.mutate(repoId, { onSuccess: () => status.refetch() })
              }
              disabled={reindex.isPending}
            >
              Refresh history
            </button>
          </div>
          {search.trim().length >= 2 && (
            <div className="lineage-results">
              {lineages.isPending ? (
                <p role="status">Searching historical symbols…</p>
              ) : lineages.isError ? (
                <p role="alert">{errorMessage(lineages.error)}</p>
              ) : lineages.data?.items.length ? (
                lineages.data.items.map((item) => (
                  <Link
                    key={item.lineage_id}
                    href={`/repos/${repoId}/history/symbols/${item.lineage_id}`}
                  >
                    <strong>
                      {item.current_qualified_name || item.current_name}
                    </strong>
                    <span>
                      {item.symbol_kind} ·{" "}
                      {item.is_deleted ? "Deleted" : "Active"}
                      {item.previous_names.length > 1
                        ? ` · Previously: ${item.previous_names.slice(0, -1).join(", ")}`
                        : ""}
                    </span>
                  </Link>
                ))
              ) : (
                <p>No matching historical symbols.</p>
              )}
            </div>
          )}
          {events.isPending ? (
            <p role="status">Loading code timeline…</p>
          ) : events.isError ? (
            <QueryError error={events.error} retry={() => events.refetch()} />
          ) : visibleEvents?.length ? (
            <ol className="symbol-timeline repository-timeline">
              {visibleEvents.map((event) => (
                <li key={event.id}>
                  <span
                    className={`event-dot event-${event.event_type}`}
                    aria-hidden="true"
                  />
                  <div>
                    <span className="badge">
                      {event.event_type.replaceAll("_", " ")}
                    </span>
                    <h2>
                      <Link
                        href={`/repos/${repoId}/history/symbols/${event.lineage_id}`}
                      >
                        {event.deterministic_label}
                      </Link>
                    </h2>
                    <p className="mono">{event.file_path || "Unknown file"}</p>
                    <p>
                      <Link
                        href={`/repos/${repoId}/commits/${event.commit.sha}`}
                      >
                        {event.commit.short_sha}
                      </Link>{" "}
                      ·{" "}
                      {event.commit.message.split("\n")[0] ||
                        "(no commit message)"}{" "}
                      · {event.commit.author_name} ·{" "}
                      {dateLabel(event.commit.committed_at)}
                    </p>
                  </div>
                </li>
              ))}
            </ol>
          ) : (
            <section className="history-panel">
              <p>No events match this filter.</p>
            </section>
          )}
          {events.data && events.data.total > events.data.page_size && (
            <nav className="pagination" aria-label="History pages">
              <button
                disabled={page === 1}
                onClick={() => setPage((value) => value - 1)}
              >
                Previous
              </button>
              <span>
                Page {page} of{" "}
                {Math.ceil(events.data.total / events.data.page_size)}
              </span>
              <button
                disabled={page * events.data.page_size >= events.data.total}
                onClick={() => setPage((value) => value + 1)}
              >
                Next
              </button>
            </nav>
          )}
        </>
      )}
    </>
  );
}
