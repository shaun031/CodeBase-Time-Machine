"use client";
import Link from "next/link";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useCommit } from "@/hooks/use-repository";
import { api } from "@/lib/api";
import { dateLabel } from "@/lib/repository";
import { QueryError } from "./workspace";

export function CommitView({ repoId, sha }: { repoId: string; sha: string }) {
  const query = useCommit(repoId, sha);
  const [showDiff, setShowDiff] = useState(false);
  const diff = useQuery({
    queryKey: ["diff", repoId, sha],
    queryFn: () => api.getDiff(repoId, sha),
    enabled: showDiff && query.isSuccess,
  });
  const symbolChanges = useQuery({
    queryKey: ["commit-symbol-events", repoId, sha],
    queryFn: () => api.getCommitEvents(repoId, sha),
  });
  const context = useQuery({
    queryKey: ["commit-context", repoId, sha],
    queryFn: () => api.getCommitContext(repoId, sha),
  });
  if (query.isError)
    return <QueryError error={query.error} retry={() => query.refetch()} />;
  if (!query.data) return <p role="status">Loading commit…</p>;
  const commit = query.data;
  return (
    <>
      <Link className="back-link" href={`/repos/${repoId}/commits`}>
        ← Commit history
      </Link>
      <p className="mono eyebrow">
        {commit.is_merge_commit ? "MERGE COMMIT · FIRST-PARENT DIFF" : "COMMIT"}
      </p>
      <h1 className="commit-heading">
        {commit.message.split("\n")[0] || "(no commit message)"}
      </h1>
      <code className="full-sha">{commit.sha}</code>
      <div className="actions">
        <Link
          className="action-link"
          href={`/repos/${repoId}/ask?commit_sha=${commit.sha}&question=${encodeURIComponent("Explain why this change was made")}`}
        >
          Explain this change
        </Link>
        <Link
          className="action-link"
          href={`/repos/${repoId}/investigate?commit=${commit.sha}`}
        >
          Investigate commit
        </Link>
      </div>
      <section className="history-panel">
        <h2>Commit message</h2>
        <pre className="commit-message">
          {commit.message || "(empty message)"}
        </pre>
        <dl className="metadata-grid">
          <div>
            <dt>Author</dt>
            <dd>{commit.author_name || "Unknown author"}</dd>
          </div>
          <div>
            <dt>Authored</dt>
            <dd>{dateLabel(commit.authored_at)}</dd>
          </div>
          <div>
            <dt>Committed</dt>
            <dd>{dateLabel(commit.committed_at)}</dd>
          </div>
          <div>
            <dt>Changes</dt>
            <dd>
              {commit.files_changed} files ·{" "}
              <span className="addition">+{commit.insertions}</span>{" "}
              <span className="deletion">−{commit.deletions}</span>
            </dd>
          </div>
        </dl>
        <h3>Parents (Git order)</h3>
        {commit.parents.length ? (
          <ul className="parent-list">
            {commit.parents.map((parent) => (
              <li key={parent}>
                <Link
                  className="mono"
                  href={`/repos/${repoId}/commits/${parent}`}
                >
                  {parent}
                </Link>
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted">Root commit — no parents.</p>
        )}
      </section>
      <section className="history-panel">
        <h2>Changed files</h2>
        <p className="muted">
          Binary changes have no line counts. Merge changes are measured against
          the first parent.
        </p>
        <ul className="changed-files">
          {commit.changes.map((change) => (
            <li key={change.id}>
              <span className="badge">{change.change_type}</span>
              <code>
                {change.change_type === "renamed" ||
                change.change_type === "copied"
                  ? `${change.old_path} → ${change.new_path}`
                  : change.new_path || change.old_path}
              </code>
              <span className="commit-numbers">
                {change.additions === null || change.deletions === null ? (
                  "Binary / no line counts"
                ) : (
                  <>
                    <span className="addition">+{change.additions}</span>{" "}
                    <span className="deletion">−{change.deletions}</span>
                  </>
                )}
              </span>
            </li>
          ))}
        </ul>
        {!commit.changes.length && <p>No file changes.</p>}
      </section>
      <section className="history-panel">
        <h2>Symbols changed in this commit</h2>
        {symbolChanges.isPending ? (
          <p role="status">Loading symbol changes…</p>
        ) : symbolChanges.isError ? (
          <p className="muted">
            Historical symbols are unavailable.{" "}
            <Link href={`/repos/${repoId}/history`}>Open History</Link> to build
            the index.
          </p>
        ) : symbolChanges.data?.length ? (
          <ul className="changed-symbols">
            {symbolChanges.data.map((event) => (
              <li key={event.id}>
                <span className="badge">
                  {event.event_type.replaceAll("_", " ")}
                </span>
                <Link
                  href={`/repos/${repoId}/history/symbols/${event.lineage_id}`}
                >
                  {event.deterministic_label}
                </Link>
                <code>{event.file_path}</code>
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted">No indexed symbol changes in this commit.</p>
        )}
      </section>
      <section className="history-panel">
        <h2>Development context</h2>
        {context.isPending ? (
          <p role="status">Loading GitHub development context…</p>
        ) : context.isError ? (
          <p className="muted">
            GitHub context unavailable.{" "}
            <Link href={`/repos/${repoId}/pull-requests`}>
              Open Pull Requests
            </Link>{" "}
            to start or retry synchronization.
          </p>
        ) : context.data.associated_pull_requests.length ||
          context.data.referenced_issues.length ? (
          <div className="development-context">
            {context.data.associated_pull_requests.length > 0 && (
              <div>
                <h3>Associated pull requests</h3>
                <ul className="context-list">
                  {context.data.associated_pull_requests.map((pull) => (
                    <li key={pull.id}>
                      <span className="badge">
                        {pull.merged ? "merged" : pull.state}
                      </span>
                      <Link
                        href={`/repos/${repoId}/pull-requests/${pull.number}`}
                      >
                        #{pull.number} {pull.title}
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {context.data.referenced_issues.length > 0 && (
              <div>
                <h3>Related issues</h3>
                <ul className="context-list">
                  {context.data.referenced_issues.map((reference) => (
                    <li
                      key={`${reference.owner}/${reference.repository}#${reference.number}-${reference.reference_type}`}
                    >
                      <span className="badge">{reference.reference_type}</span>
                      {reference.issue ? (
                        <Link
                          href={`/repos/${repoId}/issues/${reference.number}`}
                        >
                          #{reference.number} {reference.issue.title}
                        </Link>
                      ) : (
                        <span>
                          {reference.owner}/{reference.repository}#
                          {reference.number}
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        ) : (
          <p className="muted">
            No stored GitHub relationships support this commit.
          </p>
        )}
      </section>
      <section className="history-panel">
        <div className="panel-heading">
          <h2>Read-only diff</h2>
          <button onClick={() => setShowDiff(!showDiff)}>
            {showDiff ? "Hide diff" : "Load diff"}
          </button>
        </div>
        {showDiff &&
          (diff.isError ? (
            <QueryError error={diff.error} retry={() => diff.refetch()} />
          ) : !diff.data ? (
            <p role="status">Reading diff…</p>
          ) : (
            <>
              {diff.data.truncated && (
                <p className="notice" role="status">
                  Diff truncated at the configured byte limit. This is not the
                  complete diff.
                </p>
              )}
              <pre className="diff-view">
                {diff.data.content
                  ? diff.data.content.split("\n").map((line, index) => (
                      <span
                        key={index}
                        className={
                          line.startsWith("+")
                            ? "diff-add"
                            : line.startsWith("-")
                              ? "diff-delete"
                              : line.startsWith("@@")
                                ? "diff-context"
                                : ""
                        }
                      >
                        {line}
                        {"\n"}
                      </span>
                    ))
                  : "No textual diff."}
              </pre>
            </>
          ))}
      </section>
    </>
  );
}
