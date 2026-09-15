export interface Repository {
  id: string;
  provider: string;
  owner: string;
  name: string;
  full_name: string;
  url: string;
  default_branch: string | null;
  status: string;
  head_sha: string | null;
  commit_count: number;
  indexed_at: string | null;
  last_refreshed_at: string | null;
  indexing_error: string | null;
  history_rewritten: boolean;
  history_index_status: string;
  history_indexed_through_sha: string | null;
  history_limited: boolean;
  history_stale: boolean;
  history_indexed_commit_count: number;
  history_total_commit_count: number;
  active_job_id: string | null;
}
export interface AnalysisJob {
  id: string;
  repository_id: string | null;
  status: "queued" | "running" | "completed" | "failed";
  job_type: string;
  current_step: string | null;
  progress: number | null;
  error_message: string | null;
}
export interface Submission {
  repository_id: string;
  job_id: string | null;
  status: "queued" | "running" | "ready";
}
export interface CommitSummary {
  sha: string;
  short_sha: string;
  message: string;
  author_name: string;
  authored_at: string;
  committed_at: string;
  is_merge_commit: boolean;
  files_changed: number;
  insertions: number;
  deletions: number;
}
export interface FileChange {
  id: string;
  old_path: string | null;
  new_path: string | null;
  change_type: string;
  additions: number | null;
  deletions: number | null;
  similarity_score: number | null;
}
export interface CommitDetail extends CommitSummary {
  parents: string[];
  changes: FileChange[];
}
export interface CommitPage {
  items: CommitSummary[];
  page: number;
  page_size: number;
  total: number;
}
export interface RepositoryStats {
  total_commits: number;
  merge_commits: number;
  contributors: number;
  historical_paths: number;
  insertions: number;
  deletions: number;
  first_commit_at: string | null;
  latest_commit_at: string | null;
}
export interface Tag {
  name: string;
  target_sha: string;
  annotated: boolean;
}
export interface Diff {
  content: string;
  truncated: boolean;
}
export interface LanguageStats {
  language: string;
  files: number;
  lines: number;
  percentage: number;
}
export interface CodeStats {
  total_files: number;
  source_files: number;
  parsed_files: number;
  unsupported_files: number;
  failed_files: number;
  total_lines: number;
  symbol_count: number;
  functions: number;
  classes: number;
  methods: number;
  languages: LanguageStats[];
}
export interface FileTreeNode {
  name: string;
  path: string;
  type: "directory" | "file";
  language: string | null;
  size_bytes: number | null;
  parse_status: string | null;
  children: FileTreeNode[];
}
export interface RepositoryFile {
  id: string;
  path: string;
  filename: string;
  extension: string;
  language: string | null;
  blob_sha: string;
  size_bytes: number;
  line_count: number | null;
  is_binary: boolean;
  parse_status: string;
  syntax_error_count: number;
  indexed_commit_sha: string;
}
export interface FileContent {
  path: string;
  content: string;
  start_line: number;
  end_line: number;
  total_lines: number;
  truncated: boolean;
}
export interface CodeSymbol {
  id: string;
  file_id: string;
  parent_symbol_id: string | null;
  lineage_id: string | null;
  name: string;
  qualified_name: string;
  kind: string;
  signature: string | null;
  start_line: number;
  end_line: number;
  start_column: number;
  end_column: number;
  visibility: string | null;
  is_async: boolean;
  is_static: boolean;
  documentation: string | null;
  metadata: Record<string, unknown> | null;
  file_path: string | null;
  language: string | null;
}
export interface SymbolPage {
  items: CodeSymbol[];
  page: number;
  page_size: number;
  total: number;
}

