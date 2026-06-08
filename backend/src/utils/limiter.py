# Create this new file: D:\Lumen\backend\src\limiter.py
from slowapi import Limiter
from slowapi.util import get_remote_address

# Initialize the limiter independently
limiter = Limiter(key_func=get_remote_address)
