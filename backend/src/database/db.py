from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from fastapi import Depends
from collections.abc import AsyncGenerator
from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase
from src.models.user_model import User
from src.config.settings import get_settings
from src.models.user_model import Base

settings = get_settings()

DB_URL = settings.DB_URL
engine = create_async_engine(DB_URL)
async_session_maker = async_sessionmaker(engine, expire_on_commit=False)

async def create_db_and_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_async_session() -> AsyncGenerator:
    async with async_session_maker() as session:
        yield session

async def get_user_db(session: AsyncSession = Depends(get_async_session)):
    yield SQLAlchemyUserDatabase(session, User)
