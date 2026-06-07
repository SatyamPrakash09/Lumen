from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    is_development: bool = True
    DB_URL: str = 'sqlite+aiosqlite:///db.sqlite3'
    ACCESS_TOKEN_SECRET: str = "Your Secret"
    ACCESS_TOKEN_EXPIRY: int = 7
    REFRESH_TOKEN_EXPIRY: int = 15
    REFRESH_TOKEN_SECRET: str = "Your Secret"
    PRODUCTION:bool=False
    UPLOAD_DIR: str = "./uploads"
    ALLOWED_EXTENSIONS: list = ["pdf", "docx", "txt"]
    UPLOAD_MAX_SIZE: int = 20 * 1024 * 1024  # 20 MB
    ALLOWED_MIME_TYPES: dict = {
        ".pdf": ["application/pdf"],
        ".docx": ["application/vnd.openxmlformats-officedocument.wordprocessingml.document"],
        ".txt": ["text/plain"],
        ".md": ["text/markdown"],
        ".csv": ["text/csv"]
    }
    

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
        extra = "ignore"
@lru_cache()
def get_settings() -> Settings:
    return Settings()