export interface HistoryCommit {
  sha: string;
  short_sha: string;
  message: string;
  author_name: string;
  authored_at: string;
  committed_at: string;
  is_merge_commit: boolean;
}
export interface HistoryStatus {
  status: string;
  progress: number | null;
  current_step: string | null;
  indexed_commits: number;
  total_commits: number;
  lineages: number;
  versions: number;
  events: number;
  history_limited: boolean;
  history_stale: boolean;
  last_indexed_sha: string | null;
  job_id: string | null;
}
export interface SymbolVersion {
  id: string;
  lineage_id: string;
  file_path: string;
  language: string | null;
  name: string;
  qualified_name: string;
  kind: string;
  signature: string | null;
  start_line: number;
  end_line: number;
  start_column: number;
  end_column: number;
  documentation: string | null;
  match_type: string;
  match_confidence: number;
  matching_metadata: Record<string, unknown> | null;
  source_truncated: boolean;
  commit: HistoryCommit;
}
export interface SymbolEvent {
  id: string;
  lineage_id: string;
  event_type: string;
  previous_version_id: string | null;
  new_version_id: string | null;
  summary_data: Record<string, unknown> | null;
  commit: HistoryCommit;
  symbol_name: string;
  symbol_kind: string;
  file_path: string | null;
  deterministic_label: string;
}
export interface HistoryEventPage {
  items: SymbolEvent[];
  page: number;
  page_size: number;
  total: number;
}
export interface SymbolLineage {
  id: string;
  current_name: string | null;
  current_qualified_name: string | null;
  current_file_path: string | null;
  symbol_kind: string;
  is_deleted: boolean;
  introduced_commit: HistoryCommit | null;
  last_seen_commit: HistoryCommit | null;
  deleted_commit: HistoryCommit | null;
  latest_version: SymbolVersion | null;
  versions: SymbolVersion[];
  events: SymbolEvent[];
  previous_names: string[];
  file_paths: string[];
}
export interface LineageSearchItem {
  lineage_id: string;
  current_name: string | null;
  current_qualified_name: string | null;
  current_file_path: string | null;
  symbol_kind: string;
  is_deleted: boolean;
  previous_names: string[];
}
export interface LineageSearchPage {
  items: LineageSearchItem[];
  page: number;
  page_size: number;
  total: number;
}
export interface HistoricalSymbolSource {
  version_id: string;
  commit_sha: string;
  file_path: string;
  start_line: number;
  end_line: number;
  language: string | null;
  source: string;
  retrieved_from_git: boolean;
}
export interface SymbolVersionCompare {
  from_version: string;
  to_version: string;
  old_source: string;
  new_source: string;
  old_name: string;
  new_name: string;
  old_path: string;
  new_path: string;
  old_signature: string | null;
  new_signature: string | null;
  old_lines: [number, number];
  new_lines: [number, number];
  diff: string;
  truncated: boolean;
}
export interface HistoricalFileContent {
  path: string;
  commit_sha: string;
  content: string;
  language: string | null;
  total_lines: number;
  historical: true;
}

