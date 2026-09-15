import type { Submission } from "@/types/repository";

export function submissionPath(result: Submission): string {
  const base = `/repos/${encodeURIComponent(result.repository_id)}`;
  return result.status === "ready" || !result.job_id
    ? base
    : `${base}/indexing?job=${encodeURIComponent(result.job_id)}`;
}
export function validRepositoryUrl(value: string): boolean {
  return /^https:\/\/github\.com\/[a-z0-9](?:[a-z0-9-]{0,37}[a-z0-9])?\/[a-z0-9_.-]{1,104}\/?$/i.test(
    value.trim(),
  );
}
export function dateLabel(value: string | null): string {
  if (!value) return "Not indexed";
  return new Date(value).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}
