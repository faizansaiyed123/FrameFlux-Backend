from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import get_settings
from app.features.auth.models import User
from app.features.media.models import Media, MediaVersion
from app.features.jobs.models import ProcessingJob
from app.features.projects.models import Project
from app.infrastructure.database import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import all models so Alembic registers every table with SQLAlchemy metadata.
_ = (User, Media, MediaVersion, ProcessingJob, Project)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    settings = get_settings()

    context.configure(
        url=settings.database_url.replace("+asyncpg", ""),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    settings = get_settings()

    configuration = config.get_section(config.config_ini_section) or {}

    configuration["sqlalchemy.url"] = settings.database_url.replace(
        "+asyncpg",
        "+psycopg",
    )

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
