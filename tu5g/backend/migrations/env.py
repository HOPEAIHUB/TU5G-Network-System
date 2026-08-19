import asyncio
from logging.config import fileConfig
import os
import sys

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# Add current path to sys.path so app modules are importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# This is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 1. Import all models and target_metadata
# We import Base from app.database, and then try importing app.models
# to ensure all models are registered on the metadata before migrations run.
try:
    from app.database import Base
except ImportError:
    from sqlalchemy.orm import declarative_base
    Base = declarative_base()

try:
    # This will register all declarative models to the Base metadata
    import app.models
except ImportError:
    # Log or handle case where models package/module is not yet created
    pass

target_metadata = Base.metadata

def get_url() -> str:
    """
    Get the database URL from settings/env.
    Prioritizes the app.config settings object, falls back to environment variable,
    and defaults to the alembic.ini configured url.
    Also ensures the URL uses postgresql+asyncpg for async migrations.
    """
    try:
        from app.config import get_settings
        url = get_settings().DATABASE_URL
    except Exception:
        url = os.getenv("DATABASE_URL", config.get_main_option("sqlalchemy.url"))
    
    if url and url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    """Helper method to run the actual migrations in a sync context (run_sync)."""
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    ini_section = config.get_section(config.config_ini_section) or {}
    ini_section["sqlalchemy.url"] = get_url()

    connectable = async_engine_from_config(
        ini_section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    # Using asyncio to run migrations on an async connection
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
