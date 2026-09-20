"use client";
import {
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query";
import { api } from "@/lib/api";

export function useRepository(id: string) {
  return useQuery({
    queryKey: ["repository", id],
    queryFn: () => api.getRepository(id),
    refetchInterval: (query) =>
      query.state.data && !["ready", "failed"].includes(query.state.data.status)
        ? 3000
        : false,
  });
}
export function useAnalysisJob(id: string | null) {
  return useQuery({
    queryKey: ["job", id],
    queryFn: () => api.getAnalysisJob(id!),
    enabled: Boolean(id),
    refetchInterval: (query) =>
      ["completed", "failed"].includes(query.state.data?.status ?? "")
        ? false
        : Math.min(2000 * (1 + query.state.fetchFailureCount), 10000),
  });
}
export function invalidateRepository(client: QueryClient, id: string) {
  return client.invalidateQueries({
    predicate: (query) =>
      query.queryKey[1] === id && query.queryKey[0] !== "job",
  });
}
export function useCreateRepository() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: api.createRepository,
    retry: false,
    onSuccess: (result) => invalidateRepository(client, result.repository_id),
  });
}
export function useRefreshRepository() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: api.refreshRepository,
    retry: false,
    onSuccess: (result) => invalidateRepository(client, result.repository_id),
  });
}
export function useCommits(id: string, page: number) {
  return useQuery({
    queryKey: ["commits", id, page],
    queryFn: () => api.getCommits(id, page),
  });
}
export function useCommit(id: string, sha: string) {
  return useQuery({
    queryKey: ["commit", id, sha],
    queryFn: () => api.getCommit(id, sha),
  });
}
export function useRepositoryStats(id: string, enabled: boolean) {
  return useQuery({
    queryKey: ["repository-stats", id],
    queryFn: () => api.getRepositoryStats(id),
    enabled,
  });
}
export function useRepositorySystemStatus(id: string, enabled = true) {
  return useQuery({
    queryKey: ["repository-system-status", id],
    queryFn: () => api.getRepositorySystemStatus(id),
    enabled,
    refetchInterval: (query) =>
      Object.values(query.state.data ?? {}).some(
        (value) =>
          typeof value === "object" &&
          value !== null &&
          "status" in value &&
          ["indexing", "queued", "pending", "syncing"].includes(
            String(value.status),
          ),
      )
        ? 3000
        : false,
  });
}
export function useCodeStats(id: string, enabled = true) {
  return useQuery({
    queryKey: ["code-stats", id],
    queryFn: () => api.getCodeStats(id),
    enabled,
  });
}
export function useFileTree(id: string, enabled = true) {
  return useQuery({
    queryKey: ["files", id],
    queryFn: () => api.getFiles(id),
    enabled,
  });
}
export function useFile(id: string, path: string | null) {
  return useQuery({
    queryKey: ["file", id, path],
    queryFn: () => api.getFile(id, path!),
    enabled: Boolean(path),
  });
}
export function useFileContent(id: string, path: string | null) {
  return useQuery({
    queryKey: ["file-content", id, path],
    queryFn: () => api.getFileContent(id, path!),
    enabled: Boolean(path),
  });
}
export function useHistoryStatus(id: string) {
  return useQuery({
    queryKey: ["history-status", id],
    queryFn: () => api.getHistoryStatus(id),
    refetchInterval: (query) =>
      ["queued", "indexing"].includes(query.state.data?.status ?? "")
        ? 2000
        : false,
  });
}
export function useHistoryEvents(
  id: string,
  filters: {
    symbolKind?: string;
    filePath?: string;
    author?: string;
    page?: number;
  },
  enabled = true,
) {
  return useQuery({
    queryKey: ["history-events", id, filters],
    queryFn: () => api.getHistoryEvents(id, filters),
    enabled,
  });
}
export function useLineage(id: string, lineageId: string) {
  return useQuery({
    queryKey: ["lineage", id, lineageId],
    queryFn: () => api.getLineage(id, lineageId),
  });
}
export function useHistoryReindex() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: api.reindexHistory,
    retry: false,
    onSuccess: (result) => invalidateRepository(client, result.repository_id),
  });
}
export function useFileSymbols(id: string, path: string | null) {
  return useQuery({
    queryKey: ["file-symbols", id, path],
    queryFn: () => api.getFileSymbols(id, path!),
    enabled: Boolean(path),
  });
}
export function useSymbolSearch(id: string, search: string) {
  return useQuery({
    queryKey: ["symbol-search", id, search],
    queryFn: () => api.searchSymbols(id, search),
    enabled: search.trim().length >= 2,
  });
}
export function useCodeReindex() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: api.reindexCode,
    retry: false,
    onSuccess: (result) => invalidateRepository(client, result.repository_id),
  });
}
export function useGitHubStatus(id: string) {
  return useQuery({
    queryKey: ["github-status", id],
    queryFn: () => api.getGitHubStatus(id),
    refetchInterval: (query) =>
      ["queued", "syncing"].includes(query.state.data?.status ?? "")
        ? 2000
        : false,
  });
}
export function useGitHubSync() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: api.syncGitHub,
    retry: false,
    onSuccess: (result) => invalidateRepository(client, result.repository_id),
  });
}
export function usePullRequests(
  id: string,
  filters: {
    state?: string;
    search?: string;
    author?: string;
    label?: string;
    page?: number;
  },
  enabled = true,
) {
  return useQuery({
    queryKey: ["pull-requests", id, filters],
    queryFn: () => api.getPullRequests(id, filters),
    enabled,
  });
}
export function usePullRequest(id: string, number: number) {
  return useQuery({
    queryKey: ["pull-request", id, number],
    queryFn: () => api.getPullRequest(id, number),
  });
}
export function useIssues(
  id: string,
  filters: {
    state?: string;
    search?: string;
    author?: string;
    label?: string;
    page?: number;
  },
  enabled = true,
) {
  return useQuery({
    queryKey: ["issues", id, filters],
    queryFn: () => api.getIssues(id, filters),
    enabled,
  });
}
export function useIssue(id: string, number: number) {
  return useQuery({
    queryKey: ["issue", id, number],
    queryFn: () => api.getIssue(id, number),
  });
}

