from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.models import User
from src.database.db import get_async_session
from src.schemas.schema import RegistrationSchema, UserResponseSchema, LoginSchema, UpdateUsernameSchema
from src.controllers.auth_controller import register_user, login_user, logout_user, current_user, refresh_token_user, update_username
from src.utils.limiter import limiter

router = APIRouter()

@router.get("/auth")
def auth():
    return {"message": "Hello From Auth"}


@router.post("/register", response_model=UserResponseSchema)
async def register(
    data: RegistrationSchema,
    db: AsyncSession = Depends(get_async_session)
) -> UserResponseSchema:
    return await register_user(data, db)

@router.post("/login", response_model=UserResponseSchema)
async def login(
    data: LoginSchema,
    response: Response,
    db: AsyncSession = Depends(get_async_session)
) -> UserResponseSchema:
    return await login_user(data, db, response)

@router.post("/logout")
async def logout(response: Response):
    return await logout_user(response)

@router.get("/me", response_model=UserResponseSchema)
@limiter.limit("10/minute")
async def get_current_user(
    request:Request,
    user  = Depends(current_user)
) -> UserResponseSchema:
    return  user

@router.post("/update-username", response_model=UserResponseSchema)
@limiter.limit("5/minute")
async def update_username_route(
    data: UpdateUsernameSchema,
    request: Request,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_async_session)
) -> UserResponseSchema:
    # Call the controller function to update the username
    updated_user = await update_username(data.new_username, user, db)
    return updated_user


@router.post("/refresh", response_model=UserResponseSchema)
@limiter.limit("5/minute")
async def refresh(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_async_session)
) -> UserResponseSchema:
    return await refresh_token_user(request, response, db)

