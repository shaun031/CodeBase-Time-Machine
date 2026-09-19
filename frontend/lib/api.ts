import { config } from "./config";
import type { HealthResponse, SystemStatus } from "@/types/api";
import type {
  AnalysisJob,
  CommitDetail,
  CodeStats,
  CommitPage,
  Diff,
  FileContent,
  FileTreeNode,
  RepositoryFile,
  Repository,
  RepositoryStats,
  Submission,
  SymbolPage,
  CodeSymbol,
  Tag,
  HistoricalFileContent,
  HistoricalSymbolSource,
  HistoryEventPage,
  HistoryStatus,
  LineageSearchPage,
  SymbolEvent,
  SymbolLineage,
  SymbolVersionCompare,
  CommitContext,
  GitHubStatus,
  IssueDetail,
  IssuePage,
  PullRequestDetail,
  PullRequestPage,
  SymbolContext,
  ArchitectureResponse,
  ChangeCouplingResponse,
  DependencyCycleResponse,
  DependencyGraphMetrics,
  DependencyGraphNodeDetail,
  DependencyGraphStatus,
  DependencyGraphView,
  DependencyPathResponse,
  ImpactResponse,
  AIStatus,
  RepositoryAIStatus,
  AskContext,
  AskResponse,
  ArchaeologyStatus,
  ArchaeologyOverview,
  ArchaeologyVolatility,
  ArchaeologyContributors,
  ArchaeologyRewrite,
  HistoricalSearchResponse,
  ProvenanceResponse,
  ArchaeologyDossier,
  ArchitectureHistoryStatus,
  ArchitectureSnapshot,
  HistoricalArchitecture,
  ArchitectureComparison,
  ArchitectureEvolutionEvent,
  ArchitectureBaseline,
  ArchitectureRule,
  ArchitectureRuleWrite,
  ArchitectureViolation,
  Investigation,
  InvestigationCandidate,
  SZZResult,
  LineHistoryResult,
  BisectSession,
} from "@/types/repository";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly code = "API_ERROR",
  ) {
    super(message);
  }
}

