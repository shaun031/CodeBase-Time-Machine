"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  Background,
  Controls,
  MarkerType,
  MiniMap,
  ReactFlow,
  type Edge,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import {
  useGraphReindex,
  useGraphStatus,
  useRepository,
} from "@/hooks/use-repository";
import { api, errorMessage } from "@/lib/api";
import type { DependencyGraphNode } from "@/types/repository";
import { RepositoryNav } from "./repository-nav";
import { QueryError } from "./workspace";

const tabs = [
  "Architecture Graph",
  "Impact Analysis",
  "Hotspots",
  "Cycles",
  "Change Coupling",
];
const edgeColors: Record<string, string> = {
  DEPENDS_ON: "#aecbbb",
  IMPORTS: "#92b8de",
  CALLS: "#d9c18d",
  INHERITS: "#d7a9d2",
  IMPLEMENTS: "#d7a9d2",
  REFERENCES: "#8fc6b1",
  CO_CHANGES_WITH: "#b88972",
};
const dependencyEdgeTypes = new Set([
  "DEPENDS_ON",
  "IMPORTS",
  "IMPORTS_EXTERNAL",
  "CALLS",
  "INHERITS",
  "IMPLEMENTS",
  "REFERENCES",
]);

function metric(node: DependencyGraphNode, key: string) {
  return Number(node.metrics[key] ?? 0);
}

function GraphCanvas({
  graph,
  onSelect,
}: {
  graph: Awaited<ReturnType<typeof api.getGraph>>;
  onSelect: (node: DependencyGraphNode) => void;
}) {
  const source = useMemo(
    () => new Map(graph.nodes.map((node) => [node.id, node])),
    [graph],
  );
  const nodes: Node[] = graph.nodes.map((node, index) => ({
    id: node.id,
    position: { x: (index % 5) * 230, y: Math.floor(index / 5) * 130 },
    data: { label: `${node.name}\n${node.node_type}` },
    style: {
      background: node.node_type === "module" ? "#26352c" : "#1a2023",
      border: "1px solid #65786b",
      borderRadius: 7,
      color: "#e8ece9",
      fontSize: 12,
      padding: 10,
      width: 190,
      whiteSpace: "pre-line",
    },
  }));
  const edges: Edge[] = graph.edges.map((edge) => ({
    id: edge.id,
    source: edge.source_node_id,
    target: edge.target_node_id,
    label: edge.edge_type,
    markerEnd: { type: MarkerType.ArrowClosed },
    style: { stroke: edgeColors[edge.edge_type] ?? "#7d8a82" },
    labelStyle: { fill: "#aeb7b1", fontSize: 9 },
  }));
  return (
    <div className="architecture-canvas" aria-label="Dependency graph">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        fitView
        minZoom={0.15}
        maxZoom={2}
        onNodeClick={(_, item) => {
          const selected = source.get(item.id);
          if (selected) onSelect(selected);
        }}
      >
        <Background color="#303b35" gap={18} />
        <Controls />
        <MiniMap
          pannable
          zoomable
          nodeColor="#789081"
          maskColor="rgba(9, 13, 15, 0.72)"
          className="architecture-minimap"
        />
      </ReactFlow>
    </div>
  );
}

