from typing import Annotated

from fastapi.params import Depends
from sqlmodel import Session, SQLModel, create_engine

import database.populators as populators
from settings import POSTGRES_URL

from .agents.models import *  # noqa: F403 Needed for SQLModel to recognize the models defined in agents.models
from .auth.models import *  # noqa: F403 # Needed for SQLModel to recognize the models defined in auth.models
from .logging.models import *  # noqa: F403 Needed for SQLModel to recognize the models defined in logging.models
from .logging.orm_events import *  # noqa: F403
from .provider.models import *  # noqa: F403 Needed for SQLModel to recognize the models defined in provider
from .tools.models import *  # noqa: F403 Needed for SQLModel to recognize the models defined in tools.models

# Database one: General purpose, postgresql

postgres_url = POSTGRES_URL

general_engine = create_engine(postgres_url)


async def create_db_and_tables():
    SQLModel.metadata.create_all(general_engine)


async def populate_db():
    for populator in populators.__all__:
        populator_func = getattr(populators, populator)
        if callable(populator_func):
            _ = populator_func(general_engine)


async def drop_db_and_tables():
    SQLModel.metadata.drop_all(general_engine)


def get_session():
    with Session(general_engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]
