"use client";

import Link from "next/link";
import { useState } from "react";
import {
  useGitHubStatus,
  useGitHubSync,
  useIssue,
  useIssues,
  usePullRequest,
  usePullRequests,
  useRepository,
} from "@/hooks/use-repository";
import { errorMessage } from "@/lib/api";
import { dateLabel } from "@/lib/repository";
import type {
  AffectedSymbol,
  GitHubComment,
  GitHubLabel,
} from "@/types/repository";
import { QueryError } from "./workspace";
import { RepositoryNav } from "./repository-nav";
import { SafeMarkdown } from "./safe-markdown";

function Labels({ items }: { items: GitHubLabel[] }) {
  return (
    <span className="github-labels">
      {items.map((label) => (
        <span
          className="github-label"
          key={label.name}
          title={label.description ?? undefined}
          style={{ borderColor: label.color ? `#${label.color}` : undefined }}
        >
          {label.name}
        </span>
      ))}
    </span>
  );
}

function Comments({ items, empty }: { items: GitHubComment[]; empty: string }) {
  if (!items.length) return <p className="muted">{empty}</p>;
  return (
    <ol className="github-comments">
      {items.map((comment) => (
        <li key={comment.id}>
          <div className="github-comment-header">
            <strong>@{comment.author_login || "ghost"}</strong>
            <span>{dateLabel(comment.created_at)}</span>
            {comment.path && (
              <code>
                {comment.path}
                {comment.line ? `:${comment.line}` : ""}
              </code>
            )}
            <a href={comment.html_url} target="_blank" rel="noreferrer">
              View on GitHub ↗
            </a>
          </div>
          {comment.diff_hunk && (
            <pre className="review-hunk">{comment.diff_hunk}</pre>
          )}
          <SafeMarkdown value={comment.body} />
        </li>
      ))}
    </ol>
  );
}

function AffectedSymbols({
  repoId,
  items,
}: {
  repoId: string;
  items: AffectedSymbol[];
}) {
  if (!items.length)
    return <p className="muted">No affected symbols were derivable.</p>;
  return (
    <ul className="context-list">
      {items.map((symbol) => (
        <li
          key={`${symbol.lineage_id}-${symbol.commit_sha}-${symbol.event_type}`}
        >
          <span className="badge">
            {symbol.event_type.replaceAll("_", " ")}
          </span>
          <Link href={`/repos/${repoId}/history/symbols/${symbol.lineage_id}`}>
            {symbol.name}
          </Link>
          <code>{symbol.file_path}</code>
        </li>
      ))}
    </ul>
  );
}

function ContextHeader({ repoId, active }: { repoId: string; active: string }) {
  const repository = useRepository(repoId);
  if (repository.isError)
    return (
      <QueryError error={repository.error} retry={() => repository.refetch()} />
    );
  if (!repository.data) return <p role="status">Loading repository…</p>;
  return (
    <>
      <p className="mono eyebrow">GITHUB DEVELOPMENT CONTEXT</p>
      <h1 className="repo-title">{repository.data.full_name}</h1>
      <RepositoryNav repoId={repoId} active={active} />
    </>
  );
}

function GitHubAvailability({ repoId }: { repoId: string }) {
  const status = useGitHubStatus(repoId);
  const sync = useGitHubSync();
  if (status.isPending)
    return <p role="status">Loading GitHub context status…</p>;
  if (status.isError)
    return <QueryError error={status.error} retry={() => status.refetch()} />;
  const ready = ["ready", "limited"].includes(status.data?.status ?? "");
  if (ready) {
    return (
      <div className="github-status-strip">
        <span>{status.data?.pull_requests_indexed} pull requests</span>
        <span>{status.data?.issues_indexed} issues</span>
        <span>
          {(status.data?.comments_indexed ?? 0) +
            (status.data?.review_comments_indexed ?? 0)}{" "}
          comments
        </span>
        <span>Synced {dateLabel(status.data?.last_synced_at ?? null)}</span>
        <button
          onClick={() =>
            sync.mutate(repoId, { onSuccess: () => status.refetch() })
          }
          disabled={sync.isPending}
        >
          {sync.isPending ? "Starting…" : "Refresh GitHub context"}
        </button>
        {status.data?.github_index_limited && (
          <span className="notice">Configured indexing limit reached.</span>
        )}
      </div>
    );
  }
  const rateLimited = status.data?.status === "rate_limited";
  return (
    <section className="history-panel history-empty">
      <h2>
        {rateLimited
          ? "GitHub API rate limit reached"
          : "GitHub context unavailable"}
      </h2>
      <p
        className={status.data?.sync_error ? "error-message" : "muted"}
        role="status"
      >
        {status.data?.sync_error ||
          "Sync public pull requests, issues, labels, and discussions from GitHub."}
      </p>
      {status.data?.progress != null && (
        <div
          className="history-progress"
          aria-label="GitHub synchronization progress"
        >
          <span style={{ width: `${status.data.progress}%` }} />
        </div>
      )}
      {!["queued", "syncing"].includes(status.data?.status ?? "") && (
        <button
          onClick={() =>
            sync.mutate(repoId, { onSuccess: () => status.refetch() })
          }
          disabled={sync.isPending}
        >
          {sync.isPending ? "Starting…" : "Sync GitHub context"}
        </button>
      )}
      {sync.isError && (
        <p className="error-message" role="alert">
          {errorMessage(sync.error)}
        </p>
      )}
    </section>
  );
}

