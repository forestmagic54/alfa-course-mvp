from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.config.settings import Settings
from src.services.recommendation_stubs import (
    Generator,
    Ranker,
    StubGenerator,
)
from src.services.recsys_ranker import RecSysRanker


@dataclass
class AppContext:
    settings: Settings
    session_factory: async_sessionmaker[AsyncSession]

    ranker: Ranker = field(default_factory=RecSysRanker)
    generator: Generator = field(default_factory=StubGenerator)
    fallback_generator: Generator = field(default_factory=StubGenerator)