export interface GitHubStatus {
  status: string;
  progress: number | null;
  current_step: string | null;
  last_synced_at: string | null;
  pull_requests_indexed: number;
  issues_indexed: number;
  comments_indexed: number;
  review_comments_indexed: number;
  rate_limit_remaining: number | null;
  rate_limit_reset_at: string | null;
  sync_error: string | null;
  github_index_limited: boolean;
  job_id: string | null;
}
export interface GitHubLabel {
  name: string;
  description: string | null;
  color: string | null;
}
export interface GitHubComment {
  id: string;
  comment_type: "issue_comment" | "pr_comment" | "review_comment";
  author_login: string | null;
  body: string | null;
  created_at: string;
  updated_at: string;
  html_url: string;
  path: string | null;
  commit_sha: string | null;
  original_commit_sha: string | null;
  line: number | null;
  original_line: number | null;
  side: string | null;
  diff_hunk: string | null;
}
export interface PullRequestSummary {
  id: string;
  number: number;
  title: string;
  state: string;
  draft: boolean;
  merged: boolean;
  author_login: string | null;
  created_at: string;
  updated_at: string;
  merged_at: string | null;
  closed_at: string | null;
  html_url: string;
  commits_count: number;
  labels: GitHubLabel[];
}
export interface PullRequestPage {
  items: PullRequestSummary[];
  page: number;
  page_size: number;
  total: number;
}
export interface IssueSummary {
  id: string;
  number: number;
  title: string;
  state: string;
  author_login: string | null;
  created_at: string;
  updated_at: string;
  closed_at: string | null;
  html_url: string;
  milestone: string | null;
  labels: GitHubLabel[];
}
export interface IssuePage {
  items: IssueSummary[];
  page: number;
  page_size: number;
  total: number;
}
export interface AffectedSymbol {
  lineage_id: string;
  name: string;
  symbol_kind: string;
  file_path: string | null;
  event_type: string;
  commit_sha: string;
}
export interface IssueReference {
  issue: IssueSummary | null;
  owner: string;
  repository: string;
  number: number;
  reference_type: string;
  raw_reference: string;
  confidence: number;
  external: boolean;
}
export interface PullRequestDetail extends PullRequestSummary {
  body: string | null;
  base_branch: string;
  head_branch: string;
  merge_commit_sha: string | null;
  additions: number;
  deletions: number;
  changed_files: number;
  comments_count: number;
  review_comments_count: number;
  commits: CommitSummary[];
  commit_shas: string[];
  linked_issues: IssueReference[];
  comments: GitHubComment[];
  review_comments: GitHubComment[];
  affected_symbols: AffectedSymbol[];
}
export interface RelatedPullRequest {
  pull_request: PullRequestSummary;
  relationship: string;
  confidence: number;
}
export interface IssueDetail extends IssueSummary {
  body: string | null;
  comments_count: number;
  comments: GitHubComment[];
  related_pull_requests: RelatedPullRequest[];
  related_commits: CommitSummary[];
  affected_symbols: AffectedSymbol[];
}
export interface CommitContext {
  commit: CommitSummary;
  associated_pull_requests: PullRequestSummary[];
  referenced_issues: IssueReference[];
  symbol_changes: SymbolEvent[];
}
export interface SymbolContextEvent {
  event: SymbolEvent;
  commit: CommitSummary;
  pull_requests: PullRequestSummary[];
  issues: IssueReference[];
  comments: GitHubComment[];
}
export interface SymbolContext {
  lineage_id: string;
  events: SymbolContextEvent[];
}

