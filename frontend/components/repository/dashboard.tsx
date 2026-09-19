"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  useRefreshRepository,
  useCodeStats,
  useRepository,
  useRepositoryStats,
  useAIReindex,
  useAIStatus,
  useRepositoryAIStatus,
} from "@/hooks/use-repository";
import { api, errorMessage } from "@/lib/api";
import { dateLabel, submissionPath } from "@/lib/repository";
import { QueryError } from "./workspace";
import { RepositoryNav } from "./repository-nav";

export function Dashboard({ repoId }: { repoId: string }) {
  const repository = useRepository(repoId);
  const ready = repository.data?.status === "ready";
  const stats = useRepositoryStats(repoId, ready);
  const codeStats = useCodeStats(repoId, ready);
  const tags = useQuery({
    queryKey: ["tags", repoId],
    queryFn: () => api.getTags(repoId),
    enabled: ready,
  });
  const refresh = useRefreshRepository();
  const ai = useAIStatus();
  const aiIndex = useRepositoryAIStatus(repoId);
  const aiReindex = useAIReindex();
  const router = useRouter();
  if (repository.isError)
    return (
      <QueryError error={repository.error} retry={() => repository.refetch()} />
    );
  if (!repository.data) return <p role="status">Loading repository…</p>;
  const repo = repository.data;
  const embeddingReady = Boolean(
    ai.data?.available && ai.data.embedding_model_available,
  );
  const modelsReady = Boolean(embeddingReady && ai.data?.llm_model_available);
  const indexReady =
    aiIndex.data?.status === "ready" && !aiIndex.data.index_stale;
  return (
    <>
      <Link href="/" className="back-link">
        ← Analyze another repository
      </Link>
      <p className="mono eyebrow">PUBLIC GITHUB REPOSITORY</p>
      <h1 className="repo-title">{repo.full_name}</h1>
      <RepositoryNav repoId={repoId} active="Overview" />
      <div className="actions">
        <a href={repo.url} target="_blank" rel="noreferrer">
          View on GitHub ↗
        </a>
        {ready && (
          <Link className="action-link" href={`/repos/${repoId}/commits`}>
            Browse Commits
          </Link>
        )}
        <button
          disabled={refresh.isPending}
          onClick={() =>
            refresh.mutate(repoId, {
              onSuccess: (result) => router.push(submissionPath(result)),
            })
          }
        >
          {refresh.isPending
            ? "Verifying…"
            : repo.status === "failed"
              ? "Retry Analysis"
              : "Refresh Repository"}
        </button>
      </div>
      {refresh.isError && (
        <p role="alert" className="error-message">
          {errorMessage(refresh.error)}
        </p>
      )}
      {!ready && (
        <section className="history-panel">
          <p>Status: {repo.status}</p>
          {repo.indexing_error && <p role="alert">{repo.indexing_error}</p>}
          {repo.active_job_id && (
            <Link href={`/repos/${repoId}/indexing?job=${repo.active_job_id}`}>
              View indexing progress
            </Link>
          )}
        </section>
      )}
      <dl className="metadata-grid">
        <div>
          <dt>Default branch</dt>
          <dd className="mono">{repo.default_branch || "No commits yet"}</dd>
        </div>
        <div>
          <dt>Commits</dt>
          <dd>{repo.commit_count.toLocaleString()}</dd>
        </div>
        <div>
          <dt>Contributors</dt>
          <dd>{stats.data?.contributors ?? "—"}</dd>
        </div>
        <div>
          <dt>Latest indexed commit</dt>
          <dd className="mono">{repo.head_sha?.slice(0, 12) || "—"}</dd>
        </div>
        <div>
          <dt>Indexed</dt>
          <dd>{dateLabel(repo.indexed_at)}</dd>
        </div>
        <div>
          <dt>First commit</dt>
          <dd>
            {stats.data?.first_commit_at
              ? dateLabel(stats.data.first_commit_at)
              : "—"}
          </dd>
        </div>
        <div>
          <dt>Latest commit</dt>
          <dd>
            {stats.data?.latest_commit_at
              ? dateLabel(stats.data.latest_commit_at)
              : "—"}
          </dd>
        </div>
        <div>
          <dt>Historical paths</dt>
          <dd>{stats.data?.historical_paths ?? "—"}</dd>
        </div>
      </dl>
      {ready && (
        <section className="history-panel">
          <div className="section-heading">
            <h2>Current code snapshot</h2>
            <Link href={`/repos/${repoId}/code`}>Open Code Explorer →</Link>
          </div>
          {codeStats.isError ? (
            <QueryError
              error={codeStats.error}
              retry={() => codeStats.refetch()}
            />
          ) : codeStats.isPending ? (
            <p role="status">Loading code statistics…</p>
          ) : codeStats.data ? (
            <>
              <dl className="code-stat-grid">
                <div>
                  <dt>Files</dt>
                  <dd>{codeStats.data.total_files.toLocaleString()}</dd>
                </div>
                <div>
                  <dt>Lines</dt>
                  <dd>{codeStats.data.total_lines.toLocaleString()}</dd>
                </div>
                <div>
                  <dt>Functions</dt>
                  <dd>{codeStats.data.functions.toLocaleString()}</dd>
                </div>
                <div>
                  <dt>Classes</dt>
                  <dd>{codeStats.data.classes.toLocaleString()}</dd>
                </div>
                <div>
                  <dt>Methods</dt>
                  <dd>{codeStats.data.methods.toLocaleString()}</dd>
                </div>
              </dl>
              <div className="language-bars">
                {codeStats.data.languages.map((language) => (
                  <div key={language.language}>
                    <span>{language.language}</span>
                    <div>
                      <i style={{ width: `${language.percentage}%` }} />
                    </div>
                    <strong>{language.percentage}%</strong>
                  </div>
                ))}
              </div>
            </>
          ) : null}
        </section>
      )}
      {repo.history_rewritten && (
        <p className="notice">
          The previous head was not an ancestor of the refreshed head. The index
          was reconciled to the current default branch.
        </p>
      )}
      {ready && (
        <section className="history-panel architecture-header">
          <div>
            <h2>Local AI evidence index</h2>
            <p className="muted">
              {ai.isError
                ? `Could not check Ollama status: ${errorMessage(ai.error)}`
                : aiIndex.isError
                  ? `Could not load the repository AI index: ${errorMessage(aiIndex.error)}`
                  : !ai.data?.available && !ai.isPending
                    ? "Ollama server unavailable. Check the configured local URL."
                    : ai.data?.available && !ai.data.embedding_model_available
                      ? `Embedding model ${ai.data.embedding_model || "(not configured)"} is not installed.`
                      : ai.data?.available && !ai.data.llm_model_available
                        ? `LLM model ${ai.data.llm_model || "(not configured)"} is not installed.`
                        : aiIndex.data?.status === "ready" &&
                            !aiIndex.data.index_stale
                          ? `${aiIndex.data.embedded_documents.toLocaleString()} evidence documents are ready for grounded questions.`
                          : aiIndex.data?.status === "failed"
                            ? "AI indexing failed. Review the error and retry."
                            : ["queued", "indexing"].includes(
                                  aiIndex.data?.status ?? "",
                                )
                              ? "AI indexing is in progress."
                              : aiIndex.data?.status === "not_indexed"
                                ? "Repository AI index not built. Build embeddings to ask grounded questions."
                                : "Build embeddings to ask questions grounded in repository history."}
            </p>
            {aiIndex.data?.error && (
              <p className="error-message">{aiIndex.data.error}</p>
            )}
          </div>
          {indexReady ? (
            modelsReady && (
              <Link className="action-link" href={`/repos/${repoId}/ask`}>
                Ask Codebase Time Machine
              </Link>
            )
          ) : (
            <button
              disabled={
                !embeddingReady ||
                aiIndex.isError ||
                aiReindex.isPending ||
                ["queued", "indexing"].includes(aiIndex.data?.status ?? "")
              }
              onClick={() => aiReindex.mutate(repoId)}
            >
              {aiReindex.isPending ? "Starting…" : "Build AI index"}
            </button>
          )}
        </section>
      )}
      {stats.isError && (
        <QueryError error={stats.error} retry={() => stats.refetch()} />
      )}
      {ready && (
        <section className="history-panel">
          <h2>Tags</h2>
          {tags.isError ? (
            <QueryError error={tags.error} retry={() => tags.refetch()} />
          ) : tags.isPending ? (
            <p>Loading tags…</p>
          ) : tags.data?.length ? (
            <ul className="tag-list">
              {tags.data.map((tag) => (
                <li key={tag.name}>
                  <span className="mono">{tag.name}</span>
                  <code>{tag.target_sha.slice(0, 12)}</code>
                  <span className="muted">
                    {tag.annotated ? "annotated" : "lightweight"}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">No tags found.</p>
          )}
        </section>
      )}
    </>
  );
}
