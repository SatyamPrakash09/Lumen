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
    

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
        extra = "ignore"
@lru_cache()
def get_settings() -> Settings:
    return Settings()
