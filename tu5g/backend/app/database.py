"""
Database configuration for the TU5G platform backend.
Handles SQLAlchemy async engine creation, session management, and dependencies.
"""

from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

# Import configuration to get DATABASE_URL
from app.config import get_settings

settings = get_settings()

database_url = settings.DATABASE_URL
if database_url.startswith("postgresql://"):
    database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

# SQLite fallback support with pool configuration exception safety
engine_kwargs = {
    "pool_pre_ping": True,
}

if database_url.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    engine_kwargs["pool_size"] = 10
    engine_kwargs["max_overflow"] = 20

# Create SQLAlchemy async engine with optimized pool settings
engine = create_async_engine(
    database_url,
    **engine_kwargs
)

# AsyncSessionLocal sessionmaker for creating database sessions
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

# Base = declarative_base() imported from models
from app.models import Base

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency yielding a database session.
    Ensures the session is automatically closed after the request completes.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
