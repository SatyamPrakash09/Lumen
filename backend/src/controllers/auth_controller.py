import token
from typing_extensions import Annotated

from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.db import get_async_session
from src.models.models import User
from sqlalchemy import select, or_, func
from src.utils.jwt_utils import create_refresh_token, create_access_token
from pwdlib import PasswordHash
from src.config.settings import get_settings
import jwt
from jwt import PyJWTError

settings = get_settings()


password_hash = PasswordHash.recommended()

def get_password_hash(password):
    return password_hash.hash(password)

def verify_password(plain_password, hashed_password):
    return password_hash.verify(plain_password, hashed_password)

async def register_user(data, db):
    if not data.username or not data.password or not data.email:
        raise HTTPException(status_code=400, detail="Add Credential Not Present")
    if not data.username.isalnum():
        raise HTTPException(code=400, detail="username is not alpha numeric")
    find_user = select(User).where(or_(func.lower(User.username) == data.username.lower(), User.email == data.email))
    result = await db.execute(find_user)
    existing_user = result.scalars().first()
    if existing_user:
        raise HTTPException(status_code=400, detail="User already exists")

    try:
        token_payload_pre = {"username": data.username, "email": data.email}
        access_token = create_access_token(token_payload_pre)
        refresh_token = create_refresh_token(token_payload_pre)

        user = User(
            username=data.username,
            email=data.email,
            hashed_password=get_password_hash(data.password),
            avatar=data.avatar,
            first_name=data.first_name,
            last_name=data.last_name,
            access_token=access_token,
            refresh_token=refresh_token,
            is_active=True
        )
        db.add(user)
        await db.flush()

        # Re-issue tokens now that we have the real user.id
        token_payload = {
            "sub": str(user.id),
            "username": user.username,
            "email": user.email
        }
        access_token = create_access_token(token_payload)
        refresh_token = create_refresh_token(token_payload)
        user.access_token = access_token
        user.refresh_token = refresh_token

        await db.commit()
        await db.refresh(user)
        return user
    except SQLAlchemyError as e:
        await db.rollback()  
        print(f"SQLAlchemy Error: {str(e)}")
        raise HTTPException(status_code=400, detail=f"DB Error: {str(e)}")
    except Exception as e:
        print(f"Unexpected Error: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Something went wrong: {str(e)}")
    
async def login_user(data, db, response):
    if not data.password:
        raise HTTPException(
            status_code=400,
            detail="Password is required"
        )

    if not data.email and not data.username:
        raise HTTPException(
            status_code=400,
            detail="Provide either email or username"
        )
    find_user = select(User).where(
                or_(
                    func.lower(User.username) == data.username.lower() if data.username else False,
                    func.lower(User.email) == data.email.lower() if data.email else False
                )
            )
    result = await db.execute(find_user)
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=400, detail="User not Found")
    if not verify_password(data.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Password is not valid !")
    token_payload = {
        "sub":str(user.id),
        "username":user.username,
        "email": user.email
    }
    access_token = create_access_token(token_payload)
    refresh_token = create_refresh_token(token_payload)
    user.access_token = access_token
    user.refresh_token = refresh_token
    db.add(user)
    await db.commit()
    await db.refresh(user)

    # Access Token stored in cookies
    response.set_cookie(
        key="access_token",
        value=access_token,
        secure=settings.PRODUCTION,
        httponly=True,
        samesite="none" if settings.PRODUCTION else "lax",
        max_age=settings.ACCESS_TOKEN_EXPIRY * 60,
        expires=settings.ACCESS_TOKEN_EXPIRY * 60,
        path="/"
    )

    # Refresh Token stored in cookies
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        secure=settings.PRODUCTION,
        httponly=True,
        samesite="none" if settings.PRODUCTION else "lax",
        max_age=settings.REFRESH_TOKEN_EXPIRY * 24 * 60 * 60,
        expires=settings.REFRESH_TOKEN_EXPIRY * 24 * 60 * 60,
        path="/"
    )

    return user


async def logout_user(response):
    response.delete_cookie(
        key="access_token",
        path="/",
        secure=settings.PRODUCTION,
        samesite="none" if settings.PRODUCTION else "lax"
    )
    response.delete_cookie(
        key="refresh_token",
        path="/",
        secure=settings.PRODUCTION,
        samesite="none" if settings.PRODUCTION else "lax"
    )
    return {"message": "Logged out successfully"}