function NodeList({
  title,
  nodes,
}: {
  title: string;
  nodes: DependencyGraphNode[];
}) {
  return (
    <section>
      <h3>{title}</h3>
      {nodes.length ? (
        <ul className="architecture-list">
          {nodes.map((node) => (
            <li key={node.id}>
              <strong>{node.name}</strong>
              <span className="muted">{node.qualified_name}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted">No relationships found.</p>
      )}
    </section>
  );
}

export function Architecture({
  repoId,
  initialFileId,
}: {
  repoId: string;
  initialFileId?: string;
}) {
  const repository = useRepository(repoId);
  const status = useGraphStatus(repoId);
  const reindex = useGraphReindex();
  const [activeTab, setActiveTab] = useState(
    initialFileId ? "Impact Analysis" : tabs[0],
  );
  const [level, setLevel] = useState<"module" | "file" | "symbol">("module");
  const [path, setPath] = useState<string>();
  const [selected, setSelected] = useState<DependencyGraphNode>();
  const [impactTarget, setImpactTarget] = useState<DependencyGraphNode>();
  const [pathSource, setPathSource] = useState("");
  const [pathTarget, setPathTarget] = useState("");
  const [pathRequest, setPathRequest] = useState<[string, string]>();
  const graphReady = ["ready", "limited"].includes(status.data?.status ?? "");
  const graph = useQuery({
    queryKey: ["dependency-graph", repoId, level, path],
    queryFn: () => api.getGraph(repoId, level, path),
    enabled: graphReady,
  });
  const architecture = useQuery({
    queryKey: ["architecture", repoId],
    queryFn: () => api.getArchitecture(repoId),
    enabled: graphReady,
  });
  const metrics = useQuery({
    queryKey: ["graph-metrics", repoId],
    queryFn: () => api.getGraphMetrics(repoId),
    enabled: graphReady,
  });
  const cycles = useQuery({
    queryKey: ["graph-cycles", repoId],
    queryFn: () => api.getGraphCycles(repoId),
    enabled: graphReady && activeTab === "Cycles",
  });
  const coupling = useQuery({
    queryKey: ["graph-coupling", repoId],
    queryFn: () => api.getGraphCoupling(repoId),
    enabled: graphReady && activeTab === "Change Coupling",
  });
  const detail = useQuery({
    queryKey: ["graph-node", repoId, selected?.id],
    queryFn: () => api.getGraphNode(repoId, selected!.id),
    enabled: graphReady && Boolean(selected),
  });
  const impact = useQuery({
    queryKey: ["impact", repoId, impactTarget?.id, initialFileId],
    queryFn: () =>
      api.getImpact(repoId, {
        fileId:
          impactTarget?.node_type === "file"
            ? (impactTarget.file_id ?? undefined)
            : initialFileId,
        symbolId: impactTarget?.symbol_id ?? undefined,
      }),
    enabled: graphReady && Boolean(impactTarget || initialFileId),
  });
  const dependencyPath = useQuery({
    queryKey: ["dependency-path", repoId, pathRequest],
    queryFn: () =>
      api.getDependencyPath(repoId, pathRequest![0], pathRequest![1]),
    enabled: graphReady && Boolean(pathRequest),
  });

  if (repository.isError)
    return (
      <QueryError error={repository.error} retry={() => repository.refetch()} />
    );
  if (!repository.data || status.isLoading)
    return <p role="status">Loading architecture…</p>;

  const inspect = (node: DependencyGraphNode) => {
    setSelected(node);
    if (node.node_type === "module") {
      setLevel("file");
      setPath(node.path ?? node.qualified_name);
    } else if (node.node_type === "file") {
      setLevel("symbol");
      setPath(node.path ?? node.qualified_name);
    }
  };
  const displayError = graph.error ?? architecture.error ?? metrics.error;
  return (
    <>
      <p className="mono eyebrow">CURRENT ARCHITECTURE</p>
      <h1 className="repo-title">{repository.data.full_name}</h1>
      <RepositoryNav repoId={repoId} active="Architecture" />
      <section className="history-panel architecture-header">
        <div>
          <h2>Deterministic dependency graph</h2>
          <p className="muted">
            A static approximation from imports, resolvable calls, inheritance,
            repository structure, and Git history. Dynamic runtime dispatch may
            not be captured.
          </p>
        </div>
        <button
          disabled={reindex.isPending || status.data?.status === "indexing"}
          onClick={() => reindex.mutate(repoId)}
        >
          {status.data?.status === "not_indexed"
            ? "Build dependency graph"
            : "Rebuild graph"}
        </button>
      </section>
      <p className="notice">
        Explore historical snapshots, release comparisons, drift, and policy
        violations in the{" "}
        <Link href={`/repos/${repoId}/architecture/evolution`}>
          Architecture Time Machine →
        </Link>
      </p>
      {reindex.isError && (
        <p className="error-message">{errorMessage(reindex.error)}</p>
      )}
      {status.data?.status === "failed" && (
        <div className="error-panel" role="alert">
          <p>{status.data.error ?? "Graph indexing failed."}</p>
          <button onClick={() => reindex.mutate(repoId)}>
            Retry graph build
          </button>
        </div>
      )}
      {["not_indexed", "queued", "indexing"].includes(
        status.data?.status ?? "",
      ) && (
        <section className="history-panel" role="status">
          <h2>
            {status.data?.status === "not_indexed"
              ? "Graph not built"
              : "Building graph…"}
          </h2>
          <p>
            {status.data?.current_step?.replaceAll("_", " ") ??
              "Ready to build."}
          </p>
          {status.data?.progress != null && (
            <progress value={status.data.progress} max={100} />
          )}
        </section>
      )}
      {graphReady && (
        <>
          <dl className="metadata-grid">
            <div>
              <dt>Graph nodes</dt>
              <dd>{status.data?.nodes.toLocaleString()}</dd>
            </div>
            <div>
              <dt>Total relationships</dt>
              <dd>{status.data?.edges.toLocaleString()}</dd>
            </div>
            <div>
              <dt>Dependency relationships</dt>
              <dd>
                {metrics.data?.dependency_relationships.toLocaleString() ?? "—"}
              </dd>
            </div>
            <div>
              <dt>Components</dt>
              <dd>{status.data?.components}</dd>
            </div>
            <div>
              <dt>Cycles</dt>
              <dd>{status.data?.cycles}</dd>
            </div>
          </dl>
          {(status.data?.graph_stale || status.data?.graph_limited) && (
            <p className="notice">
              {status.data.graph_stale
                ? "The graph is stale for the current HEAD. Rebuild it. "
                : ""}
              {status.data.graph_limited
                ? "Configured graph limits were applied."
                : ""}
            </p>
          )}
          <div className="architecture-tabs" role="tablist">
            {tabs.map((tab) => (
              <button
                key={tab}
                role="tab"
                aria-selected={activeTab === tab}
                className={activeTab === tab ? "active" : ""}
                onClick={() => setActiveTab(tab)}
              >
                {tab}
              </button>
            ))}
          </div>
          {displayError && (
            <QueryError error={displayError} retry={() => graph.refetch()} />
          )}
          {activeTab === "Architecture Graph" && graph.data && (
            <>
              {architecture.data && (
                <section
                  className="component-overview"
                  aria-label="Architecture components"
                >
                  {architecture.data.components.map((component) => (
                    <article key={component.id}>
                      <strong>{component.name}</strong>
                      <span>{component.layer ?? "unknown"} layer</span>
                      <span>{component.node_count.toLocaleString()} nodes</span>
                    </article>
                  ))}
                </section>
              )}
              <section className="architecture-grid">
                <div>
                  <div className="graph-toolbar">
                    <strong>
                      {level === "module"
                        ? "Module overview"
                        : `${level} drill-down`}
                    </strong>
                    {level !== "module" && (
                      <button
                        onClick={() => {
                          setLevel("module");
                          setPath(undefined);
                          setSelected(undefined);
                        }}
                      >
                        Back to modules
                      </button>
                    )}
                    <span className="muted">
                      {graph.data.nodes.length} visible nodes
                    </span>
                  </div>
                  {graph.data.limited && (
                    <p className="notice">
                      This graph view was bounded for safe rendering.
                    </p>
                  )}
                  {level === "module" && graph.data.edges.length === 0 && (
                    <p className="notice">
                      No resolvable dependencies cross the current module
                      boundaries. Select a module to inspect its file graph.
                    </p>
                  )}
                  <GraphCanvas graph={graph.data} onSelect={inspect} />
                </div>
                <aside className="node-detail-panel">
                  <h2>Node details</h2>
                  {!selected && (
                    <p className="muted">
                      Select a node to inspect or drill down.
                    </p>
                  )}
                  {detail.data && (
                    <>
                      <h3>{detail.data.node.name}</h3>
                      <p className="mono muted">
                        {detail.data.node.qualified_name}
                      </p>
                      <dl className="compact-metrics">
                        <div>
                          <dt>Type</dt>
                          <dd>{detail.data.node.node_type}</dd>
                        </div>
                        <div>
                          <dt>Layer</dt>
                          <dd>{detail.data.layer ?? "unknown"}</dd>
                        </div>
                        <div>
                          <dt>Fan-in</dt>
                          <dd>{metric(detail.data.node, "fan_in")}</dd>
                        </div>
                        <div>
                          <dt>Fan-out</dt>
                          <dd>{metric(detail.data.node, "fan_out")}</dd>
                        </div>
                        <div>
                          <dt>Changes</dt>
                          <dd>{metric(detail.data.node, "change_count")}</dd>
                        </div>
                        <div>
                          <dt>Hotspot</dt>
                          <dd>
                            {metric(detail.data.node, "hotspot_score").toFixed(
                              3,
                            )}
                          </dd>
                        </div>
                      </dl>
                      <div className="actions">
                        {detail.data.node.file_id && (
                          <Link href={`/repos/${repoId}/code`}>View Code</Link>
                        )}
                        {detail.data.node.lineage_id && (
                          <Link
                            href={`/repos/${repoId}/history/symbols/${detail.data.node.lineage_id}`}
                          >
                            View History
                          </Link>
                        )}
                        {(detail.data.node.file_id ||
                          detail.data.node.symbol_id) && (
                          <button
                            onClick={() => {
                              setImpactTarget(detail.data!.node);
                              setActiveTab("Impact Analysis");
                            }}
                          >
                            Analyze Impact
                          </button>
                        )}
                        <Link
                          className="action-link"
                          href={`/repos/${repoId}/ask?${detail.data.node.lineage_id ? `lineage_id=${detail.data.node.lineage_id}&` : ""}${detail.data.node.path ? `file_path=${encodeURIComponent(detail.data.node.path)}&` : ""}question=${encodeURIComponent(`What is the role of ${detail.data.node.qualified_name}, and why is it structured this way?`)}`}
                        >
                          Ask about this node
                        </Link>
                      </div>
                      <p className="muted">
                        Used by{" "}
                        {
                          detail.data.incoming_edges.filter((edge) =>
                            dependencyEdgeTypes.has(edge.edge_type),
                          ).length
                        }{" "}
                        · Depends on{" "}
                        {
                          detail.data.outgoing_edges.filter((edge) =>
                            dependencyEdgeTypes.has(edge.edge_type),
                          ).length
                        }
                      </p>
                    </>
                  )}
                </aside>
              </section>
            </>
          )}
          {activeTab === "Impact Analysis" && (
            <section className="history-panel">
              <h2>Potential impact</h2>
              {!impactTarget && !initialFileId && (
                <p className="muted">
                  Select a file or symbol in the graph and choose Analyze
                  Impact.
                </p>
              )}
              {impact.isError && (
                <QueryError
                  error={impact.error}
                  retry={() => impact.refetch()}
                />
              )}
              {impact.data && (
                <div className="impact-columns">
                  <NodeList
                    title="Direct dependents"
                    nodes={impact.data.direct_dependents}
                  />
                  <NodeList
                    title="Transitive dependents"
                    nodes={impact.data.transitive_dependents}
                  />
                  <NodeList title="Callers" nodes={impact.data.callers} />
                  <NodeList title="Callees" nodes={impact.data.callees} />
                  <NodeList
                    title="Change coupled"
                    nodes={impact.data.change_coupled_nodes}
                  />
                </div>
              )}
              {graph.data && (
                <div className="path-controls">
                  <h3>Find dependency path</h3>
                  <select
                    aria-label="Path source"
                    value={pathSource}
                    onChange={(event) => setPathSource(event.target.value)}
                  >
                    <option value="">Source node</option>
                    {graph.data.nodes.map((node) => (
                      <option key={node.id} value={node.id}>
                        {node.name}
                      </option>
                    ))}
                  </select>
                  <select
                    aria-label="Path target"
                    value={pathTarget}
                    onChange={(event) => setPathTarget(event.target.value)}
                  >
                    <option value="">Target node</option>
                    {graph.data.nodes.map((node) => (
                      <option key={node.id} value={node.id}>
                        {node.name}
                      </option>
                    ))}
                  </select>
                  <button
                    disabled={!pathSource || !pathTarget}
                    onClick={() => setPathRequest([pathSource, pathTarget])}
                  >
                    Find path
                  </button>
                  {dependencyPath.data && (
                    <p>
                      {dependencyPath.data.found
                        ? dependencyPath.data.path
                            .map((node) => node.name)
                            .join(" → ")
                        : "No dependency path exists."}
                    </p>
                  )}
                </div>
              )}
            </section>
          )}
          {activeTab === "Hotspots" && (
            <section className="history-panel">
              <h2>Code hotspots</h2>
              <p className="muted">
                Hotspot score combines change frequency and dependency
                importance. It is not a code-quality grade.
              </p>
              {metrics.data && metrics.data.hotspot_tie_count > 1 && (
                <p className="notice">
                  {metrics.data.hotspot_tie_count} files currently share a
                  hotspot score. {metrics.data.normalization_note}
                </p>
              )}
              <ol className="hotspot-list">
                {metrics.data?.top_hotspots.map((node) => (
                  <li key={node.id}>
                    <strong>{node.qualified_name}</strong>
                    <span>Changes {metric(node, "change_count")}</span>
                    <span>Authors {metric(node, "author_count")}</span>
                    <span>Fan-in {metric(node, "fan_in")}</span>
                    <span>Fan-out {metric(node, "fan_out")}</span>
                    <span>
                      Components{" "}
                      {metric(node, "change_contribution").toFixed(3)} +{" "}
                      {metric(node, "degree_contribution").toFixed(3)} +{" "}
                      {metric(node, "coupling_contribution").toFixed(3)}
                    </span>
                    <span>
                      Score {metric(node, "hotspot_score").toFixed(3)}
                    </span>
                  </li>
                ))}
              </ol>
            </section>
          )}
          {activeTab === "Cycles" && (
            <section className="history-panel">
              <h2>Circular dependencies</h2>
              {cycles.data?.cycles.length === 0 && (
                <p className="muted">No file dependency cycles detected.</p>
              )}
              {cycles.data?.cycles.map((cycle) => (
                <article className="cycle-card" key={cycle.cycle_id}>
                  <strong>
                    Cycle {cycle.cycle_id} · {cycle.size} files
                  </strong>
                  <p>
                    {cycle.members.map((node) => node.name).join(" → ")} →{" "}
                    {cycle.members[0]?.name}
                  </p>
                </article>
              ))}
            </section>
          )}
          {activeTab === "Change Coupling" && (
            <section className="history-panel">
              <h2>Files that change together</h2>
              <p className="muted">
                Calculated as shared commits divided by the smaller file change
                count. Large commits are excluded.
              </p>
              {coupling.data?.pairs.length === 0 && (
                <p className="muted">
                  No reliable repeated co-change pairs met the current filter.
                  {coupling.data.diagnostics.commits_used < 2
                    ? ` Only ${coupling.data.diagnostics.commits_used} usable historical commit${coupling.data.diagnostics.commits_used === 1 ? " was" : "s were"} available.`
                    : ""}
                  {coupling.data.diagnostics.commits_excluded_large
                    ? ` ${coupling.data.diagnostics.commits_excluded_large} large commit${coupling.data.diagnostics.commits_excluded_large === 1 ? " was" : "s were"} excluded.`
                    : ""}
                </p>
              )}
              <ul className="architecture-list">
                {coupling.data?.pairs.map((pair) => (
                  <li key={`${pair.source.id}-${pair.target.id}`}>
                    <strong>
                      {pair.source.name} ↔ {pair.target.name}
                    </strong>
                    <span>
                      {pair.co_changes} shared commits ·{" "}
                      {(pair.coupling_score * 100).toFixed(0)}%
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </>
      )}
    </>
  );
}
