from typing import Annotated

from fastapi.params import Depends
from sqlmodel import Session, create_engine

from settings import POSTGRES_URL

postgres_url = POSTGRES_URL

general_engine = create_engine(postgres_url)


def get_session():
    with Session(general_engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]