export function useGraphStatus(id: string) {
  return useQuery({
    queryKey: ["graph-status", id],
    queryFn: () => api.getGraphStatus(id),
    refetchInterval: (query) =>
      ["queued", "indexing"].includes(query.state.data?.status ?? "")
        ? 1500
        : false,
  });
}

export function useGraphReindex() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: api.reindexGraph,
    retry: false,
    onSuccess: (result) => invalidateRepository(client, result.repository_id),
  });
}

export function useAIStatus() {
  return useQuery({
    queryKey: ["ai-status"],
    queryFn: api.getAIStatus,
    refetchInterval: 15000,
  });
}

export function useRepositoryAIStatus(id: string) {
  return useQuery({
    queryKey: ["repository-ai-status", id],
    queryFn: () => api.getRepositoryAIStatus(id),
    refetchInterval: (query) =>
      ["queued", "indexing"].includes(query.state.data?.status ?? "")
        ? 1500
        : 15000,
  });
}

export function useAIReindex() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: api.reindexAI,
    retry: false,
    onSuccess: (result) => invalidateRepository(client, result.repository_id),
  });
}

export function useAskRepository() {
  return useMutation({
    mutationFn: ({
      id,
      body,
    }: {
      id: string;
      body: Parameters<typeof api.askRepository>[1];
    }) => api.askRepository(id, body),
    retry: false,
  });
}

export function useArchaeologyStatus(id: string) {
  return useQuery({
    queryKey: ["archaeology-status", id],
    queryFn: () => api.getArchaeologyStatus(id),
    refetchInterval: (query) =>
      ["pending", "indexing"].includes(query.state.data?.status ?? "")
        ? 1500
        : false,
  });
}

export function useArchaeologyReindex() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: api.reindexArchaeology,
    retry: false,
    onSuccess: (result) => invalidateRepository(client, result.repository_id),
  });
}

export function useArchaeologyOverview(id: string, enabled: boolean) {
  return useQuery({
    queryKey: ["archaeology-overview", id],
    queryFn: () => api.getArchaeologyOverview(id),
    enabled,
  });
}

export function useArchaeologyVolatility(
  id: string,
  level: "file" | "symbol",
  sort: string,
  enabled: boolean,
) {
  return useQuery({
    queryKey: ["archaeology-volatility", id, level, sort],
    queryFn: () => api.getArchaeologyVolatility(id, level, sort),
    enabled,
  });
}

export function useArchaeologyContributors(id: string, enabled: boolean) {
  return useQuery({
    queryKey: ["archaeology-contributors", id],
    queryFn: () => api.getArchaeologyContributors(id),
    enabled,
  });
}

export function useArchaeologyRewrites(id: string, enabled: boolean) {
  return useQuery({
    queryKey: ["archaeology-rewrites", id],
    queryFn: () => api.getArchaeologyRewrites(id),
    enabled,
  });
}

export function useHistoricalSearch(
  id: string,
  search: string,
  type: string,
  status: string,
  enabled: boolean,
) {
  return useQuery({
    queryKey: ["archaeology-search", id, search, type, status],
    queryFn: () => api.searchArchaeology(id, search, type, status),
    enabled: enabled && search.trim().length > 0,
  });
}
