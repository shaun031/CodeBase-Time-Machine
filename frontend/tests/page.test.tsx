import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import Home from "@/app/page";
import { Indexing } from "@/components/repository/indexing";
import { Dashboard } from "@/components/repository/dashboard";
import { CommitList } from "@/components/repository/commits";
import { CommitView } from "@/components/repository/commit-detail";
import { CodeExplorer } from "@/components/repository/code-explorer";
import { HistoryExplorer } from "@/components/repository/history";
import { SymbolHistory } from "@/components/repository/symbol-history";
import { Architecture } from "@/components/repository/architecture";
import { ArchitectureEvolution } from "@/components/repository/architecture-evolution";
import { Archaeology } from "@/components/repository/archaeology";
import { AskAssistant } from "@/components/repository/ask";
import {
  IssueList,
  IssueView,
  PullRequestList,
  PullRequestView,
} from "@/components/repository/github-context";
import { api, ApiError } from "@/lib/api";
import type {
  AnalysisJob,
  CommitDetail,
  Repository,
  RepositoryStats,
  CodeStats,
  HistoryCommit,
  HistoryStatus,
  SymbolEvent,
  SymbolLineage,
  SymbolVersion,
} from "@/types/repository";

vi.mock("@xyflow/react", () => ({
  ReactFlow: ({
    nodes,
    edges,
    onNodeClick,
    children,
  }: {
    nodes: Array<{ id: string; data: { label: string } }>;
    edges: Array<{ id: string; source: string; target: string }>;
    onNodeClick: (event: unknown, node: { id: string }) => void;
    children: ReactNode;
  }) => (
    <div data-testid="react-flow" data-edge-count={edges.length}>
      {nodes.map((node) => (
        <button key={node.id} onClick={() => onNodeClick({}, node)}>
          {node.data.label}
        </button>
      ))}
      {children}
    </div>
  ),
  Background: () => null,
  Controls: () => null,
  MiniMap: ({
    maskColor,
    className,
  }: {
    maskColor: string;
    className: string;
  }) => (
    <div
      data-testid="graph-minimap"
      data-mask={maskColor}
      className={className}
    />
  ),
  MarkerType: { ArrowClosed: "arrowclosed" },
}));

const navigation = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => navigation }));
const repoId = "01234567-89ab-4cde-8012-3456789abcde";
const jobId = "11234567-89ab-4cde-8012-3456789abcde";
const sha = "a".repeat(40);
const repo: Repository = {
  id: repoId,
  provider: "github",
  owner: "owner",
  name: "repo",
  full_name: "owner/repo",
  url: "https://github.com/owner/repo",
  status: "ready",
  default_branch: "main",
  head_sha: sha,
  commit_count: 1,
  indexed_at: "2020-01-01T12:00:00Z",
  last_refreshed_at: null,
  indexing_error: null,
  history_rewritten: false,
  history_index_status: "not_indexed",
  history_indexed_through_sha: null,
  history_limited: false,
  history_stale: false,
  history_indexed_commit_count: 0,
  history_total_commit_count: 1,
  active_job_id: null,
};
const job: AnalysisJob = {
  id: jobId,
  repository_id: repoId,
  status: "running",
  current_step: "storing_commits",
  progress: 50,
  error_message: null,
  job_type: "repository_initial_index",
};
const stats: RepositoryStats = {
  total_commits: 1,
  merge_commits: 0,
  contributors: 1,
  historical_paths: 1,
  insertions: 1,
  deletions: 0,
  first_commit_at: "2020-01-01T12:00:00Z",
  latest_commit_at: "2020-01-01T12:00:00Z",
};
const codeStats: CodeStats = {
  total_files: 2,
  source_files: 1,
  parsed_files: 1,
  unsupported_files: 1,
  failed_files: 0,
  total_lines: 4,
  symbol_count: 2,
  functions: 0,
  classes: 1,
  methods: 1,
  languages: [{ language: "Python", files: 1, lines: 3, percentage: 100 }],
};
const commit: CommitDetail = {
  sha,
  short_sha: sha.slice(0, 12),
  message: "Rename application\n\nDetails café",
  author_name: "Fixture Author",
  authored_at: "2020-01-01T12:00:00Z",
  committed_at: "2020-01-01T12:00:00Z",
  is_merge_commit: false,
  files_changed: 1,
  insertions: 0,
  deletions: 0,
  parents: [],
  changes: [
    {
      id: "change-1",
      old_path: "app.py",
      new_path: "main.py",
      change_type: "renamed",
      additions: 0,
      deletions: 0,
      similarity_score: 100,
    },
  ],
};
const lineageId = "21234567-89ab-4cde-8012-3456789abcde";
const versionOneId = "31234567-89ab-4cde-8012-3456789abcde";
const versionTwoId = "41234567-89ab-4cde-8012-3456789abcde";
const githubStatus = {
  status: "ready",
  progress: null,
  current_step: "ready",
  last_synced_at: "2020-01-02T12:00:00Z",
  pull_requests_indexed: 1,
  issues_indexed: 1,
  comments_indexed: 2,
  review_comments_indexed: 1,
  rate_limit_remaining: 55,
  rate_limit_reset_at: null,
  sync_error: null,
  github_index_limited: false,
  job_id: null,
};
const githubLabel = { name: "bug", description: "A bug", color: "d73a4a" };
const moduleNode = {
  id: "71234567-89ab-4cde-8012-3456789abcde",
  node_type: "module",
  name: "services",
  qualified_name: "src/services",
  file_id: null,
  symbol_id: null,
  path: "src/services",
  language: null,
  lineage_id: null,
  layer: "service",
  metrics: { fan_in: 2, fan_out: 1, hotspot_score: 0 },
  metadata: {},
};
const graphFileNode = {
  ...moduleNode,
  id: "81234567-89ab-4cde-8012-3456789abcde",
  node_type: "file",
  name: "user_service.py",
  qualified_name: "src/services/user_service.py",
  file_id: "file-1",
  path: "src/services/user_service.py",
  language: "Python",
  metrics: {
    fan_in: 4,
    fan_out: 2,
    change_count: 8,
    author_count: 3,
    hotspot_score: 0.82,
  },
};
const archaeologyTarget = {
  entity_type: "symbol" as const,
  entity_id: lineageId,
  current_file_id: null,
  name: "Calculator.total",
  path: "src/math_utils.py",
  kind: "method",
  status: "current",
  introduced_at: "2020-01-01T12:00:00Z",
  last_modified_at: "2020-01-02T12:00:00Z",
  age_days: 1461,
  days_since_last_change: 1460,
  change_count: 9,
  churn: 42,
  contributor_count: 3,
  rename_count: 1,
  move_count: 1,
  rewrite_count: 1,
  changes_last_30_days: 0,
  changes_last_90_days: 0,
  changes_last_180_days: 0,
  volatility: 0.72,
  stability: 0.64,
  classification: "stable_legacy",
  metadata: {},
};
const archaeologyContributor = {
  identity_key: "fixture-author",
  display_name: "Fixture Author",
  commit_count: 8,
  files_touched: 3,
  symbols_touched: 2,
  lines_changed: 42,
  first_activity: "2020-01-01T12:00:00Z",
  last_activity: "2020-01-02T12:00:00Z",
  knowledge_score: 1,
  contribution_share: 1,
  introduced: true,
  evidence: { touches: 8 },
};
const pullRequest = {
  id: "51234567-89ab-4cde-8012-3456789abcde",
  number: 12,
  title: "Fix tax calculation",
  state: "closed",
  draft: false,
  merged: true,
  author_login: "octocat",
  created_at: "2020-01-01T12:00:00Z",
  updated_at: "2020-01-02T12:00:00Z",
  merged_at: "2020-01-02T12:00:00Z",
  closed_at: "2020-01-02T12:00:00Z",
  html_url: "https://github.com/owner/repo/pull/12",
  commits_count: 1,
  labels: [githubLabel],
};
const issue = {
  id: "61234567-89ab-4cde-8012-3456789abcde",
  number: 10,
  title: "Calculator returns incorrect tax",
  state: "closed",
  author_login: "reporter",
  created_at: "2020-01-01T10:00:00Z",
  updated_at: "2020-01-02T12:00:00Z",
  closed_at: "2020-01-02T12:00:00Z",
  html_url: "https://github.com/owner/repo/issues/10",
  milestone: "v1",
  labels: [githubLabel],
};
const historyCommit: HistoryCommit = {
  sha,
  short_sha: sha.slice(0, 12),
  message: "Introduce calculator",
  author_name: "Fixture Author",
  authored_at: "2020-01-01T12:00:00Z",
  committed_at: "2020-01-01T12:00:00Z",
  is_merge_commit: false,
};
const historyStatus: HistoryStatus = {
  status: "ready",
  progress: null,
  current_step: null,
  indexed_commits: 10,
  total_commits: 10,
  lineages: 3,
  versions: 8,
  events: 9,
  history_limited: false,
  history_stale: false,
  last_indexed_sha: sha,
  job_id: null,
};
const versionOne: SymbolVersion = {
  id: versionOneId,
  lineage_id: lineageId,
  file_path: "calculator.py",
  language: "Python",
  name: "calculate_total",
  qualified_name: "calculate_total",
  kind: "function",
  signature: "def calculate_total(values)",
  start_line: 1,
  end_line: 2,
  start_column: 1,
  end_column: 18,
  documentation: null,
  match_type: "exact",
  match_confidence: 1,
  matching_metadata: { introduced: true },
  source_truncated: false,
  commit: historyCommit,
};
const versionTwo: SymbolVersion = {
  ...versionOne,
  id: versionTwoId,
  file_path: "math_utils.py",
  name: "total",
  qualified_name: "Calculator.total",
  kind: "method",
  signature: "def total(self, values)",
  match_type: "symbol_rename",
  match_confidence: 0.92,
  commit: { ...historyCommit, message: "Rename and move total" },
};
function historyEvent(
  eventType: string,
  label: string,
  id = `event-${eventType}`,
): SymbolEvent {
  return {
    id,
    lineage_id: lineageId,
    event_type: eventType,
    previous_version_id: eventType === "introduced" ? null : versionOneId,
    new_version_id:
      eventType === "deleted"
        ? null
        : eventType === "introduced"
          ? versionOneId
          : versionTwoId,
    summary_data: null,
    commit: historyCommit,
    symbol_name: "total",
    symbol_kind: "method",
    file_path: "math_utils.py",
    deterministic_label: label,
  };
}
const historyEvents = [
  historyEvent("introduced", "calculate_total introduced"),
  historyEvent("body_changed", "calculate_total body changed"),
  historyEvent("renamed", "calculate_total renamed to total"),
  historyEvent("moved", "total moved to math_utils.py"),
  historyEvent("deleted", "total deleted"),
];
const lineage: SymbolLineage = {
  id: lineageId,
  current_name: "total",
  current_qualified_name: "Calculator.total",
  current_file_path: "math_utils.py",
  symbol_kind: "method",
  is_deleted: false,
  introduced_commit: historyCommit,
  last_seen_commit: historyCommit,
  deleted_commit: null,
  latest_version: versionTwo,
  versions: [versionOne, versionTwo],
  events: historyEvents.slice(0, 4),
  previous_names: ["calculate_total", "total"],
  file_paths: ["calculator.py", "math_utils.py"],
};

