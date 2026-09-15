import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from uuid import UUID

from app.core.config import Settings, get_settings
from app.core.ingestion_errors import IngestionError
from app.parsers.git_history import GitCommit, GitFileChange, parse_changes, parse_commit, text
from app.services.git_runner import GitRunner
from app.services.repository_url import GitHubRepositoryURL
from app.services.storage import RepositoryStorage


@dataclass
class RemoteInfo:
    default_branch: str | None
    head_sha: str | None


@dataclass(frozen=True)
class GitTreeEntry:
    path: str
    mode: str
    object_type: str
    blob_sha: str
    size_bytes: int


@dataclass(frozen=True)
class GitBlameLine:
    line: int
    commit_sha: str
    author: str
    author_time: int
    source: str


class GitService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.runner = GitRunner(self.settings)
        self.storage = RepositoryStorage(self.settings.repository_storage_path)

    def ensure_git_available(self) -> None:
        self.runner.run(["--version"])

    @staticmethod
    def validate_sha(sha: str) -> str:
        if not re.fullmatch("[0-9a-f]{40}", sha):
            raise IngestionError(
                "INVALID_COMMIT_SHA", "A full 40-character commit SHA is required.", 422
            )
        return sha

    @staticmethod
    def validate_path(value: str) -> str:
        normalized = value.replace("\\", "/")
        path = PurePosixPath(normalized)
        if (
            not value
            or path.is_absolute()
            or normalized.startswith("/")
            or normalized.startswith("-")
            or "$(" in normalized
            or (len(normalized) >= 2 and normalized[1] == ":")
            or any(part in {"", ".", ".."} for part in path.parts)
        ):
            raise IngestionError(
                "INVALID_FILE_PATH", "File path must stay inside the indexed repository.", 422
            )
        return path.as_posix()

    def verify_remote(self, url: GitHubRepositoryURL) -> RemoteInfo:
        data, _, _ = self.runner.run(
            ["ls-remote", "--symref", url.clone_url, "HEAD"],
            network=True,
            timeout=min(20, self.settings.git_command_timeout_seconds),
            failure_code="REPOSITORY_NOT_ACCESSIBLE",
        )
        branch, head = None, None
        for line in data.splitlines():
            if line.startswith(b"ref: refs/heads/") and line.endswith(b"\tHEAD"):
                branch = text(line[len(b"ref: refs/heads/") :].split(b"\t")[0])
                self.runner.run(["check-ref-format", f"refs/heads/{branch}"])
            elif line.endswith(b"\tHEAD"):
                head = self.validate_sha(line.split(b"\t")[0].decode("ascii"))
        if head and not branch:
            raise IngestionError(
                "DEFAULT_BRANCH_UNKNOWN", "Could not determine the remote default branch."
            )
        return RemoteInfo(branch, head)

    def clone_repository(
        self, repository_id: UUID, url: GitHubRepositoryURL, remote: RemoteInfo
    ) -> Path:
        destination = self.storage.path(repository_id)
        self.storage.remove_temporary(repository_id)
        temporary = self.storage.path(repository_id, temporary=True)
        temporary.parent.mkdir(parents=True, exist_ok=True)
        command = ["clone", "--bare", "--single-branch", "--no-local"]
        if remote.default_branch:
            command.append(f"--branch={remote.default_branch}")
        command.extend(["--", url.clone_url, str(temporary)])
        try:
            self.runner.run(
                command,
                network=True,
                timeout=self.settings.clone_timeout_seconds,
                disk_path=temporary,
                failure_code="CLONE_FAILED",
            )
            self.check_size(temporary)
            self.storage.validate(temporary)
            self.storage.validate(destination)
            temporary.rename(destination)
        except Exception:
            self.storage.remove_temporary(repository_id)
            raise
        return destination

    def fetch_repository(self, path: Path, url: GitHubRepositoryURL, remote: RemoteInfo) -> None:
        self.check_size(path)
        if remote.default_branch:
            self.runner.run(
                [
                    "fetch",
                    "--no-recurse-submodules",
                    "--no-write-fetch-head",
                    "--prune",
                    "--prune-tags",
                    "--force",
                    "--tags",
                    "--",
                    url.clone_url,
                    f"+refs/heads/{remote.default_branch}:refs/heads/ctm-index",
                ],
                cwd=path,
                network=True,
                timeout=self.settings.fetch_timeout_seconds,
                disk_path=path,
            )
        self.check_size(path)

    def check_size(self, path: Path) -> None:
        if self.storage.size(path) > self.settings.max_repository_size_mb * 1048576:
            raise IngestionError(
                "REPOSITORY_TOO_LARGE", "Repository exceeds the configured disk limit.", 413
            )

    def get_default_branch(self, path: Path) -> str | None:
        raw, _, code = self.runner.run(
            ["symbolic-ref", "--quiet", "HEAD"], cwd=path, accepted=(0, 1)
        )
        return text(raw).strip().removeprefix("refs/heads/") if code == 0 else None

    def get_head_sha(self, path: Path, *, fetched: bool = False) -> str | None:
        raw, _, code = self.runner.run(
            [
                "rev-parse",
                "--verify",
                "refs/heads/ctm-index^{commit}" if fetched else "HEAD^{commit}",
            ],
            cwd=path,
            accepted=(0, 128),
        )
        return self.validate_sha(text(raw).strip()) if code == 0 else None

    def get_commits(self, path: Path, head: str | None) -> list[str]:
        if head is None:
            return []
        raw, _, _ = self.runner.run(
            [
                "rev-list",
                "--topo-order",
                "--reverse",
                f"--max-count={self.settings.max_commits + 1}",
                self.validate_sha(head),
                "--",
            ],
            cwd=path,
        )
        commits = text(raw).splitlines()
        if len(commits) > self.settings.max_commits:
            raise IngestionError("TOO_MANY_COMMITS", "Repository exceeds MAX_COMMITS.", 413)
        tree, _, _ = self.runner.run(["ls-tree", "-r", "-z", "--name-only", head], cwd=path)
        if tree.count(b"\0") > self.settings.max_files:
            raise IngestionError("TOO_MANY_FILES", "Repository exceeds MAX_FILES.", 413)
        return commits

    def get_commit(self, path: Path, sha: str) -> GitCommit:
        raw, _, _ = self.runner.run(
            [
                "show",
                "-s",
                "--no-show-signature",
                "--format=%H%x00%P%x00%an%x00%ae%x00%cn%x00%ce%x00%aI%x00%cI%x00%B",
                self.validate_sha(sha),
                "--",
            ],
            cwd=path,
        )
        return parse_commit(raw)

    def _comparison(self, commit: GitCommit) -> list[str]:
        return (
            [self.validate_sha(commit.parents[0]), self.validate_sha(commit.sha)]
            if commit.parents
            else [self.validate_sha(commit.sha)]
        )

    def get_changed_files(self, path: Path, commit: GitCommit) -> list[GitFileChange]:
        base = [
            "diff-tree",
            "--root",
            "--no-commit-id",
            "-r",
            "-M",
            "--no-ext-diff",
            "--no-textconv",
            "--ignore-submodules=none",
        ]
        refs = self._comparison(commit)
        raw, _, _ = self.runner.run([*base, "--raw", "-z", *refs, "--"], cwd=path)
        nums, _, _ = self.runner.run([*base, "--numstat", "-z", *refs, "--"], cwd=path)
        changes = parse_changes(raw, nums)
        if len(changes) > self.settings.max_files:
            raise IngestionError("TOO_MANY_FILES", "A commit exceeds MAX_FILES.", 413)
        return changes

    def is_ancestor(self, path: Path, old: str, head: str | None) -> bool:
        if head is None:
            return False
        _, _, code = self.runner.run(
            ["merge-base", "--is-ancestor", self.validate_sha(old), self.validate_sha(head)],
            cwd=path,
            accepted=(0, 1, 128),
        )
        return code == 0

    def get_commit_diff(self, path: Path, sha: str) -> tuple[str, bool]:
        commit = self.get_commit(path, sha)
        raw, truncated, _ = self.runner.run(
            [
                "diff-tree",
                "--root",
                "--no-commit-id",
                "-r",
                "-M",
                "-p",
                "--no-ext-diff",
                "--no-textconv",
                "--no-color",
                *self._comparison(commit),
                "--",
            ],
            cwd=path,
            limit=self.settings.max_diff_size_bytes,
            truncate=True,
        )
        return text(raw), truncated

    def get_tags(self, path: Path) -> list[dict[str, str | bool]]:
        raw, _, _ = self.runner.run(
            [
                "for-each-ref",
                "--format=%(refname:strip=2)%00%(objecttype)%00%(objectname)%00%(*objectname)",
                "refs/tags/",
            ],
            cwd=path,
        )
        tags: list[dict[str, str | bool]] = []
        for row in raw.splitlines():
            name, kind, target, peeled = row.split(b"\0")
            tags.append(
                {
                    "name": text(name),
                    "target_sha": text(peeled or target),
                    "annotated": kind == b"tag",
                }
            )
        return tags

    def list_tracked_files(self, path: Path, head: str) -> list[GitTreeEntry]:
        raw, _, _ = self.runner.run(
            ["ls-tree", "-r", "-z", "-l", self.validate_sha(head), "--"], cwd=path
        )
        entries: list[GitTreeEntry] = []
        for record in raw.split(b"\0"):
            if not record:
                continue
            header, separator, raw_path = record.partition(b"\t")
            parts = header.split()
            if not separator or len(parts) != 4:
                raise IngestionError("INVALID_GIT_TREE", "Git returned an invalid file tree.")
            mode, kind, sha, size = (text(part) for part in parts)
            file_path = text(raw_path)
            entries.append(
                GitTreeEntry(
                    path=file_path,
                    mode=mode,
                    object_type=kind,
                    blob_sha=self.validate_sha(sha),
                    size_bytes=int(size) if size.isdigit() else 0,
                )
            )
        if len(entries) > self.settings.max_repository_files:
            raise IngestionError("TOO_MANY_FILES", "Repository exceeds MAX_REPOSITORY_FILES.", 413)
        return entries

    def get_blob(self, path: Path, blob_sha: str, size_bytes: int) -> bytes:
        if size_bytes > self.settings.max_source_file_size_bytes:
            raise IngestionError("FILE_TOO_LARGE", "File exceeds MAX_SOURCE_FILE_SIZE_BYTES.", 413)
        raw, _, _ = self.runner.run(
            ["cat-file", "blob", self.validate_sha(blob_sha)],
            cwd=path,
            limit=self.settings.max_source_file_size_bytes + 1,
        )
        return raw

    def get_blob_sha(self, path: Path, commit_sha: str, file_path: str) -> tuple[str, int]:
        sha = self.validate_sha(commit_sha)
        safe_path = self.validate_path(file_path)
        raw, _, _ = self.runner.run(["ls-tree", "-z", "-l", sha, "--", safe_path], cwd=path)
        record = raw.rstrip(b"\0")
        if not record:
            raise IngestionError(
                "HISTORICAL_FILE_NOT_FOUND", "File not found at the selected commit.", 404
            )
        header, separator, returned_path = record.partition(b"\t")
        parts = header.split()
        if (
            not separator
            or len(parts) != 4
            or text(returned_path) != safe_path
            or parts[1] != b"blob"
        ):
            raise IngestionError(
                "HISTORICAL_FILE_NOT_FOUND", "File not found at the selected commit.", 404
            )
        blob_sha = self.validate_sha(text(parts[2]))
        size = int(parts[3]) if parts[3].isdigit() else 0
        return blob_sha, size

    def file_exists_at_commit(self, path: Path, commit_sha: str, file_path: str) -> bool:
        try:
            self.get_blob_sha(path, commit_sha, file_path)
        except IngestionError as error:
            if error.code == "HISTORICAL_FILE_NOT_FOUND":
                return False
            raise
        return True

    def get_file_at_commit(self, path: Path, commit_sha: str, file_path: str) -> bytes:
        blob_sha, size = self.get_blob_sha(path, commit_sha, file_path)
        return self.get_blob(path, blob_sha, size)

    def get_parent_commits(self, path: Path, commit_sha: str) -> list[str]:
        return self.get_commit(path, self.validate_sha(commit_sha)).parents

    def get_changed_files_between(
        self, path: Path, parent_sha: str | None, commit_sha: str
    ) -> list[GitFileChange]:
        commit = self.get_commit(path, self.validate_sha(commit_sha))
        if parent_sha is not None:
            validated_parent = self.validate_sha(parent_sha)
            if not commit.parents or commit.parents[0] != validated_parent:
                raise IngestionError(
                    "INVALID_COMMIT_RANGE", "The supplied commit is not a first-parent child.", 422
                )
        return self.get_changed_files(path, commit)

    def get_file_diff(
        self, path: Path, parent_sha: str | None, commit_sha: str, file_path: str
    ) -> tuple[str, bool]:
        safe_path = self.validate_path(file_path)
        current = self.validate_sha(commit_sha)
        refs = [self.validate_sha(parent_sha), current] if parent_sha else [current]
        raw, truncated, _ = self.runner.run(
            [
                "diff-tree",
                "--root",
                "--no-commit-id",
                "-r",
                "-p",
                "--no-ext-diff",
                "--no-textconv",
                "--no-color",
                *refs,
                "--",
                safe_path,
            ],
            cwd=path,
            limit=self.settings.max_diff_size_bytes,
            truncate=True,
        )
        return text(raw), truncated

    def get_commits_touching_path(self, path: Path, file_path: str) -> list[str]:
        safe_path = self.validate_path(file_path)
        raw, _, _ = self.runner.run(
            [
                "log",
                "--follow",
                "--format=%H",
                f"--max-count={self.settings.max_history_commits}",
                "--",
                safe_path,
            ],
            cwd=path,
        )
        return [self.validate_sha(value) for value in text(raw).splitlines() if value]

    def get_file_history(self, path: Path, file_path: str) -> list[GitCommit]:
        return [
            self.get_commit(path, sha) for sha in self.get_commits_touching_path(path, file_path)
        ]

    def get_blame(
        self,
        path: Path,
        commit_sha: str,
        file_path: str,
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> list[GitBlameLine]:
        sha = self.validate_sha(commit_sha)
        safe_path = self.validate_path(file_path)
        blob_sha, size = self.get_blob_sha(path, sha, safe_path)
        del blob_sha
        content = self.get_file_at_commit(path, sha, safe_path)
        total_lines = len(content.splitlines())
        if total_lines == 0:
            return []
        start = start_line or 1
        end = end_line or min(total_lines, start + self.settings.max_blame_lines - 1)
        if (
            start < 1
            or start > total_lines
            or end < start
            or end > total_lines
            or end - start + 1 > self.settings.max_blame_lines
        ):
            raise IngestionError(
                "HISTORY_LIMIT_EXCEEDED",
                "Git blame range is outside the file or exceeds the configured line limit.",
                422,
            )
        if size > self.settings.max_source_file_size_bytes:
            raise IngestionError("HISTORICAL_SOURCE_TOO_LARGE", "File is too large to blame.", 413)
        raw, _, _ = self.runner.run(
            ["blame", "--line-porcelain", "-L", f"{start},{end}", sha, "--", safe_path],
            cwd=path,
            limit=self.settings.git_output_limit_bytes,
        )
        result: list[GitBlameLine] = []
        current_sha = ""
        current_line = start
        author = "Unknown"
        author_time = 0
        for row in text(raw).splitlines():
            header = re.fullmatch(r"([0-9a-f]{40}) \d+ (\d+)(?: \d+)?", row)
            if header:
                current_sha = self.validate_sha(header.group(1))
                current_line = int(header.group(2))
            elif row.startswith("author "):
                author = row[7:]
            elif row.startswith("author-time "):
                value = row[12:]
                author_time = int(value) if value.lstrip("-").isdigit() else 0
            elif row.startswith("\t"):
                result.append(GitBlameLine(current_line, current_sha, author, author_time, row[1:]))
        return result
