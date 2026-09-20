"""Read-only development data-integrity report for CodeBase Time Machine."""

from sqlalchemy import text

from app.db.session import get_engine

CHECKS = {
    "symbols_missing_files": """
        SELECT count(*) FROM code_symbols s
        LEFT JOIN repository_files f ON f.id = s.file_id
        WHERE f.id IS NULL
    """,
    "graph_edges_missing_nodes": """
        SELECT count(*) FROM dependency_edges e
        LEFT JOIN dependency_nodes source ON source.id = e.source_node_id
        LEFT JOIN dependency_nodes target ON target.id = e.target_node_id
        WHERE source.id IS NULL OR target.id IS NULL
    """,
    "embeddings_missing_evidence": """
        SELECT count(*) FROM evidence_embeddings e
        LEFT JOIN evidence_documents d ON d.id = e.evidence_document_id
        WHERE d.id IS NULL
    """,
    "snapshot_edges_missing_snapshots": """
        SELECT count(*) FROM architecture_snapshot_edges e
        LEFT JOIN architecture_snapshots s ON s.id = e.snapshot_id
        WHERE s.id IS NULL
    """,
    "commit_pr_links_missing_pull_requests": """
        SELECT count(*) FROM commit_pr_links l
        LEFT JOIN github_pull_requests pr ON pr.id = l.pull_request_id
        WHERE pr.id IS NULL
    """,
}


def main() -> int:
    failures: dict[str, int] = {}
    with get_engine().connect() as connection:
        for name, statement in CHECKS.items():
            count = int(connection.scalar(text(statement)) or 0)
            print(f"{name}: {count}")
            if count:
                failures[name] = count
    if failures:
        print("Integrity issues found; no data was changed.")
        return 1
    print("All checked references are valid. No data was changed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
