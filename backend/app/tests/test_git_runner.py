import os
import subprocess
import sys

import pytest

from app.core.config import Settings
from app.core.ingestion_errors import IngestionError
from app.services.git_runner import GitRunner


def test_unsafe_dns_is_rejected(monkeypatch):
    monkeypatch.setattr(
        "socket.getaddrinfo", lambda *args, **kwargs: [(2, 1, 6, "", ("127.0.0.1", 443))]
    )
    with pytest.raises(IngestionError) as error:
        GitRunner(Settings(_env_file=None))._public_address()
    assert error.value.code == "UNSAFE_REMOTE_ADDRESS"


def test_timeout_kills_process_tree(monkeypatch):
    original = subprocess.Popen

    def slow(command, **kwargs):
        if command[0].lower().endswith("git.exe") or command[0].endswith("/git"):
            return original([sys.executable, "-c", "import time; time.sleep(10)"], **kwargs)
        return original(command, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", slow)
    runner = GitRunner(Settings(_env_file=None, git_command_timeout_seconds=1))
    with pytest.raises(IngestionError) as error:
        runner.run(["--version"])
    assert error.value.code == "GIT_TIMEOUT"


def test_bounded_output(monkeypatch):
    original = subprocess.Popen

    def large(command, **kwargs):
        if command[0].lower().endswith("git.exe") or command[0].endswith("/git"):
            return original([sys.executable, "-c", "print('x' * 200000)"], **kwargs)
        return original(command, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", large)
    data, truncated, _ = GitRunner(Settings(_env_file=None)).run(
        ["--version"], limit=100, truncate=True
    )
    assert len(data) == 100 and truncated


def test_git_environment_has_no_credentials(monkeypatch):
    original = subprocess.Popen
    environments = []

    def capture(command, **kwargs):
        if "env" in kwargs:
            environments.append(kwargs["env"])
        return original(command, **kwargs)

    monkeypatch.setenv("GITHUB_TOKEN", "must-not-inherit")
    monkeypatch.setenv("GIT_CONFIG_COUNT", "20")
    monkeypatch.setenv("HTTPS_PROXY", "http://private-proxy")
    monkeypatch.setattr(subprocess, "Popen", capture)
    GitRunner(Settings(_env_file=None)).run(["--version"])
    env = environments[0]
    assert "GITHUB_TOKEN" not in env and "GIT_CONFIG_COUNT" not in env and "HTTPS_PROXY" not in env
    assert env["GIT_CONFIG_GLOBAL"] == os.devnull
    assert env["GIT_TERMINAL_PROMPT"] == "0"
