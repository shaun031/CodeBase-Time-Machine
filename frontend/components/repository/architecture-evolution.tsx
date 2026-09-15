"use client";

import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useMemo, useState } from "react";
import { api, errorMessage } from "@/lib/api";
import type {
  ArchitectureRuleWrite,
  HistoricalArchitecture,
} from "@/types/repository";
import { QueryError } from "./workspace";
import { RepositoryNav } from "./repository-nav";

const tabs = ["Time Machine", "Compare", "Drift", "Events", "Trends", "Rules", "Violations"] as const;
type Tab = (typeof tabs)[number];

function ArchitectureGraph({ graph }: { graph: HistoricalArchitecture }) {
  const modules = graph.nodes.filter((node) => node.node_type === "module");
  return (
    <div className="evolution-graph" aria-label="Historical dependency graph">
      <div className="evolution-nodes">
        {modules.map((node) => (
          <article key={node.stable_key}>
            <span>{node.layer ?? "unknown"}</span>
            <strong>{node.path}</strong>
            <small>
              in {node.metrics.fan_in ?? 0} · out {node.metrics.fan_out ?? 0}
            </small>
          </article>
        ))}
      </div>
      <ol className="dependency-list">
        {graph.edges
          .filter((edge) => edge.source.startsWith("module:"))
          .map((edge) => (
            <li key={`${edge.source}-${edge.target}`}>
              <code>{edge.source.replace("module:", "")}</code>
              <span>→</span>
              <code>{edge.target.replace("module:", "")}</code>
              <small>weight {edge.weight}</small>
            </li>
          ))}
      </ol>
    </div>
  );
}

