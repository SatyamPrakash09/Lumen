from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    ALLOWED_ORIGINS:list 
    is_development: bool = True
    DB_URL: str = 'sqlite+aiosqlite:///db.sqlite3'
    ACCESS_TOKEN_SECRET: str = "Your Secret"
    ACCESS_TOKEN_EXPIRY: int = 7
    REFRESH_TOKEN_EXPIRY: int = 15
    REFRESH_TOKEN_SECRET: str = "Your Secret"
    PRODUCTION: bool = False
    UPLOAD_DIR: str = "./uploads"
    ALLOWED_EXTENSIONS: list = ["pdf", "docx", "txt", "md", "csv"]
    UPLOAD_MAX_SIZE: int = 20 * 1024 * 1024  # 20 MB
    ALLOWED_MIME_TYPES: dict = {
        ".pdf": ["application/pdf"],
        ".docx": ["application/vnd.openxmlformats-officedocument.wordprocessingml.document"],
        ".txt": ["text/plain"],
        ".md": ["text/markdown"],
        ".csv": ["text/csv"]
    }

    # RAG / Vector Store settings
    CHROMA_DB_DIR: str = "./chroma_db"
    OLLAMA_MODEL: str = "llama3.2"
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    EMBEDDING_MODEL: str = "models/gemini-embedding-2"
    RAG_TOP_K: int = 5
    GOOGLE_API_KEY: str = ""
    GOOGLE_GENAI_MODEL: str = "gemini-2.5-flash"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
        extra = "ignore"

@lru_cache()
def get_settings() -> Settings:
    return Settings()

