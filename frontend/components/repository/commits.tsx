"use client";
import Link from "next/link";
import { useState } from "react";
import { useCommits } from "@/hooks/use-repository";
import { dateLabel } from "@/lib/repository";
import { QueryError } from "./workspace";
import { RepositoryNav } from "./repository-nav";

export function CommitList({ repoId }: { repoId: string }) {
  const [page, setPage] = useState(1);
  const query = useCommits(repoId, page);
  return (
    <>
      <Link className="back-link" href={`/repos/${repoId}`}>
        ← Repository dashboard
      </Link>
      <p className="mono eyebrow">DEFAULT BRANCH</p>
      <h1 className="repo-title">Commit history</h1>
      <RepositoryNav repoId={repoId} active="Commits" />
      {query.isError ? (
        <QueryError error={query.error} retry={() => query.refetch()} />
      ) : query.isPending ? (
        <p role="status">Loading commits…</p>
      ) : (
        <>
          <p className="muted">
            {query.data.total.toLocaleString()} commits · newest commit date
            first
          </p>
          <div className="commit-list">
            {query.data.items.length ? (
              query.data.items.map((commit) => (
                <Link
                  className="commit-row"
                  href={`/repos/${repoId}/commits/${commit.sha}`}
                  key={commit.sha}
                >
                  <code>{commit.short_sha}</code>
                  <div className="commit-description">
                    <h2>
                      {commit.message.split("\n")[0] || "(no commit message)"}
                    </h2>
                    <p>
                      {commit.author_name || "Unknown author"} ·{" "}
                      {dateLabel(commit.committed_at)}
                    </p>
                  </div>
                  {commit.is_merge_commit && (
                    <span className="badge">Merge</span>
                  )}
                  <span className="commit-numbers">
                    {commit.files_changed} files{" "}
                    <span className="addition">+{commit.insertions}</span>{" "}
                    <span className="deletion">−{commit.deletions}</span>
                  </span>
                </Link>
              ))
            ) : (
              <p className="history-panel">No commits on this page.</p>
            )}
          </div>
          <nav className="pagination" aria-label="Commit pagination">
            <button disabled={page === 1} onClick={() => setPage(page - 1)}>
              Previous
            </button>
            <span>
              Page {page} of{" "}
              {Math.max(1, Math.ceil(query.data.total / query.data.page_size))}
            </span>
            <button
              disabled={page * query.data.page_size >= query.data.total}
              onClick={() => setPage(page + 1)}
            >
              Next
            </button>
          </nav>
        </>
      )}
    </>
  );
}
