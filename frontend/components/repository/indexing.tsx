"use client";
import Link from "next/link";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import {
  invalidateRepository,
  useAnalysisJob,
  useRefreshRepository,
  useRepository,
} from "@/hooks/use-repository";
import { QueryError } from "./workspace";
import { errorMessage } from "@/lib/api";
import { submissionPath } from "@/lib/repository";

const stages = [
  "Repository validated",
  "Repository queued",
  "Repository cloned or fetched",
  "Git history read",
  "Commits and file changes stored",
  "Current source files parsed",
  "Ready",
];
const stageNumber: Record<string, number> = {
  queued: 1,
  validating_repository: 1,
  cloning_repository: 2,
  fetching_repository: 2,
  reading_git_history: 3,
  storing_commits: 4,
  finalizing_git_index: 5,
  enumerating_repository_files: 5,
  parsing_source_files: 5,
  resolving_imports: 5,
  saving_code_index: 5,
  completed: 7,
};

export function Indexing({
  repoId,
  jobId,
}: {
  repoId: string;
  jobId: string | null;
}) {
  const repository = useRepository(repoId);
  const job = useAnalysisJob(jobId || repository.data?.active_job_id || null);
  const refresh = useRefreshRepository();
  const router = useRouter();
  const client = useQueryClient();
  const belongs = job.data?.repository_id === repoId;
  useEffect(() => {
    if (belongs && job.data?.status === "completed") {
      void invalidateRepository(client, repoId);
      router.replace(`/repos/${encodeURIComponent(repoId)}`);
    }
  }, [belongs, job.data?.status, repoId, router, client]);
  if (repository.isError)
    return (
      <QueryError error={repository.error} retry={() => repository.refetch()} />
    );
  if (job.isError)
    return <QueryError error={job.error} retry={() => job.refetch()} />;
  if (job.data && !belongs)
    return <p role="alert">This job belongs to a different repository.</p>;
  if (!repository.data) return <p role="status">Loading repository…</p>;
  if (
    !jobId &&
    !repository.data.active_job_id &&
    repository.data.status === "ready"
  )
    return <Link href={`/repos/${repoId}`}>Open Repository</Link>;
  const failed =
    job.data?.status === "failed" ||
    (!jobId && repository.data.status === "failed");
  const current = stageNumber[job.data?.current_step || "queued"] ?? 1;
  function retry() {
    refresh.mutate(repoId, {
      onSuccess: (result) => {
        router.push(submissionPath(result));
        job.refetch();
        repository.refetch();
      },
    });
  }
  return (
    <>
      <Link className="back-link" href="/">
        ← All repositories
      </Link>
      <p className="mono eyebrow">BACKGROUND INDEXING</p>
      <h1 className="repo-title">{repository.data.full_name}</h1>
      <section className="history-panel">
        <h2>
          {failed
            ? "Analysis failed"
            : job.data?.status === "completed"
              ? "Repository ready"
              : "Building the Git history index"}
        </h2>
        {failed ? (
          <>
            <p role="alert" className="error-message">
              {job.data?.error_message ||
                repository.data.indexing_error ||
                "Indexing failed. Please retry."}
            </p>
            <div className="actions">
              <button onClick={retry} disabled={refresh.isPending}>
                Retry Analysis
              </button>
              <Link href="/">Back Home</Link>
            </div>
          </>
        ) : (
          <>
            <ol className="stages">
              {stages.map((label, index) => (
                <li
                  key={label}
                  className={
                    index < current
                      ? "done"
                      : index === current
                        ? "current"
                        : ""
                  }
                >
                  <span aria-hidden="true">
                    {index < current ? "✓" : index === current ? "•" : "○"}
                  </span>
                  {label}
                  {index === current && (
                    <span className="sr-only"> in progress</span>
                  )}
                </li>
              ))}
            </ol>
            {job.data?.progress != null && (
              <p className="muted">
                Repository analysis: {job.data.progress.toFixed(1)}%
              </p>
            )}
            <p className="muted">
              {job.data?.status === "queued"
                ? "Waiting for the configured background task executor."
                : "Progress reflects completed Git and static-analysis work. Repository code is never executed."}
            </p>
            {job.data?.status === "completed" ? (
              <Link href={`/repos/${repoId}`}>Open Repository</Link>
            ) : (
              <button disabled={refresh.isPending} onClick={retry}>
                Resume / requeue job
              </button>
            )}
          </>
        )}
        {refresh.isError && (
          <p role="alert" className="error-message">
            {errorMessage(refresh.error)}
          </p>
        )}
      </section>
    </>
  );
}