function Filters({
  state,
  setState,
  search,
  setSearch,
  author,
  setAuthor,
  label,
  setLabel,
}: {
  state: string;
  setState: (value: string) => void;
  search: string;
  setSearch: (value: string) => void;
  author: string;
  setAuthor: (value: string) => void;
  label: string;
  setLabel: (value: string) => void;
}) {
  return (
    <div className="github-filters">
      <label>
        State
        <select
          value={state}
          onChange={(event) => setState(event.target.value)}
        >
          <option value="all">All</option>
          <option value="open">Open</option>
          <option value="closed">Closed</option>
        </select>
      </label>
      <label>
        Search
        <input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
      </label>
      <label>
        Author
        <input
          value={author}
          onChange={(event) => setAuthor(event.target.value)}
        />
      </label>
      <label>
        Label
        <input
          value={label}
          onChange={(event) => setLabel(event.target.value)}
        />
      </label>
    </div>
  );
}

export function PullRequestList({ repoId }: { repoId: string }) {
  const status = useGitHubStatus(repoId);
  const [state, setState] = useState("all");
  const [search, setSearch] = useState("");
  const [author, setAuthor] = useState("");
  const [label, setLabel] = useState("");
  const [page, setPage] = useState(1);
  const ready = ["ready", "limited"].includes(status.data?.status ?? "");
  const query = usePullRequests(
    repoId,
    {
      state,
      search: search.trim(),
      author: author.trim(),
      label: label.trim(),
      page,
    },
    ready,
  );
  const update = (setter: (value: string) => void) => (value: string) => {
    setter(value);
    setPage(1);
  };
  return (
    <>
      <ContextHeader repoId={repoId} active="Pull Requests" />
      <GitHubAvailability repoId={repoId} />
      {ready && (
        <>
          <Filters
            state={state}
            setState={update(setState)}
            search={search}
            setSearch={update(setSearch)}
            author={author}
            setAuthor={update(setAuthor)}
            label={label}
            setLabel={update(setLabel)}
          />
          {query.isPending ? (
            <p role="status">Loading pull requests…</p>
          ) : query.isError ? (
            <QueryError error={query.error} retry={() => query.refetch()} />
          ) : query.data?.items.length ? (
            <ol className="github-item-list">
              {query.data.items.map((item) => (
                <li key={item.id}>
                  <div>
                    <span
                      className={`github-state ${item.merged ? "merged" : item.state}`}
                    >
                      {item.draft
                        ? "Draft"
                        : item.merged
                          ? "Merged"
                          : item.state}
                    </span>
                    <h2>
                      <Link
                        href={`/repos/${repoId}/pull-requests/${item.number}`}
                      >
                        #{item.number} {item.title}
                      </Link>
                    </h2>
                    <p>
                      @{item.author_login || "ghost"} ·{" "}
                      {dateLabel(item.created_at)} · {item.commits_count}{" "}
                      commits
                    </p>
                  </div>
                  <Labels items={item.labels} />
                </li>
              ))}
            </ol>
          ) : (
            <section className="history-panel">
              <p>No pull requests match these filters.</p>
            </section>
          )}
          {query.data && query.data.total > query.data.page_size && (
            <nav className="pagination" aria-label="Pull request pages">
              <button disabled={page === 1} onClick={() => setPage(page - 1)}>
                Previous
              </button>
              <span>
                Page {page} of{" "}
                {Math.ceil(query.data.total / query.data.page_size)}
              </span>
              <button
                disabled={page * query.data.page_size >= query.data.total}
                onClick={() => setPage(page + 1)}
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

export function IssueList({ repoId }: { repoId: string }) {
  const status = useGitHubStatus(repoId);
  const [state, setState] = useState("open");
  const [search, setSearch] = useState("");
  const [author, setAuthor] = useState("");
  const [label, setLabel] = useState("");
  const [page, setPage] = useState(1);
  const ready = ["ready", "limited"].includes(status.data?.status ?? "");
  const query = useIssues(
    repoId,
    {
      state,
      search: search.trim(),
      author: author.trim(),
      label: label.trim(),
      page,
    },
    ready,
  );
  const update = (setter: (value: string) => void) => (value: string) => {
    setter(value);
    setPage(1);
  };
  return (
    <>
      <ContextHeader repoId={repoId} active="Issues" />
      <GitHubAvailability repoId={repoId} />
      {ready && (
        <>
          <Filters
            state={state}
            setState={update(setState)}
            search={search}
            setSearch={update(setSearch)}
            author={author}
            setAuthor={update(setAuthor)}
            label={label}
            setLabel={update(setLabel)}
          />
          {query.isPending ? (
            <p role="status">Loading issues…</p>
          ) : query.isError ? (
            <QueryError error={query.error} retry={() => query.refetch()} />
          ) : query.data?.items.length ? (
            <ol className="github-item-list">
              {query.data.items.map((item) => (
                <li key={item.id}>
                  <div>
                    <span className={`github-state ${item.state}`}>
                      {item.state}
                    </span>
                    <h2>
                      <Link href={`/repos/${repoId}/issues/${item.number}`}>
                        #{item.number} {item.title}
                      </Link>
                    </h2>
                    <p>
                      @{item.author_login || "ghost"} ·{" "}
                      {dateLabel(item.created_at)}
                    </p>
                  </div>
                  <Labels items={item.labels} />
                </li>
              ))}
            </ol>
          ) : (
            <section className="history-panel">
              <p>No issues match these filters.</p>
            </section>
          )}
          {query.data && query.data.total > query.data.page_size && (
            <nav className="pagination" aria-label="Issue pages">
              <button disabled={page === 1} onClick={() => setPage(page - 1)}>
                Previous
              </button>
              <span>
                Page {page} of{" "}
                {Math.ceil(query.data.total / query.data.page_size)}
              </span>
              <button
                disabled={page * query.data.page_size >= query.data.total}
                onClick={() => setPage(page + 1)}
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

export function PullRequestView({
  repoId,
  number,
}: {
  repoId: string;
  number: number;
}) {
  const query = usePullRequest(repoId, number);
  if (query.isError)
    return <QueryError error={query.error} retry={() => query.refetch()} />;
  if (!query.data) return <p role="status">Loading pull request…</p>;
  const item = query.data;
  return (
    <>
      <ContextHeader repoId={repoId} active="Pull Requests" />
      <Link className="back-link" href={`/repos/${repoId}/pull-requests`}>
        ← Pull requests
      </Link>
      <header className="github-detail-header">
        <span className={`github-state ${item.merged ? "merged" : item.state}`}>
          {item.draft ? "Draft" : item.merged ? "Merged" : item.state}
        </span>
        <h1>
          {item.title} <span>#{item.number}</span>
        </h1>
        <p>
          @{item.author_login || "ghost"} · {dateLabel(item.created_at)} ·{" "}
          {item.base_branch} ← {item.head_branch}
        </p>
        <Labels items={item.labels} />
      </header>
      <div className="actions">
        <Link
          className="action-link"
          href={`/repos/${repoId}/ask?pull_request_number=${item.number}&question=${encodeURIComponent("Explain the code impact of this pull request")}`}
        >
          Explain code impact
        </Link>
      </div>
      <section className="history-panel">
        <h2>Description</h2>
        <SafeMarkdown value={item.body} />
      </section>
      <section className="history-summary">
        <div>
          <small>Commits</small>
          <strong>{item.commits_count}</strong>
        </div>
        <div>
          <small>Files changed</small>
          <strong>{item.changed_files}</strong>
        </div>
        <div>
          <small>Additions</small>
          <strong>+{item.additions}</strong>
        </div>
        <div>
          <small>Deletions</small>
          <strong>−{item.deletions}</strong>
        </div>
      </section>
      <section className="history-panel">
        <h2>Related issues</h2>
        {item.linked_issues.length ? (
          <ul className="context-list">
            {item.linked_issues.map((reference) => (
              <li
                key={`${reference.owner}/${reference.repository}#${reference.number}-${reference.reference_type}`}
              >
                <span className="badge">{reference.reference_type}</span>
                {reference.issue ? (
                  <Link href={`/repos/${repoId}/issues/${reference.number}`}>
                    #{reference.number} {reference.issue.title}
                  </Link>
                ) : (
                  <span>
                    {reference.owner}/{reference.repository}#{reference.number}{" "}
                    (external)
                  </span>
                )}
                <small>
                  {Math.round(reference.confidence * 100)}% evidence confidence
                </small>
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted">No issue references were found.</p>
        )}
      </section>
      <section className="history-panel">
        <h2>Commits</h2>
        {item.commits.length ? (
          <ul className="context-list">
            {item.commits.map((commit) => (
              <li key={commit.sha}>
                <Link
                  className="mono"
                  href={`/repos/${repoId}/commits/${commit.sha}`}
                >
                  {commit.short_sha}
                </Link>
                <span>{commit.message.split("\n")[0]}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted">
            No commits overlap the indexed default branch.
          </p>
        )}
      </section>
      <section className="history-panel">
        <h2>Affected symbols</h2>
        <AffectedSymbols repoId={repoId} items={item.affected_symbols} />
      </section>
      <section className="history-panel">
        <h2>Conversation</h2>
        <Comments items={item.comments} empty="No conversation comments." />
      </section>
      <section className="history-panel">
        <h2>Review comments</h2>
        <Comments
          items={item.review_comments}
          empty="No code review comments."
        />
      </section>
    </>
  );
}

export function IssueView({
  repoId,
  number,
}: {
  repoId: string;
  number: number;
}) {
  const query = useIssue(repoId, number);
  if (query.isError)
    return <QueryError error={query.error} retry={() => query.refetch()} />;
  if (!query.data) return <p role="status">Loading issue…</p>;
  const item = query.data;
  return (
    <>
      <ContextHeader repoId={repoId} active="Issues" />
      <Link className="back-link" href={`/repos/${repoId}/issues`}>
        ← Issues
      </Link>
      <header className="github-detail-header">
        <span className={`github-state ${item.state}`}>{item.state}</span>
        <h1>
          {item.title} <span>#{item.number}</span>
        </h1>
        <p>
          @{item.author_login || "ghost"} · {dateLabel(item.created_at)}
          {item.milestone ? ` · Milestone: ${item.milestone}` : ""}
        </p>
        <Labels items={item.labels} />
      </header>
      <div className="actions">
        <Link
          className="action-link"
          href={`/repos/${repoId}/ask?issue_number=${item.number}&question=${encodeURIComponent("Show the code and changes related to this issue")}`}
        >
          Show related code
        </Link>
      </div>
      <section className="history-panel">
        <h2>Description</h2>
        <SafeMarkdown value={item.body} />
      </section>
      <section className="history-panel">
        <h2>Related pull requests</h2>
        {item.related_pull_requests.length ? (
          <ul className="context-list">
            {item.related_pull_requests.map(
              ({ pull_request: pull, relationship, confidence }) => (
                <li key={pull.id}>
                  <span className="badge">{relationship}</span>
                  <Link href={`/repos/${repoId}/pull-requests/${pull.number}`}>
                    #{pull.number} {pull.title}
                  </Link>
                  <small>
                    {Math.round(confidence * 100)}% evidence confidence
                  </small>
                </li>
              ),
            )}
          </ul>
        ) : (
          <p className="muted">No related pull requests.</p>
        )}
      </section>
      <section className="history-panel">
        <h2>Related commits</h2>
        {item.related_commits.length ? (
          <ul className="context-list">
            {item.related_commits.map((commit) => (
              <li key={commit.sha}>
                <Link
                  className="mono"
                  href={`/repos/${repoId}/commits/${commit.sha}`}
                >
                  {commit.short_sha}
                </Link>
                <span>{commit.message.split("\n")[0]}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted">No related indexed commits.</p>
        )}
      </section>
      <section className="history-panel">
        <h2>Affected symbols</h2>
        <AffectedSymbols repoId={repoId} items={item.affected_symbols} />
      </section>
      <section className="history-panel">
        <h2>Discussion</h2>
        <Comments items={item.comments} empty="No issue comments." />
      </section>
    </>
  );
}
