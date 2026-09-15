from sqlalchemy import create_engine, pool

from alembic import context
from app.core.config import get_settings
from app.db.base import Base
from app.db.models import AnalysisJob, Repository  # noqa: F401

target_metadata = Base.metadata
url = get_settings().database_url.get_secret_value()


def run_with_connection(connection):
    configure_options = {
        "connection": connection,
        "target_metadata": target_metadata,
        "compare_type": True,
    }
    version_table_schema = context.config.attributes.get("version_table_schema")
    if version_table_schema is not None:
        configure_options["version_table_schema"] = version_table_schema
    context.configure(**configure_options)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    if not url:
        raise RuntimeError("DATABASE_URL is required for migrations")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()
elif context.config.attributes.get("connection") is not None:
    run_with_connection(context.config.attributes["connection"])
else:
    if not url:
        raise RuntimeError("DATABASE_URL is required for migrations")
    engine = create_engine(url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        run_with_connection(connection)
    engine.dispose()
