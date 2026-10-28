from sqlmodel import SQLModel

import database.populators as populators
from database.engine import SessionDep, general_engine, get_session, postgres_url

from .agents.models import *  # noqa: F403 Needed for SQLModel to recognize the models defined in agents.models
from .auth.models import *  # noqa: F403 # Needed for SQLModel to recognize the models defined in auth.models
from .keys.models import *  # noqa: F403 Needed for SQLModel to recognize the models defined in keys.models
from .logging.models import *  # noqa: F403 Needed for SQLModel to recognize the models defined in logging.models
from .logging.orm_events import *  # noqa: F403
from .provider.models import *  # noqa: F403 Needed for SQLModel to recognize the models defined in provider
from .tools.models import *  # noqa: F403 Needed for SQLModel to recognize the models defined in tools.models

__all__ = [
    "SessionDep",
    "create_db_and_tables",
    "drop_db_and_tables",
    "general_engine",
    "get_session",
    "populate_db",
    "postgres_url",
]


async def create_db_and_tables():
    SQLModel.metadata.create_all(general_engine)


async def populate_db():
    for populator in populators.__all__:
        populator_func = getattr(populators, populator)
        if callable(populator_func):
            _ = populator_func(general_engine)


async def drop_db_and_tables():
    SQLModel.metadata.drop_all(general_engine)
