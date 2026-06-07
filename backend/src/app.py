import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, APIRouter

from src.database.db import create_db_and_tables
from src.routes import auth_routes
from src.routes import session_routes
from src.config.settings import get_settings

settings = get_settings()


@asynccontextmanager
async def life_span(app: FastAPI):
    await create_db_and_tables()
    # Ensure ChromaDB persistence directory exists at startup
    os.makedirs(settings.CHROMA_DB_DIR, exist_ok=True)
    yield

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="Lumen API",
    description="RAG-powered document chat API",
    version="1.0.0",
    lifespan=life_span,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


api_router = APIRouter(prefix="/api/v1")

api_router.include_router(
    auth_routes.router,
    prefix="/auth",
    tags=["auth"]
)
api_router.include_router(
    session_routes.router,
    prefix="/sessions",
    tags=["sessions"]
)

@api_router.get("/")
def status():
    return {"message": "Server is up", "status": "ok"}

app.include_router(api_router)