export function ArchitectureEvolution({ repoId }: { repoId: string }) {
  const client = useQueryClient();
  const [tab, setTab] = useState<Tab>("Time Machine");
  const [position, setPosition] = useState(-1);
  const [fromIndex, setFromIndex] = useState(0);
  const [toIndex, setToIndex] = useState(-1);
  const [sourceLayer, setSourceLayer] = useState("controller");
  const [targetLayer, setTargetLayer] = useState("repository");
  const [ruleName, setRuleName] = useState("Controllers must not bypass services");
  const [baselineId, setBaselineId] = useState("");
  const [previewResult, setPreviewResult] = useState<{
    source_match_count: number;
    target_match_count: number;
    violation_count: number;
  } | null>(null);

  const repository = useQuery({ queryKey: ["repository", repoId], queryFn: () => api.getRepository(repoId) });
  const status = useQuery({
    queryKey: ["architecture-history-status", repoId],
    queryFn: () => api.getArchitectureHistoryStatus(repoId),
    refetchInterval: (query) => ["queued", "indexing"].includes(query.state.data?.status ?? "") ? 1500 : false,
  });
  const ready = ["ready", "limited"].includes(status.data?.status ?? "");
  const snapshots = useQuery({
    queryKey: ["architecture-snapshots", repoId],
    queryFn: () => api.getArchitectureSnapshots(repoId),
    enabled: ready,
  });
  const count = snapshots.data?.length ?? 0;
  const last = Math.max(0, count - 1);
  const effectivePosition = position < 0 ? last : Math.min(position, last);
  const effectiveToIndex = toIndex < 0 ? last : Math.min(toIndex, last);
  const selected = snapshots.data?.[effectivePosition];
  const graph = useQuery({
    queryKey: ["historical-architecture", repoId, selected?.commit_sha],
    queryFn: () => api.getArchitectureAt(repoId, selected!.commit_sha),
    enabled: ready && Boolean(selected),
  });
  const comparison = useQuery({
    queryKey: ["architecture-comparison", repoId, snapshots.data?.[fromIndex]?.id, snapshots.data?.[effectiveToIndex]?.id],
    queryFn: () => api.compareArchitecture(repoId, snapshots.data![fromIndex].id, snapshots.data![effectiveToIndex].id),
    enabled: ready && tab === "Compare" && Boolean(snapshots.data?.[fromIndex] && snapshots.data?.[effectiveToIndex]),
  });
  const baselines = useQuery({ queryKey: ["architecture-baselines", repoId], queryFn: () => api.getArchitectureBaselines(repoId), enabled: ready && tab === "Drift" });
  const drift = useQuery({ queryKey: ["architecture-drift", repoId, baselineId], queryFn: () => api.getArchitectureDrift(repoId, baselineId || undefined), enabled: ready && tab === "Drift" });
  const events = useQuery({ queryKey: ["architecture-events", repoId], queryFn: () => api.getArchitectureEvolution(repoId), enabled: ready && tab === "Events" });
  const trends = useQuery({ queryKey: ["architecture-trends", repoId], queryFn: () => api.getArchitectureTrends(repoId), enabled: ready && tab === "Trends" });
  const rules = useQuery({ queryKey: ["architecture-rules", repoId], queryFn: () => api.getArchitectureRules(repoId), enabled: ready && tab === "Rules" });
  const violations = useQuery({ queryKey: ["architecture-violations", repoId], queryFn: () => api.getArchitectureViolations(repoId), enabled: ready && (tab === "Violations" || tab === "Drift") });

  const reindex = useMutation({
    mutationFn: () => api.reindexArchitectureHistory(repoId),
    onSuccess: () => client.invalidateQueries({ queryKey: ["architecture-history-status", repoId] }),
  });
  const removeRule = useMutation({
    mutationFn: (ruleId: string) => api.deleteArchitectureRule(repoId, ruleId),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["architecture-rules", repoId] });
      client.invalidateQueries({ queryKey: ["architecture-violations", repoId] });
    },
  });
  const createRule = useMutation({
    mutationFn: (rule: ArchitectureRuleWrite) => api.createArchitectureRule(repoId, rule),
    onSuccess: () => {
      setPreviewResult(null);
      client.invalidateQueries({ queryKey: ["architecture-rules", repoId] });
      client.invalidateQueries({ queryKey: ["architecture-violations", repoId] });
    },
  });
  const preview = useMutation({
    mutationFn: (rule: ArchitectureRuleWrite) => api.previewArchitectureRule(repoId, rule),
    onSuccess: (result) => setPreviewResult(result),
  });
  const createBaseline = useMutation({
    mutationFn: () => api.createArchitectureBaseline(repoId, {
      name: `Architecture at ${selected!.short_sha}`,
      snapshot_id: selected!.id,
      is_default: false,
    }),
    onSuccess: (result) => {
      setBaselineId(result.id);
      client.invalidateQueries({ queryKey: ["architecture-baselines", repoId] });
    },
  });
  const rulePayload = useMemo<ArchitectureRuleWrite>(() => ({
    name: ruleName,
    rule_type: "forbidden_dependency",
    source_selector: { kind: "layer", value: sourceLayer },
    target_selector: { kind: "layer", value: targetLayer },
    severity: "error",
    enabled: true,
  }), [ruleName, sourceLayer, targetLayer]);
  const submitRule = (event: FormEvent) => {
    event.preventDefault();
    createRule.mutate(rulePayload);
  };

  if (repository.isError) return <QueryError error={repository.error} retry={() => repository.refetch()} />;
  if (!repository.data || status.isLoading) return <p role="status">Loading architecture evolution…</p>;
  return (
    <>
      <p className="mono eyebrow">ARCHITECTURE TIME MACHINE</p>
      <h1 className="repo-title">{repository.data.full_name}</h1>
      <RepositoryNav repoId={repoId} active="Evolution" />
      <section className="history-panel architecture-header">
        <div>
          <h2>Architecture evolution</h2>
          <p className="muted">Snapshots and changes come from static analysis of immutable Git objects. Structural drift is separate from rule violations.</p>
        </div>
        <button disabled={reindex.isPending || ["queued", "indexing"].includes(status.data?.status ?? "")} onClick={() => reindex.mutate()}>
          {status.data?.status === "not_indexed" ? "Build architecture history" : "Rebuild history"}
        </button>
      </section>
      {(status.isError || reindex.isError) && <QueryError error={status.error ?? reindex.error} retry={() => status.refetch()} />}
      {status.data?.status === "failed" && <div className="error-panel" role="alert">{status.data.error}</div>}
      {!ready && !status.isError && (
        <section className="history-panel" role="status">
          <h2>{status.data?.status === "not_indexed" ? "Architecture history is not indexed" : "Building snapshots…"}</h2>
          <p>{status.data?.current_step?.replaceAll("_", " ") ?? "Ready to build."}</p>
          {status.data?.progress != null && <progress value={status.data.progress} max={100} />}
        </section>
      )}
      {ready && (
        <>
          <dl className="metadata-grid">
            <div><dt>Snapshots</dt><dd>{status.data?.snapshots_created}</dd></div>
            <div><dt>Events</dt><dd>{status.data?.events_detected}</dd></div>
            <div><dt>Cycles observed</dt><dd>{status.data?.cycles_detected}</dd></div>
            <div><dt>Violation intervals</dt><dd>{status.data?.violations_detected}</dd></div>
          </dl>
          {(status.data?.stale || status.data?.limited) && <p className="notice">{status.data.stale ? "History is stale for the current HEAD. " : ""}{status.data.limited ? "Configured snapshot limits were applied." : ""}</p>}
          {count === 0 && <section className="history-panel"><h2>No architecture snapshots</h2><p className="muted">Rebuild architecture history after repository indexing has completed.</p></section>}
          <div className="architecture-tabs" role="tablist">
            {tabs.map((name) => <button key={name} role="tab" aria-selected={tab === name} className={tab === name ? "active" : ""} onClick={() => setTab(name)}>{name}</button>)}
          </div>
          {tab === "Time Machine" && selected && (
            <section className="history-panel">
              <div className="timeline-slider-header"><h2>Architecture at {selected.short_sha}</h2><span>{new Date(selected.committed_at).toLocaleString()} {selected.tags.join(" · ")}</span></div>
              <input aria-label="Architecture timeline" className="timeline-slider" type="range" min={0} max={last} value={effectivePosition} onChange={(event) => setPosition(Number(event.target.value))} />
              <div className="timeline-ends"><span>{snapshots.data?.[0]?.short_sha}</span><span>{snapshots.data?.[last]?.short_sha}</span></div>
              {graph.isLoading && <p role="status">Loading snapshot…</p>}
              {graph.isError && <QueryError error={graph.error} retry={() => graph.refetch()} />}
              {graph.data && <ArchitectureGraph graph={graph.data} />}
            </section>
          )}
          {tab === "Compare" && (
            <section className="history-panel">
              <h2>Compare snapshots</h2>
              <div className="compare-controls">
                <select aria-label="From snapshot" value={fromIndex} onChange={(event) => setFromIndex(Number(event.target.value))}>{snapshots.data?.map((item, index) => <option key={item.id} value={index}>{item.short_sha} {item.tags.join(" ")}</option>)}</select>
                <span>→</span>
                <select aria-label="To snapshot" value={effectiveToIndex} onChange={(event) => setToIndex(Number(event.target.value))}>{snapshots.data?.map((item, index) => <option key={item.id} value={index}>{item.short_sha} {item.tags.join(" ")}</option>)}</select>
              </div>
              {comparison.isLoading && <p role="status">Comparing snapshots…</p>}
              {comparison.isError && <QueryError error={comparison.error} retry={() => comparison.refetch()} />}
              {comparison.data && <div className="change-grid"><article><strong>+{comparison.data.nodes_added.length}</strong><span>nodes added</span></article><article><strong>−{comparison.data.nodes_removed.length}</strong><span>nodes removed</span></article><article><strong>+{comparison.data.edges_added.length}</strong><span>dependencies added</span></article><article><strong>−{comparison.data.edges_removed.length}</strong><span>dependencies removed</span></article><article><strong>{comparison.data.cycles_introduced.length}</strong><span>cycles introduced</span></article><article><strong>{comparison.data.cycles_resolved.length}</strong><span>cycles resolved</span></article></div>}
            </section>
          )}
          {tab === "Drift" && <section className="history-panel"><h2>Structural drift</h2><div className="compare-controls"><label>Baseline<select aria-label="Architecture baseline" value={baselineId} onChange={(event) => setBaselineId(event.target.value)}><option value="">Default baseline</option>{baselines.data?.map((baseline) => <option key={baseline.id} value={baseline.id}>{baseline.name}{baseline.is_default ? " (default)" : ""}</option>)}</select></label><button disabled={!selected || createBaseline.isPending} onClick={() => createBaseline.mutate()}>Use selected snapshot as baseline</button></div>{(drift.isError || createBaseline.isError) && <QueryError error={drift.error ?? createBaseline.error} retry={() => drift.refetch()} />}{drift.data && <><p className="muted">{drift.data.baseline.name} → {drift.data.to_snapshot.short_sha}</p><div className="drift-score">{drift.data.structural_drift.score}<small>/ 100 difference</small></div><p>{drift.data.structural_drift.interpretation}</p><details className="formula-note"><summary>How this is calculated</summary>{drift.data.structural_drift.formula}</details><div className="change-grid"><article><strong>+{drift.data.nodes_added.length}</strong><span>nodes added</span></article><article><strong>−{drift.data.nodes_removed.length}</strong><span>nodes removed</span></article><article><strong>+{drift.data.edges_added.length}</strong><span>dependencies added</span></article><article><strong>−{drift.data.edges_removed.length}</strong><span>dependencies removed</span></article></div><p className="muted">Active policy violations: {drift.data.policy_violations.length}</p></>}</section>}
          {tab === "Events" && <section className="history-panel"><h2>Evolution events</h2>{events.isLoading && <p role="status">Loading evolution events…</p>}{events.isError && <QueryError error={events.error} retry={() => events.refetch()} />}{events.data?.length === 0 && <p className="muted">No structural changes were detected between indexed snapshots.</p>}<ul className="evolution-events">{events.data?.map((item) => <li key={item.id}><strong>{item.event_type.replaceAll("_", " ")}</strong><code>{item.source}{item.target ? ` → ${item.target}` : ""}</code><Link href={`/repos/${repoId}/commits/${item.commit_sha}`}>{item.commit_sha.slice(0, 12)}</Link>{item.development_context.pull_requests.map((pr) => <a key={`pr-${pr.number}`} href={pr.html_url} title={pr.title} target="_blank" rel="noreferrer">PR #{pr.number}</a>)}{item.development_context.issues?.map((issue) => <a key={`issue-${issue.number}`} href={issue.html_url} title={issue.title} target="_blank" rel="noreferrer">Issue #{issue.number}</a>)}</li>)}</ul></section>}
          {tab === "Trends" && <section className="history-panel"><h2>Coupling trends</h2>{trends.isLoading && <p role="status">Loading architecture trends…</p>}{trends.isError && <QueryError error={trends.error} retry={() => trends.refetch()} />}{trends.data?.points.length === 0 && <p className="muted">No trend points are available.</p>}<div className="trend-bars">{trends.data?.points.map((point) => { const density = Number(point.dependency_density ?? 0); return <div key={String(point.commit_sha)} title={`Density ${density}`}><span>{String(point.commit_sha).slice(0, 7)}</span><i style={{ height: `${Math.max(3, density * 100)}%` }} /><small>{(density * 100).toFixed(1)}%</small></div>; })}</div><p className="muted">Dependency density over indexed snapshots. A higher value means more possible module pairs are connected.</p></section>}
          {tab === "Rules" && <section className="history-panel"><h2>Architecture rules</h2><form className="rule-form" onSubmit={submitRule}><label>Name<input value={ruleName} onChange={(event) => setRuleName(event.target.value)} required /></label><label>Source layer<select value={sourceLayer} onChange={(event) => setSourceLayer(event.target.value)}>{["presentation", "api", "controller", "service", "domain", "repository", "database", "infrastructure"].map((value) => <option key={value}>{value}</option>)}</select></label><label>Must not depend on<select value={targetLayer} onChange={(event) => setTargetLayer(event.target.value)}>{["presentation", "api", "controller", "service", "domain", "repository", "database", "infrastructure"].map((value) => <option key={value}>{value}</option>)}</select></label><div className="actions"><button type="button" onClick={() => preview.mutate(rulePayload)}>Preview across history</button><button type="submit" disabled={createRule.isPending}>Save rule</button></div>{previewResult && <p>{previewResult.source_match_count} source modules · {previewResult.target_match_count} target modules · {previewResult.violation_count} historical violation{previewResult.violation_count === 1 ? "" : "s"}.</p>}</form><ul className="architecture-list">{rules.data?.map((rule) => <li key={rule.id}><strong>{rule.name}</strong><span>{rule.source_selector.value} must not depend on {rule.target_selector?.value}</span><button onClick={() => removeRule.mutate(rule.id)}>Delete</button></li>)}</ul>{(createRule.isError || preview.isError) && <p className="error-message">{errorMessage(createRule.error ?? preview.error)}</p>}</section>}
          {tab === "Violations" && <section className="history-panel"><h2>Policy violations</h2><p className="muted">Only explicit enabled rules produce violations. Historical results mean the selected policy matches that snapshot; they do not imply the rule existed then.</p>{violations.isLoading && <p role="status">Loading policy violations…</p>}{violations.isError && <QueryError error={violations.error} retry={() => violations.refetch()} />}{violations.data?.length === 0 && <p className="muted">No configured policy violations were found.</p>}<ul className="evolution-events">{violations.data?.map((item) => <li key={item.id}><strong>{item.rule_name}</strong><code>{item.source} → {item.target}</code><span className={`status-${item.status}`}>{item.status}</span><Link href={`/repos/${repoId}/commits/${item.introduced_commit_sha}`}>introduced {item.introduced_commit_sha.slice(0, 12)}</Link>{item.resolved_commit_sha && <Link href={`/repos/${repoId}/commits/${item.resolved_commit_sha}`}>resolved {item.resolved_commit_sha.slice(0, 12)}</Link>}<small>{item.lifetime_days} day{item.lifetime_days === 1 ? "" : "s"} observed</small></li>)}</ul></section>}
        </>
      )}
    </>
  );
}
