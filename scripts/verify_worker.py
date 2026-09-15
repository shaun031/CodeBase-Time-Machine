"""Run from backend: python ../scripts/verify_worker.py (worker + Redis required)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.workers.tasks.health import health_check_task  # noqa: E402

result = health_check_task.delay()
print(f"Enqueued health_check_task: {result.id}")
try:
    payload = result.get(timeout=30)
    if payload != {"status": "ok"}:
        raise RuntimeError(f"Unexpected result: {payload!r}")
    print("Worker executed task and returned:", payload)
finally:
    result.forget()