async def current_user(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_async_session)],
):
    token = request.cookies.get("access_token")

    if not token:
        raise HTTPException(
            status_code=401,
            detail="User Not authenticated"
        )

    try:
        payload = jwt.decode(
            token,
            settings.ACCESS_TOKEN_SECRET,
            algorithms=["HS256"]
        )

        user_id = payload.get("sub")

    except PyJWTError:
        raise HTTPException(
            status_code=401,
            detail="Invalid token"
        )

    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalars().first()

    if not user:
        raise HTTPException(
            status_code=404,
            detail="User not found"
        )

    return user

async def update_username(new_username: str, user: User,  db: AsyncSession):
    new_username = new_username.strip()
    if not new_username:
        raise HTTPException(status_code=400, detail="New username is required")
    if new_username == user.username:
        raise HTTPException(status_code=400, detail="New username cannot be the same as the current username")
    if new_username.lower() == user.username.lower():
        raise HTTPException(status_code=400, detail="New username cannot differ only in case from the current username")
    if len(new_username) < 3 or len(new_username) > 50:
        raise HTTPException(status_code=400, detail="Username must be between 3 and 50 characters")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Inactive users cannot update username")
    try:
        stmt = select(User).where(User.username == new_username)
        result = await db.execute(stmt)
        existing_user = result.scalars().first()
        if existing_user:
            raise HTTPException(status_code=409, detail="Username already in use.")
        user.username = new_username
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user

    except HTTPException:
        await db.rollback()
        raise

    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )
    

async def update_email(new_email: str, user: User,  db: AsyncSession):
    new_email = new_email.strip()
    if not new_email:
        raise HTTPException(status_code=400, detail="New email is required")
    if new_email == user.email:
        raise HTTPException(status_code=400, detail="New email cannot be the same as the current email")
    if new_email.lower() == user.email.lower():
        raise HTTPException(status_code=400, detail="New email cannot differ only in case from the current email")
    if len(new_email) < 3 or len(new_email) > 50:
        raise HTTPException(status_code=400, detail="email must be between 3 and 50 characters")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Inactive users cannot update email")
    try:
        stmt = select(User).where(User.email == new_email)
        result = await db.execute(stmt)
        existing_user = result.scalars().first()
        if existing_user:
            raise HTTPException(status_code=409, detail="email already in use.")
        user.email = new_email
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user

    except HTTPException:
        await db.rollback()
        raise

    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Internal server error"
        )



async def refresh_token_user(
    request: Request,
    response: Response,
    db: AsyncSession,
) -> User:
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(
            status_code=401,
            detail="Refresh token missing"
        )

    try:
        payload = jwt.decode(
            refresh_token,
            settings.REFRESH_TOKEN_SECRET,
            algorithms=["HS256"]
        )
        user_id = payload.get("sub")
    except PyJWTError:
        raise HTTPException(
            status_code=401,
            detail="Invalid refresh token"
        )

    stmt = select(User).where(User.id == user_id)
    result = await db.execute(stmt)
    user = result.scalars().first()

    if not user or user.refresh_token != refresh_token:
        raise HTTPException(
            status_code=401,
            detail="User not found or refresh token mismatch"
        )

    # Generate new tokens
    token_payload = {
        "sub": str(user.id),
        "username": user.username,
        "email": user.email
    }
    new_access_token = create_access_token(token_payload)
    new_refresh_token = create_refresh_token(token_payload)

    user.access_token = new_access_token
    user.refresh_token = new_refresh_token
    db.add(user)
    await db.commit()
    await db.refresh(user)

    # Set new cookies
    response.set_cookie(
        key="access_token",
        value=new_access_token,
        secure=settings.PRODUCTION,
        httponly=True,
        samesite="none" if settings.PRODUCTION else "lax",
        max_age=settings.ACCESS_TOKEN_EXPIRY * 60,
        expires=settings.ACCESS_TOKEN_EXPIRY * 60,
        path="/"
    )

    response.set_cookie(
        key="refresh_token",
        value=new_refresh_token,
        secure=settings.PRODUCTION,
        httponly=True,
        samesite="none" if settings.PRODUCTION else "lax",
        max_age=settings.REFRESH_TOKEN_EXPIRY * 24 * 60 * 60,
        expires=settings.REFRESH_TOKEN_EXPIRY * 24 * 60 * 60,
        path="/"
    )

    return user



