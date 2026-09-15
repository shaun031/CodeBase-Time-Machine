"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import {
  useAIReindex,
  useAIStatus,
  useAskRepository,
  useRepository,
  useRepositoryAIStatus,
} from "@/hooks/use-repository";
import { errorMessage } from "@/lib/api";
import type { AskContext, AskResponse } from "@/types/repository";
import { RepositoryNav } from "./repository-nav";
import { QueryError } from "./workspace";

type VisibleMessage =
  | { role: "user"; content: string }
  | { role: "assistant"; content: string; response: AskResponse };

const labels: Record<string, string> = {
  strong: "Supported by history",
  moderate: "Supported by repository evidence",
  weak: "Likely inference",
  insufficient: "Not enough evidence",
};

export function AskAssistant({
  repoId,
  initial,
}: {
  repoId: string;
  initial: Omit<AskContext, "question"> & { question?: string };
}) {
  const repository = useRepository(repoId);
  const system = useAIStatus();
  const index = useRepositoryAIStatus(repoId);
  const reindex = useAIReindex();
  const ask = useAskRepository();
  const [question, setQuestion] = useState(initial.question ?? "");
  const [messages, setMessages] = useState<VisibleMessage[]>([]);
  const indexReady = index.data?.status === "ready" && !index.data.index_stale;
  const ollamaReady = Boolean(
    system.data?.available || index.data?.ollama_available,
  );
  const modelsReady = Boolean(
    ollamaReady &&
    ((system.data?.llm_model_available &&
      system.data.embedding_model_available) ||
      indexReady),
  );

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const value = question.trim();
    if (!value || !indexReady) return;
    const conversation = messages.slice(-6).map((message) => ({
      role: message.role,
      content: message.content,
    }));
    ask.mutate(
      { id: repoId, body: { ...initial, question: value, conversation } },
      {
        onSuccess: (response) => {
          setMessages((current) => [
            ...current,
            { role: "user", content: value },
            { role: "assistant", content: response.answer, response },
          ]);
          setQuestion("");
        },
      },
    );
  };

  if (repository.isError)
    return (
      <QueryError error={repository.error} retry={() => repository.refetch()} />
    );
  if (!repository.data) return <p role="status">Loading repository…</p>;
  return (
    <>
      <p className="mono eyebrow">LOCAL SOFTWARE ARCHAEOLOGY</p>
      <h1 className="repo-title">{repository.data.full_name}</h1>
      <RepositoryNav repoId={repoId} active="Ask" />

      <section className="history-panel ai-status-panel">
        <div>
          <h2>Ask CodeChronicle</h2>
          <p className="muted">
            Answers use indexed Git, code, GitHub, history, and dependency
            evidence. Ollama runs locally and repository data stays on this
            machine.
          </p>
        </div>
        <div className="ai-index-summary">
          <span
            className={`ai-state ai-state-${index.data?.status ?? "loading"}`}
          >
            {index.isPending
              ? "Checking index…"
              : indexReady
                ? "AI index ready"
                : index.data?.status.replaceAll("_", " ")}
          </span>
          {index.data && (
            <small>
              {index.data.embedded_documents.toLocaleString()} /{" "}
              {index.data.documents.toLocaleString()} documents
              {index.data.embedding_dimension
                ? ` · ${index.data.embedding_dimension} dimensions`
                : ""}
            </small>
          )}
        </div>
      </section>

      {!modelsReady && !system.isPending && (
        <section className="ai-unavailable" role="status">
          <strong>AI features unavailable</strong>
          <p>
            {!system.data?.available
              ? "Ollama is not running. Start Ollama; this page checks again automatically."
              : "Install or configure both Ollama models; this page checks again automatically."}
          </p>
          <code>{system.data?.base_url_safe}</code>
        </section>
      )}

      {modelsReady && !indexReady && (
        <section className="history-panel ai-build-panel">
          <div>
            <h2>
              {index.data?.index_stale
                ? "AI index needs rebuilding"
                : "Build the AI index"}
            </h2>
            <p className="muted">
              Evidence is chunked and embedded in the background. Unchanged
              content reuses its existing vector.
            </p>
            {index.data?.progress != null && (
              <div
                className="history-progress"
                aria-label="AI indexing progress"
              >
                <span style={{ width: `${index.data.progress}%` }} />
              </div>
            )}
            {index.data?.current_step && <p>{index.data.current_step}</p>}
            {index.data?.error && (
              <p className="error-message">{index.data.error}</p>
            )}
          </div>
          {!["queued", "indexing"].includes(index.data?.status ?? "") && (
            <button
              disabled={reindex.isPending}
              onClick={() => reindex.mutate(repoId)}
            >
              {reindex.isPending
                ? "Starting…"
                : index.data?.index_stale
                  ? "Rebuild AI index"
                  : "Build AI index"}
            </button>
          )}
        </section>
      )}
      {reindex.isError && (
        <p className="error-message">{errorMessage(reindex.error)}</p>
      )}

      {(initial.lineage_id ||
        initial.commit_sha ||
        initial.pull_request_number ||
        initial.issue_number ||
        initial.file_path) && (
        <div className="ai-context-strip">
          <strong>Attached context</strong>
          {initial.lineage_id && (
            <span>symbol {initial.lineage_id.slice(0, 8)}</span>
          )}
          {initial.commit_sha && (
            <span>commit {initial.commit_sha.slice(0, 12)}</span>
          )}
          {initial.pull_request_number && (
            <span>PR #{initial.pull_request_number}</span>
          )}
          {initial.issue_number && <span>issue #{initial.issue_number}</span>}
          {initial.file_path && (
            <code>
              {initial.file_path}
              {initial.start_line
                ? `:${initial.start_line}${initial.end_line ? `-${initial.end_line}` : ""}`
                : ""}
            </code>
          )}
        </div>
      )}

      <div className="ai-conversation" aria-live="polite">
        {messages.length === 0 && (
          <div className="ai-empty">
            <h2>What do you want to understand?</h2>
            <p>
              Try “Why does this code exist?”, “Which change introduced it?”, or
              “What depends on this module?”
            </p>
          </div>
        )}
        {messages.map((message, indexNumber) => (
          <article
            className={`ai-message ai-message-${message.role}`}
            key={indexNumber}
          >
            <strong>{message.role === "user" ? "You" : "CodeChronicle"}</strong>
            <p>{message.content}</p>
            {message.role === "assistant" && (
              <>
                <div className="ai-answer-labels">
                  <span>{labels[message.response.evidence_sufficiency]}</span>
                  <span>Confidence: {message.response.confidence}</span>
                  {message.response.cached && <span>Cached</span>}
                </div>
                {message.response.limitations.length > 0 && (
                  <ul className="ai-limitations">
                    {message.response.limitations.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                )}
                <details className="ai-evidence" open>
                  <summary>
                    Sources / Evidence ({message.response.evidence.length})
                  </summary>
                  <ol>
                    {message.response.evidence.map((item) => (
                      <li key={item.id}>
                        <div>
                          <span className="badge">
                            {item.type.replaceAll("_", " ")}
                          </span>
                          {item.source_url ? (
                            <Link href={item.source_url}>{item.title}</Link>
                          ) : (
                            <strong>{item.title}</strong>
                          )}
                        </div>
                        <small>
                          {item.relationship} · {item.retrieval_reason}
                        </small>
                        <p>
                          {item.text.slice(0, 380)}
                          {item.text.length > 380 ? "…" : ""}
                        </p>
                      </li>
                    ))}
                  </ol>
                </details>
              </>
            )}
          </article>
        ))}
      </div>

      <form className="ai-question-form" onSubmit={submit}>
        <label htmlFor="ai-question">Repository question</label>
        <textarea
          id="ai-question"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="Why does this code exist?"
          rows={4}
          maxLength={2000}
          disabled={ask.isPending}
        />
        <div>
          <small>
            {question.length} / 2,000
            {!indexReady
              ? " · You can type now; sending unlocks when the AI index is ready."
              : ""}
          </small>
          <button disabled={!question.trim() || !indexReady || ask.isPending}>
            {ask.isPending ? "Retrieving evidence…" : "Ask with evidence"}
          </button>
        </div>
      </form>
      {ask.isError && (
        <p className="error-message" role="alert">
          {errorMessage(ask.error)}
        </p>
      )}
    </>
  );
}
