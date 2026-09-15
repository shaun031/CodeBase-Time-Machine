import importlib.util
from pathlib import Path

from app.core.config import ROOT

spec = importlib.util.spec_from_file_location(
    "architecture_history_fixture_generator",
    ROOT / "scripts/create_architecture_history_test_repository.py",
)
assert spec is not None and spec.loader is not None
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)


def create_architecture_history_repository(path: Path) -> dict[str, str]:
    return generator.create_architecture_history_repository(path)