export interface DependencyGraphNode {
  id: string;
  node_type: string;
  name: string;
  qualified_name: string;
  file_id: string | null;
  symbol_id: string | null;
  path: string | null;
  language: string | null;
  lineage_id: string | null;
  layer: string | null;
  metrics: Record<string, number>;
  metadata: Record<string, unknown>;
}
export interface DependencyGraphEdge {
  id: string;
  source_node_id: string;
  target_node_id: string;
  edge_type: string;
  weight: number;
  confidence: number;
  resolution_type: string;
  metadata: Record<string, unknown>;
}
export interface DependencyGraphView {
  level: "module" | "file" | "symbol";
  nodes: DependencyGraphNode[];
  edges: DependencyGraphEdge[];
  limited: boolean;
  graph_stale: boolean;
}
export interface DependencyGraphStatus {
  status: string;
  progress: number | null;
  current_step: string | null;
  nodes: number;
  edges: number;
  cycles: number;
  components: number;
  last_indexed_sha: string | null;
  graph_stale: boolean;
  graph_limited: boolean;
  error: string | null;
  job_id: string | null;
  completed_at: string | null;
}
export interface DependencyGraphMetrics {
  nodes: number;
  edges: number;
  files: number;
  symbols: number;
  modules: number;
  external_dependencies: number;
  cycles: number;
  dependency_relationships: number;
  edge_counts: Record<string, number>;
  relationship_levels: Record<string, number>;
  average_fan_in: number;
  average_fan_out: number;
  top_fan_in: DependencyGraphNode[];
  top_fan_out: DependencyGraphNode[];
  top_hotspots: DependencyGraphNode[];
  hotspot_tie_count: number;
  hotspot_formula: string;
  normalization_note: string;
}
export interface ArchitectureComponent {
  id: string;
  name: string;
  path: string;
  component_type: string;
  layer: string | null;
  confidence: number | null;
  node_count: number;
}
export interface ArchitectureResponse {
  label: string;
  components: ArchitectureComponent[];
  component_dependencies: Array<{
    source_component_id: string;
    target_component_id: string;
    weight: number;
  }>;
  layers: Record<string, number>;
  metrics: DependencyGraphMetrics;
  graph_stale: boolean;
}
export interface DependencyGraphNodeDetail {
  node: DependencyGraphNode;
  incoming_edges: DependencyGraphEdge[];
  outgoing_edges: DependencyGraphEdge[];
  component: string | null;
  layer: string | null;
}
export interface DependencyCycle {
  cycle_id: number;
  members: DependencyGraphNode[];
  edges: DependencyGraphEdge[];
  size: number;
}
export interface DependencyCycleResponse {
  level: "file" | "module";
  cycles: DependencyCycle[];
}
export interface ChangeCouplingResponse {
  level: "file";
  pairs: Array<{
    source: DependencyGraphNode;
    target: DependencyGraphNode;
    co_changes: number;
    coupling_score: number;
  }>;
  formula: string;
  diagnostics: {
    commits_examined: number;
    commits_used: number;
    commits_excluded_large: number;
    candidate_pairs: number;
    pairs_after_filtering: number;
  };
}
export interface DependencyPathResponse {
  found: boolean;
  path: DependencyGraphNode[];
  edges: DependencyGraphEdge[];
  length: number | null;
}
export interface ImpactResponse {
  wording: string;
  target: DependencyGraphNode;
  direct_dependencies: DependencyGraphNode[];
  direct_dependents: DependencyGraphNode[];
  transitive_dependents: DependencyGraphNode[];
  callers: DependencyGraphNode[];
  callees: DependencyGraphNode[];
  change_coupled_nodes: DependencyGraphNode[];
  paths: Array<{
    distance: number;
    nodes: DependencyGraphNode[];
    edges: DependencyGraphEdge[];
    confidence: number;
  }>;
  metrics: Record<string, number>;
}

export interface AIStatus {
  provider: "ollama";
  available: boolean;
  base_url_safe: string;
  llm_model: string;
  llm_model_available: boolean;
  embedding_model: string;
  embedding_model_available: boolean;
  message: string | null;
}
export interface RepositoryAIStatus {
  status: string;
  progress: number | null;
  current_step: string | null;
  documents: number;
  embedded_documents: number;
  embedding_model: string | null;
  embedding_dimension: number | null;
  last_indexed_sha: string | null;
  index_stale: boolean;
  ollama_available: boolean;
  error: string | null;
  job_id: string | null;
  completed_at: string | null;
}
export interface AskContext {
  question: string;
  lineage_id?: string;
  symbol_id?: string;
  file_path?: string;
  start_line?: number;
  end_line?: number;
  commit_sha?: string;
  pull_request_number?: number;
  issue_number?: number;
  selected_source?: string;
  conversation?: Array<{ role: "user" | "assistant"; content: string }>;
}
export interface AIEvidence {
  id: string;
  type: string;
  title: string;
  text: string;
  source_id: string | null;
  source_url: string | null;
  commit_sha: string | null;
  file_path: string | null;
  symbol_lineage_id: string | null;
  pr_number: number | null;
  issue_number: number | null;
  score: number;
  relationship: string;
  retrieval_reason: string;
  metadata: Record<string, unknown>;
}
export interface AIClaim {
  text: string;
  evidence_ids: string[];
}
export interface AskResponse {
  answer: string;
  claims: AIClaim[];
  confidence: "high" | "medium" | "low";
  evidence_sufficiency: "strong" | "moderate" | "weak" | "insufficient";
  evidence: AIEvidence[];
  limitations: string[];
  cached: boolean;
  diagnostics: Record<string, unknown> | null;
}

