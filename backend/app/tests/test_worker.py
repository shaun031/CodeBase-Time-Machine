from app.workers.celery_app import celery_app
from app.workers.tasks.health import health_check_task


def test_task_registered_and_executes_locally():
    assert "health_check_task" in celery_app.tasks
    # apply executes the real task body without pretending a broker was contacted.
    result = health_check_task.apply()
    assert result.successful()
    assert result.get() == {"status": "ok"}


def test_json_only_serialization():
    assert celery_app.conf.accept_content == ["json"]
    assert celery_app.conf.task_serializer == "json"
