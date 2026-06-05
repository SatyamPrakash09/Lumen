from datetime import datetime, timedelta, timezone
import jwt
from src.config.settings import get_settings
settings = get_settings()

def create_refresh_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.REFRESH_TOKEN_EXPIRY)
    to_encode.update({"exp": expire})
    refresh_token = jwt.encode(to_encode, settings.REFRESH_TOKEN_SECRET, algorithm="HS256")
    return refresh_token

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRY)
    to_encode.update({"exp": expire})
    access_token = jwt.encode(to_encode, settings.ACCESS_TOKEN_SECRET, algorithm="HS256")
    return access_token