function show(ui: React.ReactNode) {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={client}>{ui}</QueryClientProvider>,
  );
}
beforeEach(() => {
  navigation.push.mockReset();
  navigation.replace.mockReset();
  vi.spyOn(api, "getSystemStatus").mockResolvedValue({
    backend: "ok",
    database: "ok",
    redis: "ok",
  });
  vi.spyOn(api, "getRepository").mockResolvedValue(repo);
  vi.spyOn(api, "getAIStatus").mockResolvedValue({
    provider: "ollama",
    available: false,
    base_url_safe: "http://127.0.0.1:11434",
    llm_model: "qwen3:4b",
    llm_model_available: false,
    embedding_model: "all-minilm",
    embedding_model_available: false,
    message: "Ollama is not running.",
  });
  vi.spyOn(api, "getRepositoryAIStatus").mockResolvedValue({
    status: "not_indexed",
    progress: null,
    current_step: null,
    documents: 0,
    embedded_documents: 0,
    embedding_model: null,
    embedding_dimension: null,
    last_indexed_sha: null,
    index_stale: false,
    ollama_available: false,
    error: null,
    job_id: null,
    completed_at: null,
  });
  vi.spyOn(api, "getAnalysisJob").mockResolvedValue(job);
  vi.spyOn(api, "getRepositoryStats").mockResolvedValue(stats);
  vi.spyOn(api, "getCodeStats").mockResolvedValue(codeStats);
  vi.spyOn(api, "getTags").mockResolvedValue([]);
  vi.spyOn(api, "getCommits").mockResolvedValue({
    items: [commit],
    page: 1,
    page_size: 50,
    total: 1,
  });
  vi.spyOn(api, "getCommit").mockResolvedValue(commit);
  vi.spyOn(api, "getFiles").mockResolvedValue([
    {
      name: "src",
      path: "src",
      type: "directory",
      language: null,
      size_bytes: null,
      parse_status: null,
      children: [
        {
          name: "service.py",
          path: "src/service.py",
          type: "file",
          language: "Python",
          size_bytes: 45,
          parse_status: "parsed",
          children: [],
        },
      ],
    },
  ]);
  vi.spyOn(api, "getFile").mockResolvedValue({
    id: "file-1",
    path: "src/service.py",
    filename: "service.py",
    extension: ".py",
    language: "Python",
    blob_sha: sha,
    size_bytes: 45,
    line_count: 3,
    is_binary: false,
    parse_status: "parsed",
    syntax_error_count: 0,
    indexed_commit_sha: sha,
  });
  vi.spyOn(api, "getFileContent").mockResolvedValue({
    path: "src/service.py",
    content: "class Service:\n    def load(self):\n        return True",
    start_line: 1,
    end_line: 3,
    total_lines: 3,
    truncated: false,
  });
  vi.spyOn(api, "getFileSymbols").mockResolvedValue([
    {
      id: "symbol-1",
      file_id: "file-1",
      parent_symbol_id: null,
      lineage_id: null,
      name: "Service",
      qualified_name: "Service",
      kind: "class",
      signature: "class Service",
      start_line: 1,
      end_line: 3,
      start_column: 1,
      end_column: 20,
      visibility: null,
      is_async: false,
      is_static: false,
      documentation: null,
      metadata: null,
      file_path: "src/service.py",
      language: "Python",
    },
  ]);
  vi.spyOn(api, "searchSymbols").mockResolvedValue({
    items: [],
    page: 1,
    page_size: 30,
    total: 0,
  });
  vi.spyOn(api, "getCommitEvents").mockResolvedValue([]);
  vi.spyOn(api, "getGitHubStatus").mockResolvedValue(githubStatus);
  vi.spyOn(api, "syncGitHub").mockResolvedValue({
    repository_id: repoId,
    job_id: jobId,
    status: "queued",
  });
  vi.spyOn(api, "getPullRequests").mockResolvedValue({
    items: [pullRequest],
    page: 1,
    page_size: 50,
    total: 1,
  });
  vi.spyOn(api, "getIssues").mockResolvedValue({
    items: [issue],
    page: 1,
    page_size: 50,
    total: 1,
  });
  vi.spyOn(api, "getPullRequest").mockResolvedValue({
    ...pullRequest,
    body: "Fixes #10\n\n<script>alert('unsafe')</script>",
    base_branch: "main",
    head_branch: "fix-tax",
    merge_commit_sha: sha,
    additions: 4,
    deletions: 2,
    changed_files: 1,
    comments_count: 1,
    review_comments_count: 1,
    commits: [commit],
    commit_shas: [sha],
    linked_issues: [
      {
        issue,
        owner: "owner",
        repository: "repo",
        number: 10,
        reference_type: "fixes",
        raw_reference: "Fixes #10",
        confidence: 0.98,
        external: false,
      },
    ],
    comments: [
      {
        id: "comment-1",
        comment_type: "pr_comment",
        author_login: "reviewer",
        body: "Looks good",
        created_at: "2020-01-02T10:00:00Z",
        updated_at: "2020-01-02T10:00:00Z",
        html_url: "https://github.com/owner/repo/pull/12#comment",
        path: null,
        commit_sha: null,
        original_commit_sha: null,
        line: null,
        original_line: null,
        side: null,
        diff_hunk: null,
      },
    ],
    review_comments: [
      {
        id: "review-1",
        comment_type: "review_comment",
        author_login: "reviewer",
        body: "Please cover this branch",
        created_at: "2020-01-02T11:00:00Z",
        updated_at: "2020-01-02T11:00:00Z",
        html_url: "https://github.com/owner/repo/pull/12#review",
        path: "tax.py",
        commit_sha: sha,
        original_commit_sha: sha,
        line: 8,
        original_line: 7,
        side: "RIGHT",
        diff_hunk: "@@ -7 +8 @@",
      },
    ],
    affected_symbols: [
      {
        lineage_id: lineageId,
        name: "calculate_tax",
        symbol_kind: "function",
        file_path: "tax.py",
        event_type: "body_changed",
        commit_sha: sha,
      },
    ],
  });
  vi.spyOn(api, "getIssue").mockResolvedValue({
    ...issue,
    body: "Tax is **incorrect**.",
    comments_count: 1,
    comments: [],
    related_pull_requests: [
      { pull_request: pullRequest, relationship: "fixes", confidence: 0.98 },
    ],
    related_commits: [commit],
    affected_symbols: [
      {
        lineage_id: lineageId,
        name: "calculate_tax",
        symbol_kind: "function",
        file_path: "tax.py",
        event_type: "body_changed",
        commit_sha: sha,
      },
    ],
  });
  vi.spyOn(api, "getCommitContext").mockResolvedValue({
    commit,
    associated_pull_requests: [pullRequest],
    referenced_issues: [
      {
        issue,
        owner: "owner",
        repository: "repo",
        number: 10,
        reference_type: "fixes",
        raw_reference: "Fixes #10",
        confidence: 0.98,
        external: false,
      },
    ],
    symbol_changes: [],
  });
  vi.spyOn(api, "getSymbolContext").mockResolvedValue({
    lineage_id: lineageId,
    events: [],
  });
  vi.spyOn(api, "getGraphStatus").mockResolvedValue({
    status: "ready",
    progress: null,
    current_step: "ready",
    nodes: 12,
    edges: 18,
    cycles: 1,
    components: 3,
    last_indexed_sha: sha,
    graph_stale: false,
    graph_limited: false,
    error: null,
    job_id: null,
    completed_at: "2020-01-01T12:00:00Z",
  });
  vi.spyOn(api, "getGraph").mockImplementation(async (_id, level) => ({
    level,
    nodes: level === "module" ? [moduleNode] : [graphFileNode],
    edges: [],
    limited: false,
    graph_stale: false,
  }));
  vi.spyOn(api, "getArchitecture").mockResolvedValue({
    label: "Current Architecture",
    components: [
      {
        id: moduleNode.id,
        name: "services",
        path: "src/services",
        component_type: "directory",
        layer: "service",
        confidence: 0.8,
        node_count: 4,
      },
    ],
    component_dependencies: [],
    layers: { service: 1 },
    graph_stale: false,
    metrics: {
      nodes: 12,
      edges: 18,
      files: 4,
      symbols: 6,
      modules: 2,
      external_dependencies: 1,
      cycles: 1,
      dependency_relationships: 9,
      edge_counts: { DEPENDS_ON: 9 },
      relationship_levels: { file: 7, module: 2 },
      average_fan_in: 1.2,
      average_fan_out: 1.2,
      top_fan_in: [graphFileNode],
      top_fan_out: [graphFileNode],
      top_hotspots: [graphFileNode],
      hotspot_tie_count: 1,
      hotspot_formula: "0.45*changes + 0.35*degree_centrality + 0.20*coupling",
      normalization_note:
        "Equal positive values receive the neutral score 0.5.",
    },
  });
  vi.spyOn(api, "getGraphMetrics").mockResolvedValue({
    nodes: 12,
    edges: 18,
    files: 4,
    symbols: 6,
    modules: 2,
    external_dependencies: 1,
    cycles: 1,
    dependency_relationships: 9,
    edge_counts: { DEPENDS_ON: 9 },
    relationship_levels: { file: 7, module: 2 },
    average_fan_in: 1.2,
    average_fan_out: 1.2,
    top_fan_in: [graphFileNode],
    top_fan_out: [graphFileNode],
    top_hotspots: [graphFileNode],
    hotspot_tie_count: 1,
    hotspot_formula: "0.45*changes + 0.35*degree_centrality + 0.20*coupling",
    normalization_note: "Equal positive values receive the neutral score 0.5.",
  });
  vi.spyOn(api, "getGraphNode").mockResolvedValue({
    node: graphFileNode,
    incoming_edges: [],
    outgoing_edges: [],
    component: "services",
    layer: "service",
  });
  vi.spyOn(api, "getGraphCycles").mockResolvedValue({
    level: "file",
    cycles: [
      {
        cycle_id: 1,
        members: [
          graphFileNode,
          { ...graphFileNode, id: "cycle-2", name: "auth_service.py" },
        ],
        edges: [],
        size: 2,
      },
    ],
  });
  vi.spyOn(api, "getGraphCoupling").mockResolvedValue({
    level: "file",
    pairs: [
      {
        source: graphFileNode,
        target: { ...graphFileNode, id: "pair-2", name: "user_controller.py" },
        co_changes: 7,
        coupling_score: 0.78,
      },
    ],
    formula: "co_change_count / min(source_change_count, target_change_count)",
    diagnostics: {
      commits_examined: 8,
      commits_used: 7,
      commits_excluded_large: 1,
      candidate_pairs: 1,
      pairs_after_filtering: 1,
    },
  });
  vi.spyOn(api, "getImpact").mockResolvedValue({
    wording: "Potentially affected",
    target: graphFileNode,
    direct_dependencies: [],
    direct_dependents: [
      { ...graphFileNode, id: "dependent", name: "user_controller.py" },
    ],
    transitive_dependents: [],
    callers: [],
    callees: [],
    change_coupled_nodes: [],
    paths: [],
    metrics: graphFileNode.metrics,
  });
  vi.spyOn(api, "getDependencyPath").mockResolvedValue({
    found: false,
    path: [],
    edges: [],
    length: null,
  });
  vi.spyOn(api, "reindexGraph").mockResolvedValue({
    repository_id: repoId,
    job_id: jobId,
    status: "queued",
  });
  vi.spyOn(api, "getHistoryStatus").mockResolvedValue(historyStatus);
  vi.spyOn(api, "getHistoryEvents").mockResolvedValue({
    items: historyEvents,
    page: 1,
    page_size: 50,
    total: historyEvents.length,
  });
  vi.spyOn(api, "searchLineages").mockResolvedValue({
    items: [],
    page: 1,
    page_size: 30,
    total: 0,
  });
  vi.spyOn(api, "getLineage").mockResolvedValue(lineage);
  vi.spyOn(api, "getHistoricalSymbolSource").mockImplementation(
    async (_id, _lineage, versionId) => ({
      version_id: versionId,
      commit_sha: sha,
      file_path: versionId === versionOneId ? "calculator.py" : "math_utils.py",
      start_line: 1,
      end_line: 2,
      language: "Python",
      source:
        versionId === versionOneId
          ? "def calculate_total(values):\n    return sum(values)"
          : "def total(self, values):\n    return sum(values)",
      retrieved_from_git: false,
    }),
  );
  vi.spyOn(api, "compareSymbolVersions").mockResolvedValue({
    from_version: versionOneId,
    to_version: versionTwoId,
    old_source: "def calculate_total(values): pass",
    new_source: "def total(self, values): pass",
    old_name: "calculate_total",
    new_name: "total",
    old_path: "calculator.py",
    new_path: "math_utils.py",
    old_signature: "def calculate_total(values)",
    new_signature: "def total(self, values)",
    old_lines: [1, 2],
    new_lines: [1, 2],
    diff: "-def calculate_total(values): pass\n+def total(self, values): pass",
    truncated: false,
  });
  vi.spyOn(api, "getHistoricalFile").mockResolvedValue({
    path: "src/service.py",
    commit_sha: sha,
    content: "class HistoricalService:\n    pass",
    language: "Python",
    total_lines: 2,
    historical: true,
  });
  vi.spyOn(api, "getArchaeologyStatus").mockResolvedValue({
    status: "ready",
    progress: 100,
    step: "ready",
    files_processed: 3,
    symbols_processed: 2,
    rewrites_detected: 1,
    copy_candidates: 1,
    contributors: 1,
    last_indexed_sha: sha,
    stale: false,
    error: null,
    job_id: jobId,
    completed_at: "2020-01-02T12:00:00Z",
  });
  vi.spyOn(api, "getArchaeologyOverview").mockResolvedValue({
    repository_age_days: 1461,
    total_historical_files: 3,
    current_files: 2,
    deleted_files: 1,
    current_symbols: 2,
    deleted_symbols: 1,
    renamed_symbols: 1,
    moved_symbols: 1,
    major_rewrites: 1,
    contributors: 1,
    median_symbol_age_days: 1461,
    median_file_age_days: 1461,
    most_changed_files: [archaeologyTarget],
    oldest_current_symbols: [archaeologyTarget],
    recently_rewritten_symbols: [archaeologyTarget],
    age_buckets: {
      under_30_days: 0,
      one_to_six_months: 0,
      six_to_twelve_months: 0,
      one_to_three_years: 0,
      over_three_years: 2,
    },
    volatility_formula: "deterministic volatility fixture",
    stability_formula: "deterministic stability fixture",
    canonical_date: "Git committer date",
    merge_commit_policy:
      "Merge commits are excluded where branch evidence exists.",
    knowledge_concentration: { label: "concentrated" },
  });
  vi.spyOn(api, "getArchaeologyVolatility").mockResolvedValue({
    level: "symbol",
    items: [archaeologyTarget],
    volatility_formula: "deterministic volatility fixture",
    stability_formula: "deterministic stability fixture",
  });
  vi.spyOn(api, "getArchaeologyContributors").mockResolvedValue({
    items: [archaeologyContributor],
    concentration: { label: "concentrated" },
    interpretation: "Repository-history knowledge only.",
  });
  vi.spyOn(api, "getArchaeologyRewrites").mockResolvedValue([
    {
      id: "rewrite-1",
      lineage_id: lineageId,
      symbol: "Calculator.total",
      file_path: "src/math_utils.py",
      commit_id: "commit-1",
      commit_sha: sha,
      committed_at: "2020-01-02T12:00:00Z",
      similarity: 0.31,
      lines_added: 8,
      lines_deleted: 5,
      reason:
        "Normalized token similarity fell below the configured threshold.",
      evidence: {},
      old_version_id: versionOneId,
      new_version_id: versionTwoId,
    },
  ]);
  vi.spyOn(api, "searchArchaeology").mockResolvedValue({
    items: [
      {
        entity_type: "symbol",
        entity_id: lineageId,
        name: "Calculator.total",
        historical_name: "calculate_total",
        kind: "method",
        file_path: "src/math_utils.py",
        commit_sha: sha,
        commit_id: "commit-1",
        status: "deleted",
        lineage_id: lineageId,
        version_id: versionOneId,
        matched_reason: "historical name",
        match_type: "exact",
        source_available: true,
      },
    ],
    page: 1,
    page_size: 50,
    total: 1,
  });
  vi.spyOn(api, "getArchaeologyDossier").mockResolvedValue({
    target: archaeologyTarget,
    provenance: {
      entity_type: "symbol",
      entity_id: lineageId,
      origin: { name: "calculate_total", path: "calculator.py" },
      current_identity: { name: "Calculator.total", path: "src/math_utils.py" },
      status: "current",
      timeline: [
        {
          event: "introduced",
          name: "calculate_total",
          committed_at: "2020-01-01T12:00:00Z",
          author: "Fixture Author",
          commit_id: "commit-1",
        },
      ],
      renames: [],
      moves: [],
      rewrites: [],
      contributors: [archaeologyContributor],
    },
    activity: {},
    contributors: {
      items: [archaeologyContributor],
      concentration: { label: "concentrated" },
      interpretation: "Repository-history knowledge only.",
    },
    development_context: {},
    dependencies: { fan_in: 4, fan_out: 2 },
    related_code: [],
    limitations: [],
  });
  vi.spyOn(api, "reindexArchaeology").mockResolvedValue({
    repository_id: repoId,
    job_id: jobId,
    status: "queued",
  });
  const snapshots = [
    {
      id: "snapshot-1",
      commit_sha: "a".repeat(40),
      short_sha: "aaaaaaaaaaaa",
      committed_at: "2024-01-01T12:00:00Z",
      tags: ["v1.0"],
      node_count: 2,
      edge_count: 1,
      module_count: 2,
      component_count: 1,
      cycle_count: 0,
      metrics: { dependency_density: 0.5 },
    },
    {
      id: "snapshot-2",
      commit_sha: "b".repeat(40),
      short_sha: "bbbbbbbbbbbb",
      committed_at: "2024-06-01T12:00:00Z",
      tags: ["v2.0"],
      node_count: 3,
      edge_count: 2,
      module_count: 3,
      component_count: 1,
      cycle_count: 0,
      metrics: { dependency_density: 0.33 },
    },
  ];
  vi.spyOn(api, "getArchitectureHistoryStatus").mockResolvedValue({
    status: "ready",
    progress: null,
    current_step: "ready",
    commits_examined: 6,
    snapshots_created: 2,
    events_detected: 2,
    cycles_detected: 1,
    violations_detected: 1,
    last_indexed_sha: "b".repeat(40),
    stale: false,
    limited: false,
    error: null,
    job_id: null,
    completed_at: "2024-06-01T12:00:00Z",
  });
  vi.spyOn(api, "getArchitectureSnapshots").mockResolvedValue(snapshots);
  vi.spyOn(api, "getArchitectureAt").mockResolvedValue({
    snapshot: snapshots[1],
    nodes: [
      { stable_key: "module:controller", node_type: "module", name: "controller", path: "controller", layer: "controller", confidence: 0.8, metrics: { fan_in: 0, fan_out: 1 } },
      { stable_key: "module:service", node_type: "module", name: "service", path: "service", layer: "service", confidence: 0.8, metrics: { fan_in: 1, fan_out: 0 } },
    ],
    edges: [{ source: "module:controller", target: "module:service", edge_type: "DEPENDS_ON", weight: 1, confidence: 1 }],
    cycles: [],
    metrics: { dependency_density: 0.5 },
    source: "deterministic_static_analysis",
  });
  vi.spyOn(api, "compareArchitecture").mockResolvedValue({
    from_snapshot: snapshots[0], to_snapshot: snapshots[1], nodes_added: [], nodes_removed: [], nodes_changed: [], edges_added: [], edges_removed: [], edges_changed: [], cycles_introduced: [], cycles_resolved: [], metrics_before: {}, metrics_after: {}, evolution_events: [], structural_drift: { score: 25, formula: "weighted Jaccard", interpretation: "Structural difference only." },
  });
  vi.spyOn(api, "getArchitectureDrift").mockResolvedValue({
    from_snapshot: snapshots[0], to_snapshot: snapshots[1], nodes_added: [], nodes_removed: [], nodes_changed: [], edges_added: [], edges_removed: [], edges_changed: [], cycles_introduced: [], cycles_resolved: [], metrics_before: {}, metrics_after: {}, evolution_events: [], structural_drift: { score: 25, formula: "weighted Jaccard", interpretation: "Structural difference only." }, baseline: { id: "baseline-1", name: "v1.0", snapshot_id: "snapshot-1", is_default: true, created_at: "2024-01-01T12:00:00Z" }, policy_violations: [],
  });
  vi.spyOn(api, "getArchitectureBaselines").mockResolvedValue([{ id: "baseline-1", name: "v1.0", snapshot_id: "snapshot-1", is_default: true, created_at: "2024-01-01T12:00:00Z" }]);
  vi.spyOn(api, "createArchitectureBaseline").mockResolvedValue({ id: "baseline-2", name: "Architecture at bbbbbbbbbbbb", snapshot_id: "snapshot-2", is_default: false, created_at: "2024-02-01T12:00:00Z" });
  vi.spyOn(api, "getArchitectureEvolution").mockResolvedValue([]);
  vi.spyOn(api, "getArchitectureTrends").mockResolvedValue({ points: snapshots.map((item) => ({ commit_sha: item.commit_sha, dependency_density: item.metrics.dependency_density })), definitions: {} });
  vi.spyOn(api, "getArchitectureRules").mockResolvedValue([]);
  vi.spyOn(api, "getArchitectureViolations").mockResolvedValue([]);
  vi.spyOn(api, "previewArchitectureRule").mockResolvedValue({ valid: true, snapshots_evaluated: 2, source_match_count: 2, target_match_count: 1, violation_count: 1 });
  vi.spyOn(api, "createArchitectureRule").mockResolvedValue({ id: "rule-1", repository_id: repoId, name: "Controllers must not bypass services", rule_type: "forbidden_dependency", source_selector: { kind: "layer", value: "controller" }, target_selector: { kind: "layer", value: "repository" }, severity: "error", enabled: true, created_at: "2024-01-01T12:00:00Z", updated_at: "2024-01-01T12:00:00Z" });
  vi.spyOn(api, "deleteArchitectureRule").mockResolvedValue(undefined);
  vi.spyOn(api, "reindexArchitectureHistory").mockResolvedValue({ repository_id: repoId, job_id: jobId, status: "queued" });
});