export interface ArchaeologyStatus {
  status: string;
  progress: number | null;
  step: string | null;
  files_processed: number;
  symbols_processed: number;
  rewrites_detected: number;
  copy_candidates: number;
  contributors: number;
  last_indexed_sha: string | null;
  stale: boolean;
  error: string | null;
  job_id: string | null;
  completed_at: string | null;
}
export interface ArchaeologyTarget {
  entity_type: "file" | "symbol";
  entity_id: string;
  current_file_id: string | null;
  name: string;
  path: string | null;
  kind: string | null;
  status: string;
  introduced_at: string | null;
  last_modified_at: string | null;
  age_days: number;
  days_since_last_change: number;
  change_count: number;
  churn: number;
  contributor_count: number;
  rename_count: number;
  move_count: number;
  rewrite_count: number;
  changes_last_30_days: number;
  changes_last_90_days: number;
  changes_last_180_days: number;
  volatility: number;
  stability: number;
  classification: string;
  metadata: Record<string, unknown>;
}
export interface ArchaeologyOverview {
  repository_age_days: number | null;
  total_historical_files: number;
  current_files: number;
  deleted_files: number;
  current_symbols: number;
  deleted_symbols: number;
  renamed_symbols: number;
  moved_symbols: number;
  major_rewrites: number;
  contributors: number;
  median_symbol_age_days: number | null;
  median_file_age_days: number | null;
  most_changed_files: ArchaeologyTarget[];
  oldest_current_symbols: ArchaeologyTarget[];
  recently_rewritten_symbols: ArchaeologyTarget[];
  age_buckets: Record<string, number>;
  volatility_formula: string;
  stability_formula: string;
  canonical_date: string;
  merge_commit_policy: string;
  knowledge_concentration: Record<string, unknown>;
}
export interface ArchaeologyVolatility {
  level: "file" | "symbol";
  items: ArchaeologyTarget[];
  volatility_formula: string;
  stability_formula: string;
}
export interface ArchaeologyContributor {
  identity_key: string;
  display_name: string;
  commit_count: number;
  files_touched: number;
  symbols_touched: number;
  lines_changed: number;
  first_activity: string;
  last_activity: string;
  knowledge_score: number | null;
  contribution_share: number | null;
  introduced: boolean;
  evidence: Record<string, unknown>;
}
export interface ArchaeologyContributors {
  items: ArchaeologyContributor[];
  concentration: Record<string, unknown>;
  interpretation: string;
}
export interface ArchaeologyRewrite {
  id: string;
  lineage_id: string;
  symbol: string;
  file_path: string;
  commit_id: string;
  commit_sha: string;
  committed_at: string;
  similarity: number;
  lines_added: number;
  lines_deleted: number;
  reason: string;
  evidence: Record<string, unknown>;
  old_version_id: string;
  new_version_id: string;
}
export interface HistoricalSearchItem {
  entity_type: string;
  entity_id: string | null;
  name: string;
  historical_name: string | null;
  kind: string | null;
  file_path: string | null;
  commit_sha: string | null;
  commit_id: string | null;
  status: string;
  lineage_id: string | null;
  version_id: string | null;
  matched_reason: string;
  match_type: "exact" | "lexical" | "semantic";
  source_available: boolean;
}
export interface HistoricalSearchResponse {
  items: HistoricalSearchItem[];
  page: number;
  page_size: number;
  total: number;
}
export interface ProvenanceResponse {
  entity_type: string;
  entity_id: string;
  origin: Record<string, unknown>;
  current_identity: Record<string, unknown>;
  status: string;
  timeline: Array<Record<string, unknown>>;
  renames: Array<Record<string, unknown>>;
  moves: Array<Record<string, unknown>>;
  rewrites: Array<Record<string, unknown>>;
  contributors: ArchaeologyContributor[];
}
export interface RelatedCode {
  candidate_lineage_id: string;
  candidate_name: string;
  candidate_path: string;
  commit_sha: string;
  similarity: number;
  relationship: string;
  confidence: number;
  evidence: Record<string, unknown>;
  status: string;
}
export interface ArchaeologyDossier {
  target: ArchaeologyTarget;
  provenance: ProvenanceResponse;
  activity: Record<string, unknown>;
  contributors: ArchaeologyContributors;
  development_context: Record<string, unknown>;
  dependencies: Record<string, unknown>;
  related_code: RelatedCode[];
  limitations: string[];
}

