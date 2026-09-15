"""Implementation detail of GitService: bounded, credential-free Git processes."""

import ipaddress
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from app.core.config import Settings
from app.core.ingestion_errors import IngestionError
from app.services.storage import RepositoryStorage


class GitRunner:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _public_address(self) -> str:
        try:
            addresses = socket.getaddrinfo("github.com", 443, type=socket.SOCK_STREAM)
            ips = [ipaddress.ip_address(info[4][0]) for info in addresses]
        except (OSError, ValueError):
            raise IngestionError("REMOTE_NETWORK_ERROR", "Could not resolve GitHub.", 503) from None
        if not ips or any(not ip.is_global for ip in ips):
            raise IngestionError(
                "UNSAFE_REMOTE_ADDRESS", "GitHub resolved to an unsafe address.", 503
            )
        address = str(ips[0])
        return f"[{address}]" if ips[0].version == 6 else address

    @staticmethod
    def _kill(process: subprocess.Popen[bytes]) -> None:
        if process.poll() is not None:
            return
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        process.wait()

    def run(
        self,
        args: list[str],
        *,
        cwd: Path | None = None,
        network: bool = False,
        timeout: int | None = None,
        limit: int | None = None,
        truncate: bool = False,
        disk_path: Path | None = None,
        accepted: tuple[int, ...] = (0,),
        failure_code: str = "GIT_COMMAND_FAILED",
    ) -> tuple[bytes, bool, int]:
        executable = shutil.which("git")
        if executable is None:
            raise IngestionError("GIT_NOT_AVAILABLE", "Git is not installed in the worker.", 503)
        max_bytes = limit if limit is not None else self.settings.git_output_limit_bytes
        # No inherited credentials, proxy, Git config, askpass, or hook configuration.
        environment = {
            key: value
            for key, value in os.environ.items()
            if key.upper() in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "COMSPEC"}
        }
        with tempfile.TemporaryDirectory(prefix="ctm-git-") as isolated_home:
            environment.update(
                {
                    "HOME": isolated_home,
                    "USERPROFILE": isolated_home,
                    "XDG_CONFIG_HOME": isolated_home,
                    "GIT_CONFIG_NOSYSTEM": "1",
                    "GIT_CONFIG_GLOBAL": os.devnull,
                    "GIT_CONFIG_SYSTEM": os.devnull,
                    "GIT_TERMINAL_PROMPT": "0",
                    "GCM_INTERACTIVE": "never",
                    "GIT_NO_REPLACE_OBJECTS": "1",
                    "GIT_LITERAL_PATHSPECS": "1",
                    "GIT_PAGER": "cat",
                    "LC_ALL": "C",
                    "GIT_ALLOW_PROTOCOL": "https",
                }
            )
            options = [
                "credential.helper=",
                f"core.hooksPath={isolated_home}",
                f"core.attributesFile={os.devnull}",
                "protocol.allow=never",
                "protocol.https.allow=always",
                "http.followRedirects=false",
                "http.proxy=",
                "http.sslVerify=true",
                "gc.auto=0",
                "maintenance.auto=false",
                "fetch.recurseSubmodules=false",
                "submodule.recurse=false",
            ]
            if network:
                options.append(f"http.curloptResolve=github.com:443:{self._public_address()}")
            command = [executable, "--no-pager"]
            for option in options:
                command.extend(["-c", option])
            command.extend(args)
            output = bytearray()
            overflow = threading.Event()
            creation_flags = 0
            if sys.platform == "win32":
                creation_flags = subprocess.CREATE_NO_WINDOW
            process = subprocess.Popen(
                command,
                cwd=cwd or isolated_home,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=os.name != "nt",
                creationflags=creation_flags,
            )

            def drain_stdout() -> None:
                assert process.stdout is not None
                while chunk := process.stdout.read(65536):
                    remaining = max_bytes - len(output)
                    output.extend(chunk[: max(0, remaining)])
                    if len(chunk) > remaining:
                        overflow.set()

            def drain_stderr() -> None:
                assert process.stderr is not None
                while process.stderr.read(65536):
                    pass  # Never store or expose untrusted Git stderr.

            readers = [threading.Thread(target=drain_stdout), threading.Thread(target=drain_stderr)]
            for reader in readers:
                reader.start()
            deadline = time.monotonic() + (timeout or self.settings.git_command_timeout_seconds)
            last_size_check = 0.0
            try:
                while process.poll() is None:
                    if overflow.is_set():
                        self._kill(process)
                        break
                    if time.monotonic() > deadline:
                        raise IngestionError(
                            "CLONE_TIMEOUT" if args[0] == "clone" else "GIT_TIMEOUT",
                            "Git operation timed out. Try a smaller repository or retry later.",
                            504,
                        )
                    if disk_path is not None and time.monotonic() - last_size_check > 0.5:
                        last_size_check = time.monotonic()
                        if (
                            RepositoryStorage().size(disk_path)
                            > self.settings.max_repository_size_mb * 1048576
                        ):
                            raise IngestionError(
                                "REPOSITORY_TOO_LARGE",
                                "Repository exceeds the configured disk limit.",
                                413,
                            )
                    time.sleep(0.02)
            finally:
                self._kill(process)
                for reader in readers:
                    reader.join()
                if process.stdout:
                    process.stdout.close()
                if process.stderr:
                    process.stderr.close()
            if overflow.is_set():
                if truncate:
                    return bytes(output), True, process.returncode
                raise IngestionError(
                    "GIT_OUTPUT_TOO_LARGE", "Git metadata exceeds the configured output limit.", 413
                )
            if process.returncode not in accepted:
                message = (
                    "The repository could not be accessed as a public GitHub repository."
                    if failure_code == "REPOSITORY_NOT_ACCESSIBLE"
                    else "Git could not complete the operation."
                )
                raise IngestionError(failure_code, message, 422 if network else 500)
            return bytes(output), False, process.returncode
