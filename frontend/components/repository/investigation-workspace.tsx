"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api, errorMessage } from "@/lib/api";
import type {
  AskResponse,
  BisectSession,
  InvestigationCandidate,
  LineHistoryResult,
  SZZResult,
} from "@/types/repository";
import { RepositoryNav } from "./repository-nav";

const tabs = [
  "Stack Trace",
  "Regression Range",
  "Commit Investigation",
  "Line Investigation",
  "SZZ Analysis",
] as const;
type Tab = (typeof tabs)[number];

function CandidateList({
  repoId,
  candidates,
  onFeedback,
}: {
  repoId: string;
  candidates: InvestigationCandidate[];
  onFeedback?: (
    commit: string,
    result: "relevant" | "not_relevant" | "unknown",
  ) => void;
}) {
  if (!candidates.length)
    return (
      <p className="muted">
        No candidate commits matched the available evidence.
      </p>
    );
  return (
    <ol className="investigation-candidates">
      {candidates.map((candidate) => (
        <li key={candidate.commit_sha}>
          <div>
            <span className="candidate-rank">#{candidate.rank}</span>
            <strong>{candidate.message || "Commit candidate"}</strong>
            <span className="badge">{candidate.confidence}</span>
          </div>
          <Link href={`/repos/${repoId}/commits/${candidate.commit_sha}`}>
            {candidate.commit_sha.slice(0, 12)}
          </Link>
          <meter min="0" max="1" value={candidate.score}>
            {candidate.score}
          </meter>
          <span>{Math.round(candidate.score * 100)} investigation points</span>
          <p>
            {candidate.reasons
              .map((reason) => reason.replaceAll("_", " "))
              .join(" · ")}
          </p>
          {!!candidate.files.length && (
            <code>{candidate.files.join(", ")}</code>
          )}
          {!!candidate.pull_requests?.length && (
            <p>
              {candidate.pull_requests.map((item) => (
                <a
                  key={item.number}
                  href={item.html_url}
                  target="_blank"
                  rel="noreferrer"
                >
                  PR #{item.number}: {item.title}
                </a>
              ))}
            </p>
          )}
          {!!candidate.issues?.length && (
            <p>
              {candidate.issues.map((item) => (
                <a
                  key={item.number}
                  href={item.html_url}
                  target="_blank"
                  rel="noreferrer"
                >
                  Issue #{item.number}: {item.title}
                </a>
              ))}
            </p>
          )}
          {onFeedback && (
            <div className="candidate-feedback" aria-label="Candidate feedback">
              <small>Your investigation note:</small>
              <button
                onClick={() => onFeedback(candidate.commit_sha, "relevant")}
              >
                Relevant
              </button>
              <button
                onClick={() => onFeedback(candidate.commit_sha, "not_relevant")}
              >
                Not relevant
              </button>
              <button
                onClick={() => onFeedback(candidate.commit_sha, "unknown")}
              >
                Unknown
              </button>
            </div>
          )}
        </li>
      ))}
    </ol>
  );
}