export interface ArchitectureHistoryStatus {
  status: string;
  progress: number | null;
  current_step: string | null;
  commits_examined: number;
  snapshots_created: number;
  events_detected: number;
  cycles_detected: number;
  violations_detected: number;
  last_indexed_sha: string | null;
  stale: boolean;
  limited: boolean;
  error: string | null;
  job_id: string | null;
  completed_at: string | null;
}
export interface ArchitectureSnapshot {
  id: string;
  commit_sha: string;
  short_sha: string;
  committed_at: string;
  tags: string[];
  node_count: number;
  edge_count: number;
  module_count: number;
  component_count: number;
  cycle_count: number;
  metrics: Record<string, number | string>;
}
export interface HistoricalArchitectureNode {
  stable_key: string;
  node_type: "module" | "component";
  name: string;
  path: string | null;
  layer: string | null;
  confidence: number;
  metrics: Record<string, number>;
}
export interface HistoricalArchitectureEdge {
  source: string;
  target: string;
  edge_type: string;
  weight: number;
  confidence: number;
}
export interface HistoricalArchitecture {
  snapshot: ArchitectureSnapshot;
  nodes: HistoricalArchitectureNode[];
  edges: HistoricalArchitectureEdge[];
  cycles: Array<{ fingerprint: string; members: string[] }>;
  metrics: Record<string, number | string>;
  source: "deterministic_static_analysis";
}
export interface ArchitectureComparison {
  from_snapshot: ArchitectureSnapshot;
  to_snapshot: ArchitectureSnapshot;
  nodes_added: HistoricalArchitectureNode[];
  nodes_removed: HistoricalArchitectureNode[];
  nodes_changed: Array<Record<string, unknown>>;
  edges_added: HistoricalArchitectureEdge[];
  edges_removed: HistoricalArchitectureEdge[];
  edges_changed: Array<Record<string, unknown>>;
  cycles_introduced: Array<{ fingerprint: string; members: string[] }>;
  cycles_resolved: Array<{ fingerprint: string; members: string[] }>;
  metrics_before: Record<string, number | string>;
  metrics_after: Record<string, number | string>;
  evolution_events: Array<{ event_type: string; value: Record<string, unknown> }>;
  structural_drift: {
    score: number;
    formula: string;
    interpretation: string;
  };
}
export interface ArchitectureEvolutionEvent {
  id: string;
  event_type: string;
  commit_sha: string;
  committed_at: string;
  source: string | null;
  target: string | null;
  development_context: {
    pull_requests: Array<{ number: number; title: string; html_url: string }>;
    issues: Array<{ number: number; title: string; html_url: string }>;
  };
}
export interface ArchitectureBaseline {
  id: string;
  name: string;
  snapshot_id: string;
  is_default: boolean;
  created_at: string;
}
export interface ArchitectureSelector {
  kind: "layer" | "component" | "path_prefix" | "module";
  value: string;
}
export interface ArchitectureRuleWrite {
  name: string;
  description?: string;
  rule_type: "allowed_dependency" | "forbidden_dependency" | "forbidden_cycle";
  source_selector: ArchitectureSelector;
  target_selector?: ArchitectureSelector;
  severity: "info" | "warning" | "error";
  enabled: boolean;
}
export interface ArchitectureRule extends ArchitectureRuleWrite {
  id: string;
  repository_id: string;
  created_at: string;
  updated_at: string;
}
export interface ArchitectureViolation {
  id: string;
  rule_id: string;
  rule_name: string;
  rule_type: string;
  severity: string;
  status: "active" | "resolved";
  source: string;
  target: string;
  introduced_commit_sha: string;
  resolved_commit_sha: string | null;
  introduced_at: string;
  resolved_at: string | null;
  lifetime_days: number | null;
  confidence: number;
}
