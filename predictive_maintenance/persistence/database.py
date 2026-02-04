"""
PDM Database Connection and Session Management

Provides SQLAlchemy engine, session factories, and database initialization.
"""

import logging
from contextlib import contextmanager, asynccontextmanager
from typing import Generator, AsyncGenerator, Optional

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, Session, declarative_base
from sqlalchemy.pool import QueuePool

logger = logging.getLogger(__name__)

# Try async support
ASYNC_AVAILABLE = False
try:
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
    ASYNC_AVAILABLE = True
except ImportError:
    logger.warning("Async SQLAlchemy not available. Install sqlalchemy[asyncio] for async support.")
    AsyncSession = None
    async_sessionmaker = None

# Base class for all models
Base = declarative_base()

# Module-level engine and session factory (initialized lazily)
_engine = None
_async_engine = None
_SessionLocal = None
_AsyncSessionLocal = None


def get_engine(database_url: Optional[str] = None, **kwargs):
    """
    Get or create the database engine.
    
    Args:
        database_url: Database connection URL. If not provided, uses config.
        **kwargs: Additional engine configuration options.
    
    Returns:
        SQLAlchemy Engine instance
    """
    global _engine
    
    if _engine is not None:
        return _engine
    
    if database_url is None:
        from ..config import settings
        database_url = settings.database.url
    
    default_kwargs = {
        "poolclass": QueuePool,
        "pool_size": 5,
        "max_overflow": 10,
        "pool_pre_ping": True,
        "pool_recycle": 3600,
        "echo": False,
    }
    default_kwargs.update(kwargs)
    
    _engine = create_engine(database_url, **default_kwargs)
    
    # Add event listeners for connection debugging
    @event.listens_for(_engine, "connect")
    def on_connect(dbapi_conn, connection_record):
        logger.debug("Database connection established")
    
    @event.listens_for(_engine, "checkout")
    def on_checkout(dbapi_conn, connection_record, connection_proxy):
        logger.debug("Connection checked out from pool")
    
    logger.info(f"Database engine created: {database_url.split('@')[-1] if '@' in database_url else database_url}")
    return _engine


def get_async_engine(database_url: Optional[str] = None, **kwargs):
    """Get or create the async database engine."""
    global _async_engine
    
    if not ASYNC_AVAILABLE:
        raise RuntimeError("Async SQLAlchemy not available. Install sqlalchemy[asyncio]")
    
    if _async_engine is not None:
        return _async_engine
    
    if database_url is None:
        from ..config import settings
        database_url = settings.database.async_url
    
    default_kwargs = {
        "pool_size": 5,
        "max_overflow": 10,
        "pool_pre_ping": True,
        "pool_recycle": 3600,
        "echo": False,
    }
    default_kwargs.update(kwargs)
    
    _async_engine = create_async_engine(database_url, **default_kwargs)
    logger.info("Async database engine created")
    return _async_engine


def get_session_factory():
    """Get the session factory, creating engine if needed."""
    global _SessionLocal
    
    if _SessionLocal is None:
        engine = get_engine()
        _SessionLocal = sessionmaker(
            bind=engine,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )
    
    return _SessionLocal


def get_async_session_factory():
    """Get the async session factory."""
    global _AsyncSessionLocal
    
    if not ASYNC_AVAILABLE:
        raise RuntimeError("Async SQLAlchemy not available")
    
    if _AsyncSessionLocal is None:
        engine = get_async_engine()
        _AsyncSessionLocal = async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )
    
    return _AsyncSessionLocal


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """
    Context manager for database sessions.
    
    Usage:
        with get_session() as session:
            session.query(Model).all()
    """
    SessionLocal = get_session_factory()
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@asynccontextmanager
async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Async context manager for database sessions.
    
    Usage:
        async with get_async_session() as session:
            await session.execute(query)
    """
    AsyncSessionLocal = get_async_session_factory()
    session = AsyncSessionLocal()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


def init_db(drop_existing: bool = False):
    """
    Initialize the database schema.
    
    Args:
        drop_existing: If True, drop all existing tables first.
    """
    engine = get_engine()
    
    # Import all models to ensure they're registered with Base
    from . import models  # noqa: F401
    
    if drop_existing:
        logger.warning("Dropping all existing tables!")
        Base.metadata.drop_all(bind=engine)
    
    Base.metadata.create_all(bind=engine)
    logger.info("Database schema initialized")


async def init_db_async(drop_existing: bool = False):
    """Initialize the database schema asynchronously."""
    engine = get_async_engine()
    
    from . import models  # noqa: F401
    
    async with engine.begin() as conn:
        if drop_existing:
            logger.warning("Dropping all existing tables!")
            await conn.run_sync(Base.metadata.drop_all)
        
        await conn.run_sync(Base.metadata.create_all)
    
    logger.info("Database schema initialized (async)")


def health_check() -> bool:
    """Check database connectivity."""
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return False


async def health_check_async() -> bool:
    """Check database connectivity asynchronously."""
    try:
        engine = get_async_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"Async database health check failed: {e}")
        return False