export function InvestigationWorkspace({
  repoId,
  initialCommit = "",
  initialFile = "",
  initialLine = "",
}: {
  repoId: string;
  initialCommit?: string;
  initialFile?: string;
  initialLine?: string;
}) {
  const [tab, setTab] = useState<Tab>(
    initialFile ? "Line Investigation" : "Stack Trace",
  );
  const [stackTrace, setStackTrace] = useState("");
  const [errorText, setErrorText] = useState("");
  const [good, setGood] = useState("");
  const [bad, setBad] = useState(initialCommit);
  const [fixCommit, setFixCommit] = useState(initialCommit);
  const [file, setFile] = useState(initialFile);
  const [line, setLine] = useState(initialLine);
  const [commitAtLine, setCommitAtLine] = useState(initialCommit);
  const [investigationId, setInvestigationId] = useState<string | null>(null);
  const [szz, setSzz] = useState<SZZResult | null>(null);
  const [lineResult, setLineResult] = useState<LineHistoryResult | null>(null);
  const [bisect, setBisect] = useState<BisectSession | null>(null);
  const [explanation, setExplanation] = useState<AskResponse | null>(null);

  const repository = useQuery({
    queryKey: ["repository", repoId],
    queryFn: () => api.getRepository(repoId),
  });
  const investigation = useQuery({
    queryKey: ["investigation", repoId, investigationId],
    queryFn: () => api.getInvestigation(repoId, investigationId!),
    enabled: Boolean(investigationId),
    refetchInterval: (query) =>
      ["pending", "analyzing"].includes(query.state.data?.status ?? "")
        ? 1000
        : false,
  });
  const create = useMutation({
    mutationFn: (payload: Parameters<typeof api.createInvestigation>[1]) =>
      api.createInvestigation(repoId, payload),
    onSuccess: (data) => {
      setInvestigationId(data.id);
      setSzz(null);
      setLineResult(null);
    },
  });
  const runSzz = useMutation({
    mutationFn: () =>
      api.investigateSZZ(repoId, {
        fix_commit_sha: fixCommit,
        file_path: file || undefined,
      }),
    onSuccess: (data) => setSzz(data),
  });
  const traceLine = useMutation({
    mutationFn: () =>
      api.getLineHistory(repoId, file, Number(line), commitAtLine || undefined),
    onSuccess: (data) => setLineResult(data),
  });
  const startBisect = useMutation({
    mutationFn: () => api.createBisect(repoId, good, bad),
    onSuccess: (data) => setBisect(data),
  });
  const classify = useMutation({
    mutationFn: (result: "good" | "bad" | "unknown") =>
      api.classifyBisect(
        repoId,
        bisect!.id,
        bisect!.current_candidate!,
        result,
      ),
    onSuccess: (data) => setBisect(data),
  });
  const explain = useMutation({
    mutationFn: () =>
      api.explainInvestigation(
        repoId,
        investigationId!,
        "Explain the strongest regression candidates and cite the deterministic evidence.",
      ),
    onSuccess: (data) => setExplanation(data),
  });
  const feedback = useMutation({
    mutationFn: ({
      commit,
      result,
    }: {
      commit: string;
      result: "relevant" | "not_relevant" | "unknown";
    }) =>
      api.saveInvestigationFeedback(repoId, investigationId!, commit, result),
  });

  const activeError =
    create.error ||
    runSzz.error ||
    traceLine.error ||
    startBisect.error ||
    classify.error ||
    explain.error ||
    feedback.error;
  const report = investigation.data?.result;

  function submitFailure(event: FormEvent) {
    event.preventDefault();
    create.mutate({
      stack_trace: stackTrace || undefined,
      error_message: errorText || undefined,
      known_good_commit: good || undefined,
      known_bad_commit: bad || undefined,
    });
  }

  return (
    <>
      <p className="mono eyebrow">DETERMINISTIC FAILURE INVESTIGATION</p>
      <h1 className="repo-title">
        {repository.data?.full_name ?? "Repository investigation"}
      </h1>
      <RepositoryNav repoId={repoId} active="Investigate" />
      <section className="history-panel investigation-intro">
        <h2>Bug and regression investigation</h2>
        <p>
          Paste failure evidence or inspect a known range. Analysis reads
          indexed data and immutable Git objects only; it never runs code from
          the repository.
        </p>
      </section>
      <div className="architecture-tabs investigation-tabs" role="tablist">
        {tabs.map((name) => (
          <button
            key={name}
            role="tab"
            aria-selected={tab === name}
            className={tab === name ? "active" : ""}
            onClick={() => setTab(name)}
          >
            {name}
          </button>
        ))}
      </div>

      {tab === "Stack Trace" && (
        <form
          className="history-panel investigation-form"
          onSubmit={submitFailure}
        >
          <h2>Analyze a failure</h2>
          <label>
            Stack trace
            <textarea
              aria-label="Stack trace"
              value={stackTrace}
              onChange={(event) => setStackTrace(event.target.value)}
              placeholder={
                "TypeError: Cannot read properties of undefined\n    at loadData (src/app.js:42:9)"
              }
              rows={11}
            />
          </label>
          <label>
            Exact error message (optional)
            <input
              value={errorText}
              onChange={(event) => setErrorText(event.target.value)}
            />
          </label>
          <button
            disabled={
              create.isPending || (!stackTrace.trim() && !errorText.trim())
            }
          >
            {create.isPending ? "Starting…" : "Analyze failure"}
          </button>
        </form>
      )}

      {tab === "Regression Range" && (
        <form
          className="history-panel investigation-form"
          onSubmit={submitFailure}
        >
          <h2>Known-good to known-bad range</h2>
          <label>
            Known-good commit
            <input
              required
              minLength={40}
              maxLength={40}
              value={good}
              onChange={(event) => setGood(event.target.value.trim())}
            />
          </label>
          <label>
            Known-bad commit
            <input
              required
              minLength={40}
              maxLength={40}
              value={bad}
              onChange={(event) => setBad(event.target.value.trim())}
            />
          </label>
          <button disabled={create.isPending}>Analyze static range</button>
          <button
            type="button"
            disabled={
              startBisect.isPending || good.length !== 40 || bad.length !== 40
            }
            onClick={() => startBisect.mutate()}
          >
            Start manual bisect
          </button>
        </form>
      )}

      {tab === "Commit Investigation" && (
        <section className="history-panel investigation-form">
          <h2>Investigate a suspected fix commit</h2>
          <label>
            Commit SHA
            <input
              minLength={40}
              maxLength={40}
              value={fixCommit}
              onChange={(event) => setFixCommit(event.target.value.trim())}
            />
          </label>
          <label>
            Limit to repository path (optional)
            <input
              value={file}
              onChange={(event) => setFile(event.target.value)}
            />
          </label>
          <button
            disabled={runSzz.isPending || fixCommit.length !== 40}
            onClick={() => runSzz.mutate()}
          >
            Investigate commit history
          </button>
        </section>
      )}

      {tab === "Line Investigation" && (
        <section className="history-panel investigation-form">
          <h2>Trace a repository line</h2>
          <label>
            Repository path
            <input
              value={file}
              onChange={(event) => setFile(event.target.value)}
              placeholder="src/service.ts"
            />
          </label>
          <label>
            Line number
            <input
              type="number"
              min="1"
              value={line}
              onChange={(event) => setLine(event.target.value)}
            />
          </label>
          <label>
            Commit SHA (optional; defaults to HEAD)
            <input
              value={commitAtLine}
              onChange={(event) => setCommitAtLine(event.target.value.trim())}
            />
          </label>
          <button
            disabled={traceLine.isPending || !file || Number(line) < 1}
            onClick={() => traceLine.mutate()}
          >
            Trace line history
          </button>
        </section>
      )}

      {tab === "SZZ Analysis" && (
        <section className="history-panel investigation-form">
          <h2>Conservative SZZ analysis</h2>
          <p className="muted">
            Use a known fix commit to blame changed parent lines. Results are
            candidates, not proof of causation.
          </p>
          <label>
            Fix commit SHA
            <input
              minLength={40}
              maxLength={40}
              value={fixCommit}
              onChange={(event) => setFixCommit(event.target.value.trim())}
            />
          </label>
          <label>
            Repository path (optional)
            <input
              value={file}
              onChange={(event) => setFile(event.target.value)}
            />
          </label>
          <button
            disabled={runSzz.isPending || fixCommit.length !== 40}
            onClick={() => runSzz.mutate()}
          >
            Run static SZZ analysis
          </button>
        </section>
      )}

      {activeError && (
        <div className="error-panel" role="alert">
          {errorMessage(activeError)}
        </div>
      )}
      {investigationId &&
        ["pending", "analyzing"].includes(
          investigation.data?.status ?? "pending",
        ) && (
          <p className="history-panel" role="status">
            Building the evidence report…
          </p>
        )}
      {investigation.data?.status === "failed" && (
        <div className="error-panel">{investigation.data.error}</div>
      )}
      {report && (
        <section className="history-panel investigation-report">
          <h2>Evidence report</h2>
          <p>
            <strong>{report.failure.exception_type || "Failure"}</strong>{" "}
            {report.failure.error_message}
          </p>
          <p className="muted">{report.score_meaning}</p>
          <h3>Resolved stack frames</h3>
          <pre>{JSON.stringify(report.resolved_frames, null, 2)}</pre>
          <h3>Ranked candidate commits</h3>
          <CandidateList
            repoId={repoId}
            candidates={report.top_candidates}
            onFeedback={(commit, result) => feedback.mutate({ commit, result })}
          />
          <button disabled={explain.isPending} onClick={() => explain.mutate()}>
            {explain.isPending
              ? "Asking local Ollama…"
              : "Explain investigation"}
          </button>
          {explanation && (
            <div className="investigation-explanation">
              <h3>Grounded local explanation</h3>
              <p>{explanation.answer}</p>
              <p className="muted">
                Confidence: {explanation.confidence} · Evidence:{" "}
                {explanation.evidence_sufficiency}
              </p>
            </div>
          )}
          <details>
            <summary>Method and limitations</summary>
            <p>{report.score_formula}</p>
            <ul>
              {report.limitations.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </details>
        </section>
      )}
      {szz && (
        <section className="history-panel investigation-report">
          <h2>SZZ candidates</h2>
          <p className="muted">{szz.score_definition}</p>
          <CandidateList repoId={repoId} candidates={szz.candidates} />
          {!!szz.excluded.length && (
            <details>
              <summary>Excluded or down-ranked evidence</summary>
              <pre>{JSON.stringify(szz.excluded, null, 2)}</pre>
            </details>
          )}
        </section>
      )}
      {lineResult && (
        <section className="history-panel investigation-report">
          <h2>Line history evidence</h2>
          <pre>{JSON.stringify(lineResult, null, 2)}</pre>
        </section>
      )}
      {bisect && (
        <section className="history-panel investigation-report">
          <h2>Manual static bisect</h2>
          <p>{bisect.notice}</p>
          <p>
            <strong>{bisect.remaining_commit_count}</strong> candidates remain.
          </p>
          {bisect.current_candidate && (
            <>
              <Link
                href={`/repos/${repoId}/commits/${bisect.current_candidate}`}
              >
                {bisect.current_candidate}
              </Link>
              <div className="actions">
                {(["good", "bad", "unknown"] as const).map((value) => (
                  <button
                    key={value}
                    disabled={classify.isPending}
                    onClick={() => classify.mutate(value)}
                  >
                    Mark {value}
                  </button>
                ))}
              </div>
            </>
          )}
          {bisect.status === "complete" && (
            <p className="notice">
              Static narrowing is complete. Review the remaining commit with its
              diff and context.
            </p>
          )}
        </section>
      )}
    </>
  );
}
