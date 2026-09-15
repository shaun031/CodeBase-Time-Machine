"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  ChevronDown,
  ChevronRight,
  Copy,
  FileCode2,
  Folder,
  FolderOpen,
  Search,
} from "lucide-react";
import {
  useCodeReindex,
  useCommits,
  useFile,
  useFileContent,
  useFileSymbols,
  useFileTree,
  useRepository,
  useSymbolSearch,
} from "@/hooks/use-repository";
import { api, errorMessage } from "@/lib/api";
import { submissionPath } from "@/lib/repository";
import type { CodeSymbol, FileTreeNode } from "@/types/repository";
import { QueryError } from "./workspace";
import { RepositoryNav } from "./repository-nav";

function flatten(nodes: FileTreeNode[]): FileTreeNode[] {
  return nodes.flatMap((node) =>
    node.type === "file" ? [node] : flatten(node.children),
  );
}

function sourceLines(value: string): string[] {
  return value
    ? value.split(/\r\n|\n|\r/).slice(0, value.endsWith("\n") ? -1 : undefined)
    : [];
}
function FileNode({
  node,
  selected,
  choose,
}: {
  node: FileTreeNode;
  selected: string | null;
  choose: (path: string) => void;
}) {
  const [open, setOpen] = useState(true);
  if (node.type === "directory") {
    return (
      <li>
        <button
          className="tree-row"
          onClick={() => setOpen(!open)}
          aria-expanded={open}
        >
          {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
          {open ? <FolderOpen size={14} /> : <Folder size={14} />}
          <span>{node.name}</span>
        </button>
        {open && (
          <ul>
            {node.children.map((child) => (
              <FileNode
                key={child.path}
                node={child}
                selected={selected}
                choose={choose}
              />
            ))}
          </ul>
        )}
      </li>
    );
  }
  return (
    <li>
      <button
        className={`tree-row file ${selected === node.path ? "selected" : ""}`}
        onClick={() => choose(node.path)}
      >
        <FileCode2 size={13} />
        <span>{node.name}</span>
      </button>
    </li>
  );
}

function Outline({
  symbols,
  jump,
  repoId,
}: {
  symbols: CodeSymbol[];
  jump: (line: number) => void;
  repoId: string;
}) {
  return symbols.length ? (
    <ul className="symbol-outline">
      {symbols.map((symbol) => (
        <li
          key={symbol.id}
          style={{ paddingLeft: symbol.parent_symbol_id ? 16 : 0 }}
        >
          <button onClick={() => jump(symbol.start_line)}>
            <span>{symbol.name}</span>
            <small>{symbol.kind}</small>
          </button>
          {symbol.lineage_id && (
            <span className="symbol-context-links">
              <Link
                className="symbol-history-link"
                href={`/repos/${repoId}/history/symbols/${symbol.lineage_id}`}
              >
                View History
              </Link>
              <Link
                className="symbol-history-link"
                href={`/repos/${repoId}/ask?lineage_id=${symbol.lineage_id}&symbol_id=${symbol.id}&question=${encodeURIComponent(`Why does ${symbol.qualified_name} exist?`)}`}
              >
                Ask Why
              </Link>
              <Link
                className="symbol-history-link"
                href={`/repos/${repoId}/archaeology?lineage_id=${symbol.lineage_id}`}
              >
                Archaeology Dossier
              </Link>
            </span>
          )}
        </li>
      ))}
    </ul>
  ) : (
    <p className="muted">No symbols found in this file.</p>
  );
}

export function CodeExplorer({ repoId }: { repoId: string }) {
  const repository = useRepository(repoId);
  const tree = useFileTree(repoId, repository.data?.status === "ready");
  const [selected, setSelected] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [copied, setCopied] = useState("");
  const [viewSha, setViewSha] = useState("HEAD");
  const [selectedLines, setSelectedLines] = useState<[number, number] | null>(
    null,
  );
  const allFiles = useMemo(() => flatten(tree.data ?? []), [tree.data]);
  const activePath = selected ?? allFiles[0]?.path ?? null;
  const metadata = useFile(repoId, activePath);
  const content = useFileContent(repoId, activePath);
  const commits = useCommits(repoId, 1);
  const historicalContent = useQuery({
    queryKey: ["historical-file", repoId, activePath, viewSha],
    queryFn: () => api.getHistoricalFile(repoId, activePath!, viewSha),
    enabled: Boolean(activePath) && viewSha !== "HEAD",
  });
  const symbols = useFileSymbols(repoId, activePath);
  const results = useSymbolSearch(repoId, debounced);
  const reindex = useCodeReindex();
  const router = useRouter();
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(search.trim()), 250);
    return () => window.clearTimeout(timer);
  }, [search]);
  function jump(line: number) {
    document
      .getElementById(`source-line-${line}`)
      ?.scrollIntoView({ behavior: "smooth", block: "center" });
  }
  function selectSymbol(symbol: CodeSymbol) {
    if (!symbol.file_path) return;
    setSelected(symbol.file_path);
    setSelectedLines(null);
    window.setTimeout(() => jump(symbol.start_line), 150);
  }
  async function copy(value: string, label: string) {
    await navigator.clipboard.writeText(value);
    setCopied(label);
    window.setTimeout(() => setCopied(""), 1500);
  }
  if (repository.isError)
    return (
      <QueryError error={repository.error} retry={() => repository.refetch()} />
    );
  if (!repository.data) return <p role="status">Loading repository…</p>;
  if (repository.data.status !== "ready") {
    return (
      <>
        <h1 className="repo-title">{repository.data.full_name}</h1>
        <RepositoryNav repoId={repoId} active="Code" />
        <section className="history-panel">
          <h2>Code index unavailable</h2>
          <p className="muted">Current status: {repository.data.status}</p>
        </section>
      </>
    );
  }
  return (
    <>
      <p className="mono eyebrow">
        CURRENT HEAD · {repository.data.head_sha?.slice(0, 12)}
      </p>
      <h1 className="repo-title">{repository.data.full_name}</h1>
      <RepositoryNav repoId={repoId} active="Code" />
      <div className="code-toolbar">
        <label className="symbol-search">
          <Search size={15} />
          <span className="sr-only">Search symbols</span>
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search functions, classes, methods…"
          />
        </label>
        <label className="snapshot-selector">
          <span>Viewing</span>
          <select
            aria-label="Viewing commit"
            value={viewSha}
            onChange={(event) => {
              setViewSha(event.target.value);
              setSelectedLines(null);
            }}
          >
            <option value="HEAD">HEAD</option>
            {commits.data?.items.map((commit) => (
              <option key={commit.sha} value={commit.sha}>
                {commit.short_sha} · {commit.message.split("\n")[0]}
              </option>
            ))}
          </select>
        </label>
        <button
          onClick={() =>
            reindex.mutate(repoId, {
              onSuccess: (result) => router.push(submissionPath(result)),
            })
          }
          disabled={reindex.isPending}
        >
          Reindex current code
        </button>
      </div>
      {reindex.isError && (
        <p role="alert" className="error-message">
          {errorMessage(reindex.error)}
        </p>
      )}
      {search.trim().length >= 2 && (
        <div className="symbol-results">
          {results.isPending ? (
            <p role="status">Searching symbols…</p>
          ) : results.isError ? (
            <p role="alert">{errorMessage(results.error)}</p>
          ) : results.data?.items.length ? (
            results.data.items.map((symbol) => (
              <button key={symbol.id} onClick={() => selectSymbol(symbol)}>
                <strong>{symbol.qualified_name}</strong>
                <span>
                  {symbol.kind} · {symbol.file_path}
                </span>
              </button>
            ))
          ) : (
            <p>No matching symbols.</p>
          )}
        </div>
      )}
      {tree.isError ? (
        <QueryError error={tree.error} retry={() => tree.refetch()} />
      ) : tree.isPending ? (
        <p role="status">Loading repository files…</p>
      ) : (
        <div className="code-layout">
          <aside
            className="file-browser"
            tabIndex={0}
            aria-label="Repository files"
          >
            <h2>Files</h2>
            <ul className="file-tree">
              {tree.data?.map((node) => (
                <FileNode
                  key={node.path}
                  node={node}
                  selected={activePath}
                  choose={(path) => {
                    setSelected(path);
                    setSelectedLines(null);
                  }}
                />
              ))}
            </ul>
          </aside>
          <section className="source-panel">
            {viewSha !== "HEAD" && (
              <div className="historical-banner" role="status">
                <strong>Historical snapshot</strong>
                <span>{viewSha.slice(0, 12)}</span>
              </div>
            )}
            {!activePath ? (
              <p className="muted">This repository has no indexed files.</p>
            ) : metadata.isError ||
              (viewSha === "HEAD"
                ? content.isError
                : historicalContent.isError) ? (
              <QueryError
                error={
                  metadata.error ||
                  (viewSha === "HEAD" ? content.error : historicalContent.error)
                }
                retry={() => {
                  metadata.refetch();
                  if (viewSha === "HEAD") content.refetch();
                  else historicalContent.refetch();
                }}
              />
            ) : metadata.isPending ||
              (viewSha === "HEAD"
                ? content.isPending
                : historicalContent.isPending) ? (
              <p role="status">Loading source file…</p>
            ) : (
              metadata.data &&
              (viewSha === "HEAD" ? content.data : historicalContent.data) && (
                <>
                  <header className="source-header">
                    <div>
                      <strong className="mono">{metadata.data.path}</strong>
                      <p>
                        {metadata.data.language || "Text"} ·{" "}
                        {metadata.data.line_count ?? 0} lines ·{" "}
                        {(metadata.data.size_bytes / 1024).toFixed(1)} KB
                      </p>
                    </div>
                    <div>
                      <Link
                        className="source-action-link"
                        href={`/repos/${repoId}/ask?file_path=${encodeURIComponent(metadata.data.path)}${selectedLines ? `&start_line=${selectedLines[0]}&end_line=${selectedLines[1]}` : ""}${viewSha !== "HEAD" ? `&commit_sha=${viewSha}` : ""}&question=${encodeURIComponent(selectedLines ? "Why do these selected lines exist?" : "Explain the purpose and history of this file")}`}
                      >
                        {selectedLines
                          ? "Ask about selection"
                          : "Ask CodeChronicle"}
                      </Link>
                      <Link
                        className="source-action-link"
                        href={`/repos/${repoId}/architecture?file=${encodeURIComponent(metadata.data.id)}`}
                      >
                        Analyze Impact
                      </Link>
                      <button
                        title="Copy path"
                        onClick={() => copy(metadata.data.path, "path")}
                      >
                        <Copy size={14} />{" "}
                        {copied === "path" ? "Copied" : "Path"}
                      </button>
                      <button
                        title="Copy source"
                        onClick={() =>
                          copy(
                            viewSha === "HEAD"
                              ? content.data!.content
                              : historicalContent.data!.content,
                            "source",
                          )
                        }
                      >
                        <Copy size={14} />{" "}
                        {copied === "source" ? "Copied" : "Source"}
                      </button>
                    </div>
                  </header>
                  <div
                    className="source-code"
                    role="region"
                    aria-label={`Source code for ${metadata.data.path}`}
                    tabIndex={0}
                  >
                    {sourceLines(
                      viewSha === "HEAD"
                        ? content.data!.content
                        : historicalContent.data!.content,
                    ).map((line, index) => (
                      <div
                        className={`source-line ${selectedLines && index + 1 >= selectedLines[0] && index + 1 <= selectedLines[1] ? "source-line-selected" : ""}`}
                        id={`source-line-${index + 1}`}
                        key={index}
                      >
                        <button
                          className="line-selector"
                          title="Select this line for an AI question"
                          onClick={(event) => {
                            const lineNumber = index + 1;
                            setSelectedLines((current) =>
                              event.shiftKey && current
                                ? [
                                    Math.min(current[0], lineNumber),
                                    Math.max(current[1], lineNumber),
                                  ]
                                : [lineNumber, lineNumber],
                            );
                          }}
                        >
                          {index + 1}
                        </button>
                        <code>{line || " "}</code>
                      </div>
                    ))}
                  </div>
                </>
              )
            )}
          </section>
          <aside
            className="outline-panel"
            tabIndex={0}
            aria-label="File outline"
          >
            <h2>Outline</h2>
            {viewSha !== "HEAD" ? (
              <p className="muted">
                Select a timeline event in History to inspect symbols at this
                commit.
              </p>
            ) : symbols.isPending && activePath ? (
              <p role="status">Loading symbols…</p>
            ) : symbols.isError ? (
              <p role="alert">{errorMessage(symbols.error)}</p>
            ) : (
              <Outline
                symbols={symbols.data ?? []}
                jump={jump}
                repoId={repoId}
              />
            )}
          </aside>
        </div>
      )}
    </>
  );
}
