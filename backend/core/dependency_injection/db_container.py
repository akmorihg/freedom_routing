from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import AsyncAdaptedQueuePool

from backend.settings import Settings


class DBContainer:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, settings: Settings):
        if self._initialized:
            return

        self.settings = settings

        self.internal_db_engine: AsyncEngine = create_async_engine(
            self.settings.DATABASE_URL,
            echo=False,
            poolclass=AsyncAdaptedQueuePool,
            pool_size=100,
            max_overflow=200,
        )

        self.internal_db_session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
            self.internal_db_engine,
            autocommit=False,
            expire_on_commit=False,
        )

    def internal_engine(self) -> AsyncEngine:
        return self.internal_db_engine

    def internal_session(self) -> AsyncSession:
        return self.internal_db_session_factory()