describe("AI assistant", () => {
  it("keeps the question editable while the AI index is unavailable", async () => {
    show(<AskAssistant repoId={repoId} initial={{}} />);
    const question = await screen.findByLabelText("Repository question");
    expect(question).toBeEnabled();
    fireEvent.change(question, { target: { value: "My own question" } });
    expect(question).toHaveValue("My own question");
    expect(
      screen.getByRole("button", { name: "Ask with evidence" }),
    ).toBeDisabled();
  });

  it("submits a user-entered question when the index is ready", async () => {
    vi.mocked(api.getAIStatus).mockResolvedValue({
      provider: "ollama",
      available: true,
      base_url_safe: "http://127.0.0.1:11434",
      llm_model: "qwen3:4b",
      llm_model_available: true,
      embedding_model: "all-minilm",
      embedding_model_available: true,
      message: null,
    });
    vi.mocked(api.getRepositoryAIStatus).mockResolvedValue({
      status: "ready",
      progress: null,
      current_step: "ready",
      documents: 12,
      embedded_documents: 12,
      embedding_model: "all-minilm",
      embedding_dimension: 384,
      last_indexed_sha: sha,
      index_stale: false,
      ollama_available: true,
      error: null,
      job_id: jobId,
      completed_at: "2020-01-01T12:00:00Z",
    });
    const ask = vi.spyOn(api, "askRepository").mockResolvedValue({
      answer: "The evidence supports this explanation.",
      claims: [],
      confidence: "low",
      evidence_sufficiency: "weak",
      evidence: [],
      limitations: [],
      cached: false,
      diagnostics: null,
    });
    show(<AskAssistant repoId={repoId} initial={{}} />);
    const question = await screen.findByLabelText("Repository question");
    fireEvent.change(question, { target: { value: "Why is this here?" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask with evidence" }));
    expect(
      await screen.findByText("The evidence supports this explanation."),
    ).toBeVisible();
    expect(ask).toHaveBeenCalledWith(
      repoId,
      expect.objectContaining({ question: "Why is this here?" }),
    );
  });
});
describe("repository submission", () => {
  it("validates empty and unsupported URLs without sending a request", () => {
    const create = vi.spyOn(api, "createRepository");
    show(<Home />);
    fireEvent.click(screen.getByRole("button", { name: "Analyze Repository" }));
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Enter a public GitHub URL",
    );
    fireEvent.change(screen.getByLabelText("Repository URL"), {
      target: { value: "https://localhost/a/b" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Analyze Repository" }));
    expect(create).not.toHaveBeenCalled();
  });
  it("submits and navigates to the returned job", async () => {
    const create = vi.spyOn(api, "createRepository").mockResolvedValue({
      repository_id: repoId,
      job_id: jobId,
      status: "queued",
    });
    show(<Home />);
    fireEvent.change(screen.getByLabelText("Repository URL"), {
      target: { value: "https://github.com/owner/repo.git" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Analyze Repository" }));
    await waitFor(() =>
      expect(navigation.push).toHaveBeenCalledWith(
        `/repos/${repoId}/indexing?job=${jobId}`,
      ),
    );
    expect(create).toHaveBeenCalledWith(
      "https://github.com/owner/repo.git",
      expect.anything(),
    );
  });
  it("reuses an already indexed repository", async () => {
    vi.spyOn(api, "createRepository").mockResolvedValue({
      repository_id: repoId,
      job_id: null,
      status: "ready",
    });
    show(<Home />);
    fireEvent.change(screen.getByLabelText("Repository URL"), {
      target: { value: "https://github.com/owner/repo" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Analyze Repository" }));
    await waitFor(() =>
      expect(navigation.push).toHaveBeenCalledWith(`/repos/${repoId}`),
    );
  });
  it("displays safe API errors", async () => {
    vi.spyOn(api, "createRepository").mockRejectedValue(
      new ApiError(
        422,
        "Repository is not publicly accessible.",
        "REPOSITORY_NOT_ACCESSIBLE",
      ),
    );
    show(<Home />);
    fireEvent.change(screen.getByLabelText("Repository URL"), {
      target: { value: "https://github.com/owner/repo" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Analyze Repository" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "not publicly accessible",
    );
  });
});
describe("indexing", () => {
  it("shows measured processing progress", async () => {
    show(<Indexing repoId={repoId} jobId={jobId} />);
    expect(await screen.findByText(/Repository analysis: 50.0%/)).toBeVisible();
    expect(navigation.replace).not.toHaveBeenCalled();
  });
  it("navigates after completion", async () => {
    vi.spyOn(api, "getAnalysisJob").mockResolvedValue({
      ...job,
      status: "completed",
      current_step: "completed",
      progress: null,
    });
    show(<Indexing repoId={repoId} jobId={jobId} />);
    await waitFor(() =>
      expect(navigation.replace).toHaveBeenCalledWith(`/repos/${repoId}`),
    );
  });
  it("shows failure and retries", async () => {
    vi.spyOn(api, "getAnalysisJob").mockResolvedValue({
      ...job,
      status: "failed",
      error_message: "Repository exceeds MAX_COMMITS.",
    });
    vi.spyOn(api, "refreshRepository").mockResolvedValue({
      repository_id: repoId,
      job_id: "new-job",
      status: "queued",
    });
    show(<Indexing repoId={repoId} jobId={jobId} />);
    expect(
      await screen.findByRole("heading", { name: "Analysis failed" }),
    ).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Retry Analysis" }));
    await waitFor(() =>
      expect(navigation.push).toHaveBeenCalledWith(
        `/repos/${repoId}/indexing?job=new-job`,
      ),
    );
  });
  it("rejects a job belonging to another repository", async () => {
    vi.spyOn(api, "getAnalysisJob").mockResolvedValue({
      ...job,
      repository_id: "other",
      status: "completed",
    });
    show(<Indexing repoId={repoId} jobId={jobId} />);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "different repository",
    );
    expect(navigation.replace).not.toHaveBeenCalled();
  });
});
describe("history explorer", () => {
  it("renders dashboard and starts refresh", async () => {
    vi.spyOn(api, "refreshRepository").mockResolvedValue({
      repository_id: repoId,
      job_id: jobId,
      status: "queued",
    });
    show(<Dashboard repoId={repoId} />);
    expect(
      await screen.findByRole("heading", { name: "owner/repo" }),
    ).toBeVisible();
    expect(
      screen.getByRole("link", { name: "Browse Commits" }),
    ).toHaveAttribute("href", `/repos/${repoId}/commits`);
    fireEvent.click(screen.getByRole("button", { name: "Refresh Repository" }));
    await waitFor(() => expect(navigation.push).toHaveBeenCalled());
  });
  it("renders commit rows and bounded pagination", async () => {
    show(<CommitList repoId={repoId} />);
    expect(
      await screen.findByRole("heading", { name: "Rename application" }),
    ).toBeVisible();
    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
  });
  it("renders renames and a clearly truncated, escaped diff", async () => {
    const diff = vi.spyOn(api, "getDiff").mockResolvedValue({
      content: "+<script>alert('unsafe')</script>",
      truncated: true,
    });
    const view = show(<CommitView repoId={repoId} sha={sha} />);
    expect(await screen.findByText("app.py → main.py")).toBeVisible();
    expect(diff).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Load diff" }));
    expect(await screen.findByText(/Diff truncated/)).toBeVisible();
    expect(view.container.querySelector("script")).toBeNull();
  });
});

describe("code explorer", () => {
  it("renders a lazy file tree, source lines, and symbol outline", async () => {
    show(<CodeExplorer repoId={repoId} />);
    expect(await screen.findByText("service.py")).toBeVisible();
    expect(await screen.findByText("class Service:")).toBeVisible();
    expect(screen.getByRole("button", { name: /Service/ })).toBeVisible();
    expect(api.getFileContent).toHaveBeenCalledWith(repoId, "src/service.py");
  });

  it("debounces global symbol search", async () => {
    vi.mocked(api.searchSymbols).mockResolvedValue({
      items: [
        {
          ...(await api.getFileSymbols(repoId, "src/service.py"))[0],
          file_path: "src/service.py",
        },
      ],
      page: 1,
      page_size: 30,
      total: 1,
    });
    show(<CodeExplorer repoId={repoId} />);
    fireEvent.change(await screen.findByLabelText("Search symbols"), {
      target: { value: "Service" },
    });
    expect(await screen.findByText("class · src/service.py")).toBeVisible();
    expect(api.searchSymbols).toHaveBeenCalledWith(repoId, "Service");
  });

  it("shows file-tree loading and safe errors", async () => {
    vi.mocked(api.getFiles).mockImplementation(() => new Promise(() => {}));
    const view = show(<CodeExplorer repoId={repoId} />);
    expect(await screen.findByText("Loading repository files…")).toBeVisible();
    view.unmount();
    vi.mocked(api.getFiles).mockRejectedValue(
      new ApiError(409, "Code indexing failed."),
    );
    show(<CodeExplorer repoId={repoId} />);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Code indexing failed",
    );
  });

  it("links current symbols to history and clearly labels historical code", async () => {
    const current = (await api.getFileSymbols(repoId, "src/service.py"))[0];
    vi.mocked(api.getFileSymbols).mockResolvedValue([
      { ...current, lineage_id: lineageId },
    ]);
    show(<CodeExplorer repoId={repoId} />);
    expect(
      await screen.findByRole("link", { name: "View History" }),
    ).toHaveAttribute("href", `/repos/${repoId}/history/symbols/${lineageId}`);
    fireEvent.change(screen.getByLabelText("Viewing commit"), {
      target: { value: sha },
    });
    expect(await screen.findByText("Historical snapshot")).toBeVisible();
    expect(await screen.findByText("class HistoricalService:")).toBeVisible();
  });
});

describe("historical analysis", () => {
  it("renders all timeline event categories and lineage links", async () => {
    show(<HistoryExplorer repoId={repoId} />);
    expect(await screen.findByRole("link", { name: "History" })).toBeVisible();
    expect(await screen.findByText("calculate_total introduced")).toBeVisible();
    expect(screen.getByText("calculate_total body changed")).toBeVisible();
    expect(screen.getByText("calculate_total renamed to total")).toBeVisible();
    expect(screen.getByText("total moved to math_utils.py")).toBeVisible();
    expect(screen.getByText("total deleted")).toBeVisible();
    expect(
      screen.getByText("calculate_total introduced").closest("a"),
    ).toHaveAttribute("href", `/repos/${repoId}/history/symbols/${lineageId}`);
  });

  it("shows loading, failed, and limited history states", async () => {
    vi.mocked(api.getHistoryStatus).mockImplementationOnce(
      () => new Promise(() => {}),
    );
    const loading = show(<HistoryExplorer repoId={repoId} />);
    expect(await screen.findByText("Loading historical index…")).toBeVisible();
    loading.unmount();

    vi.mocked(api.getHistoryStatus).mockResolvedValueOnce({
      ...historyStatus,
      status: "failed",
      last_indexed_sha: null,
    });
    const failed = show(<HistoryExplorer repoId={repoId} />);
    expect(await screen.findByText("Historical analysis failed")).toBeVisible();
    failed.unmount();

    vi.mocked(api.getHistoryStatus).mockResolvedValueOnce({
      ...historyStatus,
      status: "limited",
      history_limited: true,
      indexed_commits: 5,
    });
    show(<HistoryExplorer repoId={repoId} />);
    expect(await screen.findByText(/limited to 5 of 10 commits/)).toBeVisible();
  });

  it("loads historical source, selects a version, and compares versions", async () => {
    show(<SymbolHistory repoId={repoId} lineageId={lineageId} />);
    expect(await screen.findByText("Calculator.total")).toBeVisible();
    expect(await screen.findByText("def total(self, values):")).toBeVisible();
    expect(screen.getByText("Possible heuristic lineage match")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: /introduced/i }));
    await waitFor(() =>
      expect(api.getHistoricalSymbolSource).toHaveBeenCalledWith(
        repoId,
        lineageId,
        versionOneId,
      ),
    );
    fireEvent.click(screen.getByRole("button", { name: /renamed/i }));
    fireEvent.click(
      await screen.findByRole("button", {
        name: "Compare with previous version",
      }),
    );
    expect(
      await screen.findByText(/def calculate_total\(values\): pass/),
    ).toBeVisible();
    expect(api.compareSymbolVersions).toHaveBeenCalledWith(
      repoId,
      lineageId,
      versionOneId,
      versionTwoId,
    );
  });

  it("links commit symbol events to their lineage", async () => {
    vi.mocked(api.getCommitEvents).mockResolvedValue([historyEvents[2]]);
    show(<CommitView repoId={repoId} sha={sha} />);
    const link = await screen.findByRole("link", {
      name: "calculate_total renamed to total",
    });
    expect(link).toHaveAttribute(
      "href",
      `/repos/${repoId}/history/symbols/${lineageId}`,
    );
  });
});

describe("GitHub development context", () => {
  it("renders pull request and issue lists with filters and labels", async () => {
    const pullView = show(<PullRequestList repoId={repoId} />);
    expect(await screen.findByText("#12 Fix tax calculation")).toBeVisible();
    expect(screen.getByText("bug")).toBeVisible();
    pullView.unmount();
    show(<IssueList repoId={repoId} />);
    expect(
      await screen.findByText("#10 Calculator returns incorrect tax"),
    ).toBeVisible();
    fireEvent.change(screen.getByLabelText("State"), {
      target: { value: "closed" },
    });
    await waitFor(() =>
      expect(api.getIssues).toHaveBeenCalledWith(
        repoId,
        expect.objectContaining({ state: "closed" }),
      ),
    );
  });

  it("renders PR evidence, comments, review locations and safe markdown", async () => {
    const view = show(<PullRequestView repoId={repoId} number={12} />);
    expect(await screen.findByText("Fix tax calculation")).toBeVisible();
    expect(
      screen.getByRole("link", {
        name: "#10 Calculator returns incorrect tax",
      }),
    ).toBeVisible();
    expect(screen.getByText("Looks good")).toBeVisible();
    expect(screen.getByText("tax.py:8")).toBeVisible();
    expect(screen.getByText("calculate_tax")).toHaveAttribute(
      "href",
      `/repos/${repoId}/history/symbols/${lineageId}`,
    );
    expect(view.container.querySelector("script")).toBeNull();
  });

  it("renders issue relationships, commits and affected symbols", async () => {
    show(<IssueView repoId={repoId} number={10} />);
    expect(
      await screen.findByText("Calculator returns incorrect tax"),
    ).toBeVisible();
    expect(screen.getByText("#12 Fix tax calculation")).toBeVisible();
    expect(screen.getByText(commit.short_sha)).toBeVisible();
    expect(screen.getByText("calculate_tax")).toBeVisible();
  });

  it("shows rate-limit recovery without breaking repository pages", async () => {
    vi.mocked(api.getGitHubStatus).mockResolvedValue({
      ...githubStatus,
      status: "rate_limited",
      sync_error: "GitHub API rate limit reached. Try again after 2030-01-01.",
    });
    show(<PullRequestList repoId={repoId} />);
    expect(
      await screen.findByText("GitHub API rate limit reached"),
    ).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Sync GitHub context" }),
    ).toBeVisible();
  });

  it("shows development context on commit pages", async () => {
    show(<CommitView repoId={repoId} sha={sha} />);
    expect(await screen.findByText("Development context")).toBeVisible();
    expect(screen.getByText("#12 Fix tax calculation")).toBeVisible();
    expect(
      screen.getByText("#10 Calculator returns incorrect tax"),
    ).toBeVisible();
  });
});

describe("software archaeology", () => {
  it("renders the overview, age distribution, volatility controls, contributors, and rewrites", async () => {
    show(<Archaeology repoId={repoId} />);
    expect(
      await screen.findByRole("heading", { name: "owner/repo" }),
    ).toBeVisible();
    expect(screen.getByRole("link", { name: "Archaeology" })).toHaveAttribute(
      "href",
      `/repos/${repoId}/archaeology`,
    );
    expect(await screen.findByText("Repository age")).toBeVisible();
    expect(screen.getAllByText("4.0 years").length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("tab", { name: "Code Age" }));
    expect(await screen.findByText("Current symbol age")).toBeVisible();
    expect(screen.getByText("over three years")).toBeVisible();

    fireEvent.click(screen.getByRole("tab", { name: "Volatility" }));
    expect(await screen.findByText("Historical activity")).toBeVisible();
    fireEvent.change(screen.getByLabelText("Sort archaeology"), {
      target: { value: "stability" },
    });
    await waitFor(() =>
      expect(api.getArchaeologyVolatility).toHaveBeenCalledWith(
        repoId,
        "symbol",
        "stability",
      ),
    );

    fireEvent.click(screen.getByRole("tab", { name: "Contributors" }));
    expect(await screen.findByText("Fixture Author")).toBeVisible();
    expect(screen.getByText("concentrated")).toBeVisible();

    fireEvent.click(screen.getByRole("tab", { name: "Rewrites" }));
    expect(await screen.findByText("31% similar")).toBeVisible();
    expect(screen.getByText("+8 / -5")).toBeVisible();
  });

  it("searches historical and deleted code with explicit filters", async () => {
    show(<Archaeology repoId={repoId} />);
    fireEvent.click(await screen.findByRole("tab", { name: "Search History" }));
    fireEvent.change(screen.getByLabelText("Search repository history"), {
      target: { value: "calculate_total" },
    });
    expect(await screen.findByText("calculate_total")).toBeVisible();
    expect(screen.getByText("deleted")).toBeVisible();
    expect(screen.getByText("exact · historical name")).toBeVisible();
    await waitFor(() =>
      expect(api.searchArchaeology).toHaveBeenCalledWith(
        repoId,
        "calculate_total",
        "all",
        "all",
      ),
    );

    fireEvent.click(screen.getByRole("tab", { name: "Deleted Code" }));
    await waitFor(() =>
      expect(api.searchArchaeology).toHaveBeenCalledWith(
        repoId,
        "calculate_total",
        "deleted_symbol",
        "deleted",
      ),
    );
  });

  it("opens a deterministic provenance dossier", async () => {
    show(<Archaeology repoId={repoId} />);
    fireEvent.click(
      await screen.findByRole("button", { name: "Calculator.total" }),
    );
    const dialog = await screen.findByRole("dialog", {
      name: "Archaeology dossier",
    });
    await waitFor(() => expect(dialog).toHaveTextContent("calculate_total"));
    expect(dialog).toHaveTextContent("Fixture Author: 100%");
    expect(dialog).toHaveTextContent("Fan-in4");
    expect(
      screen.getByRole("link", { name: "View full symbol history" }),
    ).toHaveAttribute("href", `/repos/${repoId}/history/symbols/${lineageId}`);
  });

  it("shows indexing and failure states and can start a rebuild", async () => {
    vi.mocked(api.getArchaeologyStatus).mockResolvedValue({
      status: "not_indexed",
      progress: null,
      step: null,
      files_processed: 0,
      symbols_processed: 0,
      rewrites_detected: 0,
      copy_candidates: 0,
      contributors: 0,
      last_indexed_sha: null,
      stale: false,
      error: "Previous archaeology index is unavailable.",
      job_id: null,
      completed_at: null,
    });
    show(<Archaeology repoId={repoId} />);
    expect(await screen.findByText("Build archaeology index")).toBeVisible();
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Previous archaeology index is unavailable.",
    );
    fireEvent.click(screen.getByRole("button", { name: "Build index" }));
    await waitFor(() =>
      expect(api.reindexArchaeology).toHaveBeenCalledWith(
        repoId,
        expect.any(Object),
      ),
    );
  });
});

describe("current architecture", () => {
  it("passes module edges to React Flow and applies the dark minimap theme", async () => {
    const target = {
      ...moduleNode,
      id: "module-2",
      name: "models",
      qualified_name: "src/models",
    };
    vi.mocked(api.getGraph).mockResolvedValue({
      level: "module",
      nodes: [moduleNode, target],
      edges: [
        {
          id: "edge-1",
          source_node_id: moduleNode.id,
          target_node_id: target.id,
          edge_type: "DEPENDS_ON",
          weight: 1,
          confidence: 1,
          resolution_type: "aggregate",
          metadata: {},
        },
      ],
      limited: false,
      graph_stale: false,
    });
    show(<Architecture repoId={repoId} />);
    expect(await screen.findByText("Dependency relationships")).toBeVisible();
    expect(await screen.findByTestId("react-flow")).toHaveAttribute(
      "data-edge-count",
      "1",
    );
    expect(screen.getByTestId("graph-minimap")).toHaveAttribute(
      "data-mask",
      "rgba(9, 13, 15, 0.72)",
    );
  });

  it("renders a bounded module graph and drills into files", async () => {
    show(<Architecture repoId={repoId} />);
    expect(
      await screen.findByText("Deterministic dependency graph"),
    ).toBeVisible();
    expect(
      (await screen.findAllByLabelText("Dependency graph"))[0],
    ).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: /services\s+module/i }));
    await waitFor(() =>
      expect(api.getGraph).toHaveBeenCalledWith(repoId, "file", "src/services"),
    );
    expect(await screen.findByText("file drill-down")).toBeVisible();
    expect(await screen.findByText("Fan-in")).toBeVisible();
    expect(screen.getByText("Fan-out")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Rebuild graph" }));
    await waitFor(() =>
      expect(api.reindexGraph).toHaveBeenCalledWith(repoId, expect.any(Object)),
    );
  });

  it("shows node details and deterministic potential impact", async () => {
    show(<Architecture repoId={repoId} initialFileId="file-1" />);
    expect(await screen.findByText("Potential impact")).toBeVisible();
    expect(await screen.findByText("Direct dependents")).toBeVisible();
    expect(screen.getByText("user_controller.py")).toBeVisible();
    expect(api.getImpact).toHaveBeenCalledWith(
      repoId,
      expect.objectContaining({ fileId: "file-1" }),
    );
  });

  it("renders hotspots, cycles, and change coupling", async () => {
    show(<Architecture repoId={repoId} />);
    fireEvent.click(await screen.findByRole("tab", { name: "Hotspots" }));
    expect(await screen.findByText("Code hotspots")).toBeVisible();
    expect(screen.getByText("Score 0.820")).toBeVisible();
    fireEvent.click(screen.getByRole("tab", { name: "Cycles" }));
    expect(await screen.findByText(/Cycle 1 · 2 files/)).toBeVisible();
    fireEvent.click(screen.getByRole("tab", { name: "Change Coupling" }));
    expect(await screen.findByText("7 shared commits · 78%")).toBeVisible();
  });

  it("explains tied hotspots, empty coupling, and an empty module graph", async () => {
    const metricResult = await api.getGraphMetrics(repoId);
    vi.mocked(api.getGraphMetrics).mockResolvedValue({
      ...metricResult,
      hotspot_tie_count: 4,
      normalization_note:
        "Equal positive values receive the neutral score 0.5.",
    });
    vi.mocked(api.getGraphCoupling).mockResolvedValue({
      level: "file",
      pairs: [],
      formula:
        "co_change_count / min(source_change_count, target_change_count)",
      diagnostics: {
        commits_examined: 2,
        commits_used: 1,
        commits_excluded_large: 1,
        candidate_pairs: 0,
        pairs_after_filtering: 0,
      },
    });
    vi.mocked(api.getGraph).mockResolvedValue({
      level: "module",
      nodes: [moduleNode],
      edges: [],
      limited: false,
      graph_stale: false,
    });
    show(<Architecture repoId={repoId} />);
    expect(
      await screen.findByText(/No resolvable dependencies cross/),
    ).toBeVisible();
    fireEvent.click(screen.getByRole("tab", { name: "Hotspots" }));
    expect(await screen.findByText(/4 files currently share/)).toBeVisible();
    fireEvent.click(screen.getByRole("tab", { name: "Change Coupling" }));
    expect(
      await screen.findByText(/Only 1 usable historical commit was available/),
    ).toBeVisible();
    expect(screen.getByText(/1 large commit was excluded/)).toBeVisible();
  });

  it("shows loading, empty, failure, and bounded graph states", async () => {
    vi.mocked(api.getGraphStatus).mockResolvedValue({
      ...(await api.getGraphStatus(repoId)),
      status: "failed",
      error: "Dependency graph indexing failed safely.",
    });
    show(<Architecture repoId={repoId} />);
    expect(
      await screen.findByText("Dependency graph indexing failed safely."),
    ).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Retry graph build" }),
    ).toBeVisible();
  });
});

describe("architecture evolution", () => {
  it("travels through deterministic historical snapshots", async () => {
    show(<ArchitectureEvolution repoId={repoId} />);
    expect(await screen.findByText("Architecture at bbbbbbbbbbbb")).toBeVisible();
    expect(screen.getByLabelText("Architecture timeline")).toHaveValue("1");
    expect((await screen.findAllByText("controller"))[0]).toBeVisible();
    expect(api.getArchitectureAt).toHaveBeenCalledWith(repoId, "b".repeat(40));
  });

  it("keeps structural drift separate and previews policy rules", async () => {
    show(<ArchitectureEvolution repoId={repoId} />);
    fireEvent.click(await screen.findByRole("tab", { name: "Events" }));
    expect(await screen.findByText("No structural changes were detected between indexed snapshots.")).toBeVisible();
    fireEvent.click(await screen.findByRole("tab", { name: "Drift" }));
    expect(await screen.findByText("Structural difference only.")).toBeVisible();
    expect(screen.getByText("Active policy violations: 0")).toBeVisible();
    expect(screen.getByLabelText("Architecture baseline")).toHaveValue("");
    fireEvent.click(screen.getByRole("button", { name: "Use selected snapshot as baseline" }));
    await waitFor(() => expect(api.createArchitectureBaseline).toHaveBeenCalledWith(repoId, {
      name: "Architecture at bbbbbbbbbbbb",
      snapshot_id: "snapshot-2",
      is_default: false,
    }));
    fireEvent.click(screen.getByRole("tab", { name: "Rules" }));
    fireEvent.click(await screen.findByRole("button", { name: "Preview across history" }));
    expect(await screen.findByText("2 source modules · 1 target modules · 1 historical violation.")).toBeVisible();
  });
});
