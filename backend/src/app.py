from contextlib import asynccontextmanager

from fastapi import FastAPI, APIRouter

from src.database.db import create_db_and_tables
from src.routes import auth_routes


@asynccontextmanager
async def life_span(app: FastAPI):
    await create_db_and_tables()
    yield

app = FastAPI(lifespan=life_span)

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(
    auth_routes.router,
    prefix="/auth",
    tags=["auth"]
)

@api_router.get("/")
def status():
    return {"message": "Server is up", "status": "ok"}

app.include_router(api_router)