function isSystemStatus(value: unknown): value is SystemStatus {
  if (!value || typeof value !== "object") return false;
  const data = value as Record<string, unknown>;
  return (
    data.backend === "ok" &&
    ["ok", "unavailable"].includes(String(data.database)) &&
    ["ok", "unavailable", "not_required"].includes(String(data.redis)) &&
    ["ok", "unavailable"].includes(String(data.ollama))
  );
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  acceptDegraded = false,
): Promise<T> {
  let response: Response;
  try {
    const timeout = path.endsWith("/ask")
      ? 210000
      : options.method === "POST"
        ? 90000
        : 15000;
    response = await fetch(`${config.apiBaseUrl}${path}`, {
      ...options,
      signal: AbortSignal.timeout(timeout),
      cache: "no-store",
    });
  } catch {
    throw new ApiError(
      0,
      "Cannot reach the backend, or the request timed out. Check the local services and retry.",
      "NETWORK_ERROR",
    );
  }
  if (response.status === 204 && response.ok) return undefined as T;
  let data: unknown;
  try {
    data = await response.json();
  } catch {
    throw new ApiError(
      response.status,
      "The backend returned an unreadable response.",
    );
  }
  if (
    !response.ok &&
    !(acceptDegraded && response.status === 503 && isSystemStatus(data))
  ) {
    let message = `API request failed (${response.status})`;
    let code = "API_ERROR";
    if (
      data &&
      typeof data === "object" &&
      "error" in data &&
      data.error &&
      typeof data.error === "object"
    ) {
      if ("message" in data.error && typeof data.error.message === "string")
        message = data.error.message;
      if ("code" in data.error && typeof data.error.code === "string")
        code = data.error.code;
    }
    throw new ApiError(response.status, message, code);
  }
  if (acceptDegraded && !isSystemStatus(data))
    throw new ApiError(502, "Invalid system status response");
  return data as T;
}
const part = encodeURIComponent;
const filePath = (path: string) => path.split("/").map(part).join("/");
export const api = {
  getHealth: () => request<HealthResponse>("/api/health"),
  getSystemStatus: () => request<SystemStatus>("/api/system/status", {}, true),
  createRepository: (url: string) =>
    request<Submission>("/api/repositories", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    }),
  getRepository: (id: string) =>
    request<Repository>(`/api/repositories/${part(id)}`),
  refreshRepository: (id: string) =>
    request<Submission>(`/api/repositories/${part(id)}/refresh`, {
      method: "POST",
    }),
  getAnalysisJob: (id: string) => request<AnalysisJob>(`/api/jobs/${part(id)}`),
  getCommits: (id: string, page: number) =>
    request<CommitPage>(
      `/api/repositories/${part(id)}/commits?page=${page}&page_size=50`,
    ),
  getCommit: (id: string, sha: string) =>
    request<CommitDetail>(`/api/repositories/${part(id)}/commits/${part(sha)}`),
  getDiff: (id: string, sha: string) =>
    request<Diff>(`/api/repositories/${part(id)}/commits/${part(sha)}/diff`),
  getRepositoryStats: (id: string) =>
    request<RepositoryStats>(`/api/repositories/${part(id)}/stats`),
  getTags: (id: string) => request<Tag[]>(`/api/repositories/${part(id)}/tags`),
  getCodeStats: (id: string) =>
    request<CodeStats>(`/api/repositories/${part(id)}/code/stats`),
  getFiles: (id: string) =>
    request<FileTreeNode[]>(`/api/repositories/${part(id)}/files`),
  getFile: (id: string, path: string) =>
    request<RepositoryFile>(
      `/api/repositories/${part(id)}/files/${filePath(path)}`,
    ),
  getFileContent: (id: string, path: string) =>
    request<FileContent>(
      `/api/repositories/${part(id)}/files/${filePath(path)}/content`,
    ),
  getFileSymbols: (id: string, path: string) =>
    request<CodeSymbol[]>(
      `/api/repositories/${part(id)}/files/${filePath(path)}/symbols`,
    ),
  searchSymbols: (id: string, search: string) =>
    request<SymbolPage>(
      `/api/repositories/${part(id)}/symbols?search=${part(search)}&page_size=30`,
    ),
  reindexCode: (id: string) =>
    request<Submission>(`/api/repositories/${part(id)}/code/reindex`, {
      method: "POST",
    }),
  reindexHistory: (id: string) =>
    request<Submission>(`/api/repositories/${part(id)}/history/reindex`, {
      method: "POST",
    }),
  getHistoryStatus: (id: string) =>
    request<HistoryStatus>(`/api/repositories/${part(id)}/history/status`),
  getHistoryEvents: (
    id: string,
    filters: {
      symbolKind?: string;
      filePath?: string;
      author?: string;
      page?: number;
    } = {},
  ) => {
    const query = new URLSearchParams({
      page: String(filters.page ?? 1),
      page_size: "50",
    });
    if (filters.symbolKind) query.set("symbol_kind", filters.symbolKind);
    if (filters.filePath) query.set("file_path", filters.filePath);
    if (filters.author) query.set("author", filters.author);
    return request<HistoryEventPage>(
      `/api/repositories/${part(id)}/history/events?${query}`,
    );
  },
  searchLineages: (id: string, search: string) =>
    request<LineageSearchPage>(
      `/api/repositories/${part(id)}/history/lineages?search=${part(search)}&page_size=30`,
    ),
  getLineage: (id: string, lineageId: string) =>
    request<SymbolLineage>(
      `/api/repositories/${part(id)}/lineages/${part(lineageId)}`,
    ),
  getSymbolHistory: (id: string, symbolId: string) =>
    request<SymbolLineage>(
      `/api/repositories/${part(id)}/symbols/${part(symbolId)}/history`,
    ),
  getHistoricalSymbolSource: (
    id: string,
    lineageId: string,
    versionId: string,
  ) =>
    request<HistoricalSymbolSource>(
      `/api/repositories/${part(id)}/lineages/${part(lineageId)}/versions/${part(versionId)}/source`,
    ),
  compareSymbolVersions: (
    id: string,
    lineageId: string,
    fromVersion: string,
    toVersion: string,
  ) =>
    request<SymbolVersionCompare>(
      `/api/repositories/${part(id)}/lineages/${part(lineageId)}/compare?from_version=${part(fromVersion)}&to_version=${part(toVersion)}`,
    ),
  getHistoricalFile: (id: string, path: string, sha: string) =>
    request<HistoricalFileContent>(
      `/api/repositories/${part(id)}/files/content-at?path=${part(path)}&commit_sha=${part(sha)}`,
    ),
  getCommitEvents: (id: string, sha: string) =>
    request<SymbolEvent[]>(
      `/api/repositories/${part(id)}/commits/${part(sha)}/symbols`,
    ),
  syncGitHub: (id: string) =>
    request<Submission>(`/api/repositories/${part(id)}/github/sync`, {
      method: "POST",
    }),
  getGitHubStatus: (id: string) =>
    request<GitHubStatus>(`/api/repositories/${part(id)}/github/status`),
  getPullRequests: (
    id: string,
    filters: {
      state?: string;
      search?: string;
      author?: string;
      label?: string;
      page?: number;
    } = {},
  ) => {
    const query = new URLSearchParams({
      state: filters.state ?? "all",
      page: String(filters.page ?? 1),
      page_size: "50",
    });
    if (filters.search) query.set("search", filters.search);
    if (filters.author) query.set("author", filters.author);
    if (filters.label) query.set("label", filters.label);
    return request<PullRequestPage>(
      `/api/repositories/${part(id)}/pull-requests?${query}`,
    );
  },
  getPullRequest: (id: string, number: number) =>
    request<PullRequestDetail>(
      `/api/repositories/${part(id)}/pull-requests/${number}`,
    ),
  getIssues: (
    id: string,
    filters: {
      state?: string;
      search?: string;
      author?: string;
      label?: string;
      page?: number;
    } = {},
  ) => {
    const query = new URLSearchParams({
      state: filters.state ?? "all",
      page: String(filters.page ?? 1),
      page_size: "50",
    });
    if (filters.search) query.set("search", filters.search);
    if (filters.author) query.set("author", filters.author);
    if (filters.label) query.set("label", filters.label);
    return request<IssuePage>(`/api/repositories/${part(id)}/issues?${query}`);
  },
  getIssue: (id: string, number: number) =>
    request<IssueDetail>(`/api/repositories/${part(id)}/issues/${number}`),
  getCommitContext: (id: string, sha: string) =>
    request<CommitContext>(
      `/api/repositories/${part(id)}/commits/${part(sha)}/context`,
    ),
  getSymbolContext: (id: string, lineageId: string) =>
    request<SymbolContext>(
      `/api/repositories/${part(id)}/lineages/${part(lineageId)}/context`,
    ),
  reindexGraph: (id: string) =>
    request<Submission>(`/api/repositories/${part(id)}/graph/reindex`, {
      method: "POST",
    }),
  getGraphStatus: (id: string) =>
    request<DependencyGraphStatus>(
      `/api/repositories/${part(id)}/graph/status`,
    ),
  getGraph: (
    id: string,
    level: "module" | "file" | "symbol",
    path?: string,
  ) => {
    const query = new URLSearchParams({ level, max_nodes: "300" });
    if (path) query.set("path", path);
    return request<DependencyGraphView>(
      `/api/repositories/${part(id)}/graph?${query}`,
    );
  },
  getGraphNode: (id: string, nodeId: string) =>
    request<DependencyGraphNodeDetail>(
      `/api/repositories/${part(id)}/graph/nodes/${part(nodeId)}`,
    ),
  getGraphMetrics: (id: string) =>
    request<DependencyGraphMetrics>(
      `/api/repositories/${part(id)}/graph/metrics`,
    ),
  getArchitecture: (id: string) =>
    request<ArchitectureResponse>(`/api/repositories/${part(id)}/architecture`),
  getGraphCycles: (id: string, level: "file" | "module" = "file") =>
    request<DependencyCycleResponse>(
      `/api/repositories/${part(id)}/graph/cycles?level=${level}`,
    ),
  getGraphCoupling: (id: string) =>
    request<ChangeCouplingResponse>(
      `/api/repositories/${part(id)}/graph/coupling`,
    ),
  getDependencyPath: (id: string, sourceId: string, targetId: string) =>
    request<DependencyPathResponse>(
      `/api/repositories/${part(id)}/graph/path?source_node_id=${part(sourceId)}&target_node_id=${part(targetId)}`,
    ),
  getImpact: (
    id: string,
    target: { fileId?: string; symbolId?: string; lineageId?: string },
    depth = 3,
  ) => {
    const query = new URLSearchParams({
      depth: String(depth),
      include_coupling: "true",
    });
    if (target.fileId) query.set("file_id", target.fileId);
    if (target.symbolId) query.set("symbol_id", target.symbolId);
    if (target.lineageId) query.set("lineage_id", target.lineageId);
    return request<ImpactResponse>(
      `/api/repositories/${part(id)}/impact?${query}`,
    );
  },
  getAIStatus: () => request<AIStatus>("/api/system/ai-status"),
  getRepositoryAIStatus: (id: string) =>
    request<RepositoryAIStatus>(`/api/repositories/${part(id)}/ai/status`),
  reindexAI: (id: string) =>
    request<Submission>(`/api/repositories/${part(id)}/ai/reindex`, {
      method: "POST",
    }),
  askRepository: (id: string, body: AskContext) =>
    request<AskResponse>(`/api/repositories/${part(id)}/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  getArchaeologyStatus: (id: string) =>
    request<ArchaeologyStatus>(
      `/api/repositories/${part(id)}/archaeology/status`,
    ),
  reindexArchaeology: (id: string) =>
    request<Submission>(`/api/repositories/${part(id)}/archaeology/reindex`, {
      method: "POST",
    }),
  getArchaeologyOverview: (id: string) =>
    request<ArchaeologyOverview>(
      `/api/repositories/${part(id)}/archaeology/overview`,
    ),
  getArchaeologyVolatility: (
    id: string,
    level: "file" | "symbol",
    sort: string,
  ) =>
    request<ArchaeologyVolatility>(
      `/api/repositories/${part(id)}/archaeology/volatility?level=${level}&sort=${part(sort)}&limit=100`,
    ),
  getArchaeologyContributors: (id: string) =>
    request<ArchaeologyContributors>(
      `/api/repositories/${part(id)}/archaeology/contributors`,
    ),
  getArchaeologyRewrites: (id: string) =>
    request<ArchaeologyRewrite[]>(
      `/api/repositories/${part(id)}/archaeology/rewrites`,
    ),
  searchArchaeology: (id: string, q: string, type = "all", status = "all") =>
    request<HistoricalSearchResponse>(
      `/api/repositories/${part(id)}/archaeology/search?q=${part(q)}&type=${part(type)}&status=${part(status)}`,
    ),
  getProvenance: (
    id: string,
    target: { fileId?: string; symbolId?: string; lineageId?: string },
  ) => {
    const query = new URLSearchParams();
    if (target.fileId) query.set("file_id", target.fileId);
    if (target.symbolId) query.set("symbol_id", target.symbolId);
    if (target.lineageId) query.set("lineage_id", target.lineageId);
    return request<ProvenanceResponse>(
      `/api/repositories/${part(id)}/archaeology/provenance?${query}`,
    );
  },
  getArchaeologyDossier: (
    id: string,
    target: { fileId?: string; symbolId?: string; lineageId?: string },
  ) => {
    const query = new URLSearchParams();
    if (target.fileId) query.set("file_id", target.fileId);
    if (target.symbolId) query.set("symbol_id", target.symbolId);
    if (target.lineageId) query.set("lineage_id", target.lineageId);
    return request<ArchaeologyDossier>(
      `/api/repositories/${part(id)}/archaeology/dossier?${query}`,
    );
  },
  getArchitectureHistoryStatus: (id: string) =>
    request<ArchitectureHistoryStatus>(
      `/api/repositories/${part(id)}/architecture/history/status`,
    ),
  reindexArchitectureHistory: (id: string) =>
    request<Submission>(
      `/api/repositories/${part(id)}/architecture/history/reindex`,
      { method: "POST" },
    ),
  getArchitectureSnapshots: (id: string) =>
    request<ArchitectureSnapshot[]>(
      `/api/repositories/${part(id)}/architecture/snapshots?limit=500`,
    ),
  getArchitectureAt: (id: string, sha: string) =>
    request<HistoricalArchitecture>(
      `/api/repositories/${part(id)}/architecture/at/${part(sha)}`,
    ),
  compareArchitecture: (id: string, fromId: string, toId: string) =>
    request<ArchitectureComparison>(
      `/api/repositories/${part(id)}/architecture/compare?from_snapshot_id=${part(fromId)}&to_snapshot_id=${part(toId)}`,
    ),
  getArchitectureEvolution: (
    id: string,
    filters: {
      eventType?: string;
      module?: string;
      component?: string;
      fromDate?: string;
      toDate?: string;
    } = {},
  ) => {
    const query = new URLSearchParams({ limit: "500" });
    if (filters.eventType) query.set("event_type", filters.eventType);
    if (filters.module) query.set("module", filters.module);
    if (filters.component) query.set("component", filters.component);
    if (filters.fromDate) query.set("from_date", filters.fromDate);
    if (filters.toDate) query.set("to_date", filters.toDate);
    return request<ArchitectureEvolutionEvent[]>(
      `/api/repositories/${part(id)}/architecture/evolution?${query}`,
    );
  },
  getArchitectureTrends: (id: string) =>
    request<{
      points: Array<Record<string, number | string>>;
      definitions: Record<string, string>;
    }>(`/api/repositories/${part(id)}/architecture/trends`),
  getArchitectureBaselines: (id: string) =>
    request<ArchitectureBaseline[]>(
      `/api/repositories/${part(id)}/architecture/baselines`,
    ),
  createArchitectureBaseline: (
    id: string,
    body: { name: string; snapshot_id: string; is_default: boolean },
  ) =>
    request<ArchitectureBaseline>(
      `/api/repositories/${part(id)}/architecture/baselines`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      },
    ),
  getArchitectureDrift: (id: string, baselineId?: string) =>
    request<
      ArchitectureComparison & {
        baseline: ArchitectureBaseline;
        policy_violations: ArchitectureViolation[];
      }
    >(
      `/api/repositories/${part(id)}/architecture/drift${baselineId ? `?baseline_id=${part(baselineId)}` : ""}`,
    ),
  getArchitectureRules: (id: string) =>
    request<ArchitectureRule[]>(
      `/api/repositories/${part(id)}/architecture/rules`,
    ),
  createArchitectureRule: (id: string, body: ArchitectureRuleWrite) =>
    request<ArchitectureRule>(
      `/api/repositories/${part(id)}/architecture/rules`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      },
    ),
  previewArchitectureRule: (id: string, rule: ArchitectureRuleWrite) =>
    request<{
      valid: boolean;
      snapshots_evaluated: number;
      source_match_count: number;
      target_match_count: number;
      violation_count: number;
    }>(`/api/repositories/${part(id)}/architecture/rules/validate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ rule }),
    }),
  deleteArchitectureRule: (id: string, ruleId: string) =>
    request<void>(
      `/api/repositories/${part(id)}/architecture/rules/${part(ruleId)}`,
      { method: "DELETE" },
    ),
  getArchitectureViolations: (
    id: string,
    filters: {
      status?: string;
      rule?: string;
      severity?: string;
      fromDate?: string;
      toDate?: string;
    } = {},
  ) => {
    const query = new URLSearchParams({ limit: "500" });
    if (filters.status) query.set("status", filters.status);
    if (filters.rule) query.set("rule", filters.rule);
    if (filters.severity) query.set("severity", filters.severity);
    if (filters.fromDate) query.set("from_date", filters.fromDate);
    if (filters.toDate) query.set("to_date", filters.toDate);
    return request<ArchitectureViolation[]>(
      `/api/repositories/${part(id)}/architecture/violations?${query}`,
    );
  },
  createInvestigation: (
    id: string,
    body: {
      stack_trace?: string;
      error_message?: string;
      known_good_commit?: string;
      known_bad_commit?: string;
      file_path?: string;
      line?: number;
      lineage_id?: string;
    },
  ) =>
    request<Investigation>(`/api/repositories/${part(id)}/investigations`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  getInvestigation: (id: string, investigationId: string) =>
    request<Investigation>(
      `/api/repositories/${part(id)}/investigations/${part(investigationId)}`,
    ),
  getInvestigationCandidates: (id: string, investigationId: string) =>
    request<InvestigationCandidate[]>(
      `/api/repositories/${part(id)}/investigations/${part(investigationId)}/candidates`,
    ),
  explainInvestigation: (
    id: string,
    investigationId: string,
    question: string,
  ) =>
    request<AskResponse>(
      `/api/repositories/${part(id)}/investigations/${part(investigationId)}/explain`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
      },
    ),
  saveInvestigationFeedback: (
    id: string,
    investigationId: string,
    commit: string,
    result: "relevant" | "not_relevant" | "unknown",
  ) =>
    request<{ investigation_id: string; commit_sha: string; result: string }>(
      `/api/repositories/${part(id)}/investigations/${part(investigationId)}/feedback`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ commit_sha: commit, result }),
      },
    ),
  investigateSZZ: (
    id: string,
    body: { fix_commit_sha: string; file_path?: string; lineage_id?: string },
  ) =>
    request<SZZResult>(`/api/repositories/${part(id)}/investigations/szz`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  getLineHistory: (id: string, file: string, line: number, commit?: string) => {
    const query = new URLSearchParams({ path: file, line: String(line) });
    if (commit) query.set("commit_sha", commit);
    return request<LineHistoryResult>(
      `/api/repositories/${part(id)}/line-history?${query}`,
    );
  },
  createBisect: (id: string, knownGood: string, knownBad: string) =>
    request<BisectSession>(
      `/api/repositories/${part(id)}/investigations/bisect`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ known_good: knownGood, known_bad: knownBad }),
      },
    ),
  classifyBisect: (
    id: string,
    bisectId: string,
    commit: string,
    result: "good" | "bad" | "unknown",
  ) =>
    request<BisectSession>(
      `/api/repositories/${part(id)}/investigations/bisect/${part(bisectId)}/classify`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ commit_sha: commit, result }),
      },
    ),
};
export function errorMessage(error: unknown): string {
  return error instanceof ApiError
    ? error.message
    : "The request could not be completed. Please retry.";
}
