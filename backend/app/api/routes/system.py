from fastapi import APIRouter, Response

from app.core.config import get_settings
from app.schemas.health import SystemStatus
from app.services.system import check_database, check_redis

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/status", response_model=SystemStatus)
def system_status(response: Response) -> SystemStatus:
    database_ok = check_database()
    redis_required = get_settings().task_execution_mode == "celery"
    redis_ok = check_redis() if redis_required else None
    if not database_ok or redis_required and not redis_ok:
        response.status_code = 503
    return SystemStatus(
        database="ok" if database_ok else "unavailable",
        redis=("ok" if redis_ok else "unavailable") if redis_required else "not_required",
    )
