"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  useArchaeologyContributors,
  useArchaeologyOverview,
  useArchaeologyReindex,
  useArchaeologyRewrites,
  useArchaeologyStatus,
  useArchaeologyVolatility,
  useHistoricalSearch,
  useRepository,
} from "@/hooks/use-repository";
import { api, errorMessage } from "@/lib/api";
import { dateLabel } from "@/lib/repository";
import type { ArchaeologyTarget } from "@/types/repository";
import { QueryError } from "./workspace";
import { RepositoryNav } from "./repository-nav";

type Tab =
  | "Overview"
  | "Code Age"
  | "Volatility"
  | "Contributors"
  | "Rewrites"
  | "Deleted Code"
  | "Search History";

const tabs: Tab[] = [
  "Overview",
  "Code Age",
  "Volatility",
  "Contributors",
  "Rewrites",
  "Deleted Code",
  "Search History",
];

function days(value: number | null) {
  if (value === null) return "Unknown";
  if (value >= 365) return `${(value / 365).toFixed(1)} years`;
  return `${value} days`;
}

function TargetTable({
  rows,
  open,
}: {
  rows: ArchaeologyTarget[];
  open: (row: ArchaeologyTarget) => void;
}) {
  return rows.length ? (
    <div className="archaeology-table-wrap">
      <table className="archaeology-table">
        <thead>
          <tr>
            <th>Target</th>
            <th>Status</th>
            <th>Age</th>
            <th>Changes</th>
            <th>Churn</th>
            <th>Contributors</th>
            <th>Volatility</th>
            <th>Stability</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={`${row.entity_type}-${row.entity_id}`}>
              <td>
                <button className="table-link" onClick={() => open(row)}>
                  {row.name}
                </button>
                <small>{row.path}</small>
              </td>
              <td>
                <span className="badge">
                  {row.classification.replaceAll("_", " ")}
                </span>
              </td>
              <td>{days(row.age_days)}</td>
              <td>{row.change_count}</td>
              <td>{row.churn}</td>
              <td>{row.contributor_count}</td>
              <td>{row.volatility.toFixed(2)}</td>
              <td>{row.stability.toFixed(2)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  ) : (
    <p className="muted">No matching historical entities.</p>
  );
}

export function Archaeology({
  repoId,
  initialLineageId,
}: {
  repoId: string;
  initialLineageId?: string;
}) {
  const repository = useRepository(repoId);
  const status = useArchaeologyStatus(repoId);
  const ready = status.data?.status === "ready" && !status.data.stale;
  const overview = useArchaeologyOverview(repoId, ready);
  const [tab, setTab] = useState<Tab>("Overview");
  const [level, setLevel] = useState<"file" | "symbol">("symbol");
  const [sort, setSort] = useState("volatility");
  const volatility = useArchaeologyVolatility(repoId, level, sort, ready);
  const contributors = useArchaeologyContributors(repoId, ready);
  const rewrites = useArchaeologyRewrites(repoId, ready);
  const reindex = useArchaeologyReindex();
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [searchType, setSearchType] = useState("all");
  const [searchStatus, setSearchStatus] = useState("all");
  const effectiveType =
    tab === "Deleted Code" && searchType === "all"
      ? "deleted_symbol"
      : searchType;
  const effectiveStatus = tab === "Deleted Code" ? "deleted" : searchStatus;
  const search = useHistoricalSearch(
    repoId,
    debounced,
    effectiveType,
    effectiveStatus,
    ready,
  );
  const [selected, setSelected] = useState<ArchaeologyTarget | null>(null);
  const [selectedLineage, setSelectedLineage] = useState(
    initialLineageId ?? null,
  );
  const dossier = useQuery({
    queryKey: [
      "archaeology-dossier",
      repoId,
      selected?.entity_type,
      selected?.entity_id,
      selectedLineage,
    ],
    queryFn: () =>
      api.getArchaeologyDossier(
        repoId,
        selectedLineage
          ? { lineageId: selectedLineage }
          : selected!.entity_type === "symbol"
            ? { lineageId: selected!.entity_id }
            : { fileId: selected!.current_file_id! },
      ),
    enabled:
      ready &&
      Boolean(
        selectedLineage ||
        (selected &&
          (selected.entity_type === "symbol" || selected.current_file_id)),
      ),
  });
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(query.trim()), 250);
    return () => window.clearTimeout(timer);
  }, [query]);

  if (repository.isError)
    return (
      <QueryError error={repository.error} retry={() => repository.refetch()} />
    );
  if (!repository.data || status.isPending)
    return <p role="status">Loading archaeology…</p>;
  return (
    <>
      <p className="mono eyebrow">DETERMINISTIC SOFTWARE ARCHAEOLOGY</p>
      <h1 className="repo-title">{repository.data.full_name}</h1>
      <RepositoryNav repoId={repoId} active="Archaeology" />
      {status.isError ? (
        <QueryError error={status.error} retry={() => status.refetch()} />
      ) : !ready ? (
        <section className="history-panel archaeology-build">
          <div>
            <h2>
              {status.data?.stale
                ? "Archaeology index is stale"
                : "Build archaeology index"}
            </h2>
            <p className="muted">
              Uses indexed Git and symbol history. Ollama is optional.
            </p>
            {status.data?.error && (
              <p role="alert" className="error-message">
                {status.data.error}
              </p>
            )}
          </div>
          <div>
            <strong>{status.data?.status.replaceAll("_", " ")}</strong>
            {status.data?.progress !== null && (
              <span>{status.data?.progress.toFixed(0)}%</span>
            )}
            <button
              disabled={
                reindex.isPending ||
                ["pending", "indexing"].includes(status.data?.status ?? "")
              }
              onClick={() =>
                reindex.mutate(repoId, {
                  onSuccess: () => {
                    status.refetch();
                  },
                })
              }
            >
              {reindex.isPending ? "Starting…" : "Build index"}
            </button>
          </div>
          {reindex.isError && (
            <p role="alert" className="error-message">
              {errorMessage(reindex.error)}
            </p>
          )}
        </section>
      ) : overview.isError ? (
        <QueryError error={overview.error} retry={() => overview.refetch()} />
      ) : (
        <>
          <div
            className="architecture-tabs"
            role="tablist"
            aria-label="Archaeology sections"
          >
            {tabs.map((item) => (
              <button
                key={item}
                role="tab"
                aria-selected={tab === item}
                className={tab === item ? "active" : ""}
                onClick={() => setTab(item)}
              >
                {item}
              </button>
            ))}
          </div>
          {tab === "Overview" && overview.data && (
            <>
              <section className="archaeology-cards">
                <article>
                  <span>Repository age</span>
                  <strong>{days(overview.data.repository_age_days)}</strong>
                </article>
                <article>
                  <span>Current symbols</span>
                  <strong>{overview.data.current_symbols}</strong>
                </article>
                <article>
                  <span>Deleted symbols</span>
                  <strong>{overview.data.deleted_symbols}</strong>
                </article>
                <article>
                  <span>Major rewrites</span>
                  <strong>{overview.data.major_rewrites}</strong>
                </article>
                <article>
                  <span>Historical contributors</span>
                  <strong>{overview.data.contributors}</strong>
                </article>
                <article>
                  <span>Median symbol age</span>
                  <strong>{days(overview.data.median_symbol_age_days)}</strong>
                </article>
              </section>
              <section className="history-panel">
                <h2>Most changed files</h2>
                <TargetTable
                  rows={overview.data.most_changed_files}
                  open={setSelected}
                />
                <details className="formula-note">
                  <summary>Metric definitions</summary>
                  <p>
                    <strong>Volatility:</strong>{" "}
                    {overview.data.volatility_formula}
                  </p>
                  <p>
                    <strong>Stability:</strong>{" "}
                    {overview.data.stability_formula}
                  </p>
                  <p>
                    {overview.data.canonical_date}.{" "}
                    {overview.data.merge_commit_policy}
                  </p>
                </details>
              </section>
            </>
          )}
          {tab === "Code Age" && overview.data && (
            <section className="history-panel">
              <h2>Current symbol age</h2>
              <div className="age-bars">
                {Object.entries(overview.data.age_buckets).map(
                  ([label, count]) => (
                    <div key={label}>
                      <span>{label.replaceAll("_", " ")}</span>
                      <progress
                        value={count}
                        max={Math.max(overview.data!.current_symbols, 1)}
                      />
                      <strong>{count}</strong>
                    </div>
                  ),
                )}
              </div>
              <h3>Oldest current symbols</h3>
              <TargetTable
                rows={overview.data.oldest_current_symbols}
                open={setSelected}
              />
            </section>
          )}
          {tab === "Volatility" && (
            <section className="history-panel">
              <div className="archaeology-controls">
                <h2>Historical activity</h2>
                <select
                  aria-label="Entity level"
                  value={level}
                  onChange={(event) =>
                    setLevel(event.target.value as "file" | "symbol")
                  }
                >
                  <option value="symbol">Symbols</option>
                  <option value="file">Files</option>
                </select>
                <select
                  aria-label="Sort archaeology"
                  value={sort}
                  onChange={(event) => setSort(event.target.value)}
                >
                  <option value="volatility">Most volatile</option>
                  <option value="stability">Most stable</option>
                  <option value="changes">Most changed</option>
                  <option value="oldest">Oldest</option>
                  <option value="newest">Newest</option>
                </select>
              </div>
              {volatility.isError ? (
                <QueryError
                  error={volatility.error}
                  retry={() => volatility.refetch()}
                />
              ) : volatility.isPending ? (
                <p role="status">Calculating view…</p>
              ) : (
                <TargetTable
                  rows={volatility.data?.items ?? []}
                  open={setSelected}
                />
              )}
              <p className="muted">
                High churn means frequently changed. It does not imply poor
                quality or predict defects.
              </p>
            </section>
          )}
          {tab === "Contributors" && (
            <section className="history-panel">
              <h2>Historical contributors</h2>
              <p className="muted">
                Contribution share and knowledge indicators use repository
                history; they do not describe organizational ownership.
              </p>
              {contributors.data?.items.length ? (
                <div className="archaeology-table-wrap">
                  <table className="archaeology-table">
                    <thead>
                      <tr>
                        <th>Contributor</th>
                        <th>Commits</th>
                        <th>Files</th>
                        <th>Symbols</th>
                        <th>First activity</th>
                        <th>Last activity</th>
                      </tr>
                    </thead>
                    <tbody>
                      {contributors.data.items.map((item) => (
                        <tr key={item.identity_key}>
                          <td>{item.display_name}</td>
                          <td>{item.commit_count}</td>
                          <td>{item.files_touched}</td>
                          <td>{item.symbols_touched}</td>
                          <td>{dateLabel(item.first_activity)}</td>
                          <td>{dateLabel(item.last_activity)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="muted">No contributor evidence.</p>
              )}
              <p>
                {String(
                  contributors.data?.concentration.label ?? "Insufficient data",
                ).replaceAll("_", " ")}
              </p>
            </section>
          )}
          {tab === "Rewrites" && (
            <section className="history-panel">
              <h2>Major rewrites</h2>
              {rewrites.data?.length ? (
                <ol className="archaeology-event-list">
                  {rewrites.data.map((item) => (
                    <li key={item.id}>
                      <div>
                        <strong>{item.symbol}</strong>
                        <small>{item.file_path}</small>
                      </div>
                      <span>{(item.similarity * 100).toFixed(0)}% similar</span>
                      <span>
                        +{item.lines_added} / -{item.lines_deleted}
                      </span>
                      <Link
                        href={`/repos/${repoId}/history/symbols/${item.lineage_id}`}
                      >
                        {item.commit_sha.slice(0, 12)}
                      </Link>
                    </li>
                  ))}
                </ol>
              ) : (
                <p className="muted">
                  No major rewrites met the configured deterministic threshold.
                </p>
              )}
            </section>
          )}
          {tab === "Deleted Code" && (
            <HistoricalSearch
              repoId={repoId}
              query={query}
              setQuery={setQuery}
              searchType={searchType === "all" ? "deleted_symbol" : searchType}
              setSearchType={setSearchType}
              searchStatus="deleted"
              setSearchStatus={setSearchStatus}
              search={search}
            />
          )}
          {tab === "Search History" && (
            <HistoricalSearch
              repoId={repoId}
              query={query}
              setQuery={setQuery}
              searchType={searchType}
              setSearchType={setSearchType}
              searchStatus={searchStatus}
              setSearchStatus={setSearchStatus}
              search={search}
            />
          )}
        </>
      )}
      {(selected || selectedLineage) && (
        <div
          className="dossier-backdrop"
          onClick={() => {
            setSelected(null);
            setSelectedLineage(null);
          }}
          role="presentation"
        >
          <aside
            className="dossier-panel"
            role="dialog"
            aria-modal="true"
            aria-label="Archaeology dossier"
            onClick={(event) => event.stopPropagation()}
          >
            <button
              className="dossier-close"
              onClick={() => {
                setSelected(null);
                setSelectedLineage(null);
              }}
            >
              Close
            </button>
            {dossier.isPending ? (
              <p role="status">Loading dossier…</p>
            ) : dossier.isError ? (
              <p role="alert">{errorMessage(dossier.error)}</p>
            ) : (
              dossier.data && (
                <>
                  <p className="eyebrow">ARCHAEOLOGY DOSSIER</p>
                  <h2>{dossier.data.target.name}</h2>
                  <p className="mono">{dossier.data.target.path}</p>
                  <dl className="dossier-grid">
                    <div>
                      <dt>Origin</dt>
                      <dd>
                        {String(
                          dossier.data.provenance.origin.name ?? "Unknown",
                        )}
                      </dd>
                    </div>
                    <div>
                      <dt>Introduced</dt>
                      <dd>{dateLabel(dossier.data.target.introduced_at)}</dd>
                    </div>
                    <div>
                      <dt>Changes</dt>
                      <dd>{dossier.data.target.change_count}</dd>
                    </div>
                    <div>
                      <dt>Major rewrites</dt>
                      <dd>{dossier.data.target.rewrite_count}</dd>
                    </div>
                    <div>
                      <dt>Fan-in</dt>
                      <dd>{String(dossier.data.dependencies.fan_in ?? 0)}</dd>
                    </div>
                    <div>
                      <dt>Fan-out</dt>
                      <dd>{String(dossier.data.dependencies.fan_out ?? 0)}</dd>
                    </div>
                  </dl>
                  <h3>Provenance</h3>
                  <ol className="dossier-timeline">
                    {dossier.data.provenance.timeline.map((event, index) => (
                      <li key={`${String(event.commit_id)}-${index}`}>
                        <strong>
                          {String(event.event).replaceAll("_", " ")}
                        </strong>
                        <span>{String(event.name ?? event.path ?? "")}</span>
                        <small>
                          {event.committed_at
                            ? dateLabel(String(event.committed_at))
                            : "Unknown date"}{" "}
                          · {String(event.author ?? "Unknown")}
                        </small>
                      </li>
                    ))}
                  </ol>
                  <h3>Historical contributors</h3>
                  {dossier.data.contributors.items.map((item) => (
                    <p key={item.identity_key}>
                      {item.display_name}:{" "}
                      {((item.contribution_share ?? 0) * 100).toFixed(0)}%
                    </p>
                  ))}
                  {dossier.data.target.entity_type === "symbol" && (
                    <Link
                      className="action-link"
                      href={`/repos/${repoId}/history/symbols/${dossier.data.target.entity_id}`}
                    >
                      View full symbol history
                    </Link>
                  )}
                </>
              )
            )}
          </aside>
        </div>
      )}
    </>
  );
}

function HistoricalSearch({
  repoId,
  query,
  setQuery,
  searchType,
  setSearchType,
  searchStatus,
  setSearchStatus,
  search,
}: {
  repoId: string;
  query: string;
  setQuery: (value: string) => void;
  searchType: string;
  setSearchType: (value: string) => void;
  searchStatus: string;
  setSearchStatus: (value: string) => void;
  search: ReturnType<typeof useHistoricalSearch>;
}) {
  return (
    <section className="history-panel">
      <div className="archaeology-controls">
        <label className="symbol-search">
          <span className="sr-only">Search repository history</span>
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search repository history…"
          />
        </label>
        <select
          aria-label="Historical result type"
          value={searchType}
          onChange={(event) => setSearchType(event.target.value)}
        >
          <option value="all">All types</option>
          <option value="symbol">Symbols</option>
          <option value="file">Files</option>
          <option value="deleted_symbol">Deleted symbols</option>
          <option value="deleted_file">Deleted files</option>
        </select>
        <select
          aria-label="Historical result status"
          value={searchStatus}
          onChange={(event) => setSearchStatus(event.target.value)}
        >
          <option value="all">All states</option>
          <option value="current">Current</option>
          <option value="deleted">Deleted</option>
        </select>
      </div>
      {!query.trim() ? (
        <p className="muted">
          Search current and deleted symbols, old names, historical paths, and
          historical source.
        </p>
      ) : search.isPending ? (
        <p role="status">Searching history…</p>
      ) : search.isError ? (
        <p role="alert">{errorMessage(search.error)}</p>
      ) : search.data?.items.length ? (
        <ol className="historical-search-results">
          {search.data.items.map((item, index) => (
            <li key={`${item.entity_id}-${item.version_id}-${index}`}>
              <div>
                <span className="badge">{item.status}</span>
                <strong>{item.historical_name || item.name}</strong>
                <small>
                  {item.kind} · {item.file_path}
                </small>
              </div>
              <span>
                {item.match_type} · {item.matched_reason}
              </span>
              {item.lineage_id && (
                <Link
                  href={`/repos/${repoId}/history/symbols/${item.lineage_id}`}
                >
                  View history
                </Link>
              )}
            </li>
          ))}
        </ol>
      ) : (
        <p className="muted">No historical matches.</p>
      )}
    </section>
  );
}
