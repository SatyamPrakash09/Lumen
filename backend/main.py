from uvicorn import run
from src.config.settings import get_settings

settings = get_settings()

if __name__ == "__main__":
    run(
        "src.app:app",
        host="localhost",
        port=8000,
        reload=settings.is_development
    )