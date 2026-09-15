"use client";
import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, Github, LockKeyhole } from "lucide-react";
import { useCreateRepository } from "@/hooks/use-repository";
import { errorMessage } from "@/lib/api";
import { submissionPath, validRepositoryUrl } from "@/lib/repository";

export function RepositoryForm() {
  const [url, setUrl] = useState("");
  const [validation, setValidation] = useState<string | null>(null);
  const mutation = useCreateRepository();
  const router = useRouter();
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (mutation.isPending) return;
    if (!validRepositoryUrl(url)) {
      setValidation(
        "Enter a public GitHub URL: https://github.com/owner/repository.",
      );
      return;
    }
    setValidation(null);
    mutation.mutate(url.trim(), {
      onSuccess: (result) => router.push(submissionPath(result)),
    });
  }
  const error =
    validation || (mutation.isError ? errorMessage(mutation.error) : null);
  return (
    <section className="repository-panel" aria-labelledby="repository-heading">
      <div className="panel-heading">
        <h2 id="repository-heading">Start with a repository</h2>
        <span className="mono badge">PUBLIC GITHUB</span>
      </div>
      <form onSubmit={submit} noValidate>
        <label htmlFor="repository-url">Repository URL</label>
        <div className="input-row">
          <div className="input-wrap">
            <Github size={19} aria-hidden="true" />
            <input
              id="repository-url"
              type="url"
              value={url}
              onChange={(event) => {
                setUrl(event.target.value);
                setValidation(null);
                mutation.reset();
              }}
              disabled={mutation.isPending}
              placeholder="https://github.com/owner/repository"
              autoComplete="off"
              spellCheck={false}
              maxLength={2048}
              aria-invalid={Boolean(error)}
              aria-describedby={error ? "submission-error" : "phase-note"}
            />
          </div>
          <button type="submit" disabled={mutation.isPending}>
            {mutation.isPending
              ? "Verifying repository…"
              : "Analyze Repository"}
            <ArrowRight size={16} aria-hidden="true" />
          </button>
        </div>
        {error && (
          <p id="submission-error" className="error-message" role="alert">
            {error}
          </p>
        )}
        <p id="phase-note" className="phase-note">
          {mutation.isPending
            ? "Checking public access. Cloning will run in the background."
            : "Explore commits, changed files, renames, and diffs on the default branch."}
        </p>
      </form>
      <div className="panel-footer">
        <LockKeyhole size={13} aria-hidden="true" />
        <span>Public repositories. Read-only analysis. Runs locally.</span>
      </div>
    </section>
  );
}
