"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useLineage, useRepository } from "@/hooks/use-repository";
import { api, errorMessage } from "@/lib/api";
import { dateLabel } from "@/lib/repository";
import { QueryError } from "./workspace";
import { RepositoryNav } from "./repository-nav";

function sourceLines(value: string): string[] {
  return value ? value.split(/\r\n|\n|\r/) : [];
}

export function SymbolHistory({
  repoId,
  lineageId,
}: {
  repoId: string;
  lineageId: string;
}) {
  const repository = useRepository(repoId);
  const lineage = useLineage(repoId, lineageId);
  const [selected, setSelected] = useState<string | null>(null);
  const [compare, setCompare] = useState(false);
  const selectedVersion = selected ?? lineage.data?.latest_version?.id ?? null;
  const source = useQuery({
    queryKey: ["historical-symbol-source", repoId, lineageId, selectedVersion],
    queryFn: () =>
      api.getHistoricalSymbolSource(repoId, lineageId, selectedVersion!),
    enabled: Boolean(selectedVersion),
  });
  const versionIndex =
    lineage.data?.versions.findIndex((item) => item.id === selectedVersion) ??
    -1;
  const selectedDetails =
    versionIndex >= 0 ? lineage.data?.versions[versionIndex] : null;
  const previous =
    versionIndex > 0 ? lineage.data?.versions[versionIndex - 1] : null;
  const comparison = useQuery({
    queryKey: [
      "symbol-compare",
      repoId,
      lineageId,
      previous?.id,
      selectedVersion,
    ],
    queryFn: () =>
      api.compareSymbolVersions(
        repoId,
        lineageId,
        previous!.id,
        selectedVersion!,
      ),
    enabled: compare && Boolean(previous && selectedVersion),
  });
  const context = useQuery({
    queryKey: ["symbol-context", repoId, lineageId],
    queryFn: () => api.getSymbolContext(repoId, lineageId),
  });
  const counts = useMemo(() => {
    const events = lineage.data?.events ?? [];
    return {
      renamed: events.filter((item) => item.event_type.includes("renamed"))
        .length,
      moved: events.filter((item) => item.event_type.includes("moved")).length,
    };
  }, [lineage.data]);

  if (repository.isError)
    return (
      <QueryError error={repository.error} retry={() => repository.refetch()} />
    );
  if (lineage.isError)
    return <QueryError error={lineage.error} retry={() => lineage.refetch()} />;
  if (!repository.data || !lineage.data)
    return <p role="status">Loading symbol history…</p>;
  const item = lineage.data;
  return (
    <>
      <p className="mono eyebrow">SYMBOL TIME TRAVEL</p>
      <h1 className="repo-title">{repository.data.full_name}</h1>
      <RepositoryNav repoId={repoId} active="History" />
      <Link className="back-link" href={`/repos/${repoId}/history`}>
        ← Repository timeline
      </Link>
      <header className="lineage-header">
        <div>
          <span className="badge">{item.symbol_kind}</span>
          <h1>
            {item.current_qualified_name ||
              item.current_name ||
              "Deleted symbol"}
          </h1>
          <p className="mono">
            {item.current_file_path || item.file_paths.at(-1)}
          </p>
        </div>
        <strong
          className={item.is_deleted ? "status-deleted" : "status-active"}
        >
          {item.is_deleted ? "Deleted" : "Active"}
        </strong>
      </header>
      <div className="actions">
        <Link
          className="action-link"
          href={`/repos/${repoId}/ask?lineage_id=${lineageId}&file_path=${encodeURIComponent(item.current_file_path || item.file_paths.at(-1) || "")}&question=${encodeURIComponent(`Why does ${item.current_qualified_name || item.current_name || "this symbol"} exist?`)}`}
        >
          Ask Why
        </Link>
        <Link
          className="action-link"
          href={`/repos/${repoId}/ask?lineage_id=${lineageId}&question=${encodeURIComponent(`Analyze the impact of ${item.current_qualified_name || item.current_name || "this symbol"}`)}`}
        >
          Explain Impact
        </Link>
        <Link
          className="action-link"
          href={`/repos/${repoId}/archaeology?lineage_id=${lineageId}`}
        >
          Archaeology Dossier
        </Link>
      </div>
      <section className="history-summary">
        <div>
          <small>Introduced</small>
          <strong>
            {item.introduced_commit
              ? dateLabel(item.introduced_commit.committed_at)
              : "Unknown"}
          </strong>
        </div>
        <div>
          <small>Introduced by</small>
          <strong>{item.introduced_commit?.author_name || "Unknown"}</strong>
        </div>
        <div>
          <small>Total events</small>
          <strong>{item.events.length}</strong>
        </div>
        <div>
          <small>Renamed / moved</small>
          <strong>
            {counts.renamed} / {counts.moved}
          </strong>
        </div>
      </section>
      <div className="lineage-layout">
        <ol className="symbol-timeline">
          {item.events.map((event) => {
            const versionId = event.new_version_id || event.previous_version_id;
            const development = context.data?.events.find(
              (candidate) => candidate.event.id === event.id,
            );
            return (
              <li key={event.id}>
                <span
                  className={`event-dot event-${event.event_type}`}
                  aria-hidden="true"
                />
                <button
                  className={selectedVersion === versionId ? "selected" : ""}
                  onClick={() => versionId && setSelected(versionId)}
                  disabled={!versionId}
                >
                  <strong>{event.event_type.replaceAll("_", " ")}</strong>
                  <span>{event.deterministic_label}</span>
                  <span className="mono">{event.commit.short_sha}</span>
                  <small>
                    {event.commit.message.split("\n")[0]} ·{" "}
                    {dateLabel(event.commit.committed_at)}
                  </small>
                </button>
                {development &&
                  (development.pull_requests.length > 0 ||
                    development.issues.length > 0) && (
                    <div className="timeline-context">
                      {development.pull_requests.map((pull) => (
                        <Link
                          key={pull.id}
                          href={`/repos/${repoId}/pull-requests/${pull.number}`}
                        >
                          PR #{pull.number}: {pull.title}
                        </Link>
                      ))}
                      {development.issues.map((reference) =>
                        reference.issue ? (
                          <Link
                            key={`${reference.number}-${reference.reference_type}`}
                            href={`/repos/${repoId}/issues/${reference.number}`}
                          >
                            Issue #{reference.number}: {reference.issue.title}
                          </Link>
                        ) : null,
                      )}
                    </div>
                  )}
              </li>
            );
          })}
        </ol>
        <section className="historical-source-panel">
          {source.isPending ? (
            <p role="status">Loading historical source…</p>
          ) : source.isError ? (
            <QueryError error={source.error} retry={() => source.refetch()} />
          ) : source.data ? (
            <>
              <div className="historical-banner">
                <strong>Historical snapshot</strong>
                <span>
                  {source.data.commit_sha.slice(0, 12)} ·{" "}
                  {source.data.file_path}
                </span>
                {selectedDetails && (
                  <span>
                    {selectedDetails.name}
                    {selectedDetails.signature
                      ? ` · ${selectedDetails.signature}`
                      : ""}{" "}
                    · {selectedDetails.commit.author_name} ·{" "}
                    {dateLabel(selectedDetails.commit.committed_at)}
                  </span>
                )}
              </div>
              {selectedDetails && selectedDetails.match_confidence < 0.95 && (
                <details className="lineage-confidence">
                  <summary>Possible heuristic lineage match</summary>
                  <p>
                    Match confidence:{" "}
                    {(selectedDetails.match_confidence * 100).toFixed(0)}%
                  </p>
                  {selectedDetails.matching_metadata && (
                    <pre>
                      {JSON.stringify(
                        selectedDetails.matching_metadata,
                        null,
                        2,
                      )}
                    </pre>
                  )}
                </details>
              )}
              <div className="source-code historical-code" tabIndex={0}>
                {sourceLines(source.data.source).map((line, index) => (
                  <div className="source-line" key={index}>
                    <span>{source.data!.start_line + index}</span>
                    <code>{line || " "}</code>
                  </div>
                ))}
              </div>
              <button onClick={() => setCompare(!compare)} disabled={!previous}>
                {compare ? "Hide comparison" : "Compare with previous version"}
              </button>
              {compare &&
                (comparison.isPending ? (
                  <p role="status">Comparing versions…</p>
                ) : comparison.isError ? (
                  <p role="alert">{errorMessage(comparison.error)}</p>
                ) : comparison.data ? (
                  <div className="version-comparison">
                    <dl className="comparison-metadata">
                      <div>
                        <dt>Name</dt>
                        <dd>
                          {comparison.data.old_name} →{" "}
                          {comparison.data.new_name}
                        </dd>
                      </div>
                      <div>
                        <dt>File</dt>
                        <dd>
                          {comparison.data.old_path} →{" "}
                          {comparison.data.new_path}
                        </dd>
                      </div>
                      <div>
                        <dt>Signature</dt>
                        <dd>
                          {comparison.data.old_signature || "—"} →{" "}
                          {comparison.data.new_signature || "—"}
                        </dd>
                      </div>
                    </dl>
                    {comparison.data.truncated && (
                      <p className="notice">Diff truncated.</p>
                    )}
                    <pre className="diff-view">
                      {comparison.data.diff || "No textual change."}
                    </pre>
                  </div>
                ) : null)}
            </>
          ) : null}
        </section>
      </div>
      {context.isError && (
        <p className="muted">
          GitHub context unavailable. Sync it from the Pull Requests or Issues
          page.
        </p>
      )}
    </>
  );
}
