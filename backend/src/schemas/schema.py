from pydantic import BaseModel, EmailStr
from typing import Optional


class BaseSchema(BaseModel):
    pass


class RegistrationSchema(BaseSchema):
    password: str
    email: EmailStr
    first_name: str
    last_name: Optional[str] = None
    niat_id: str
    avatar: Optional[str] = None  


class LoginSchema(BaseSchema):
    niat_id: Optional[str] = None
    email: Optional[EmailStr] = None
    password: str


class UserResponseSchema(BaseSchema):
    niat_id: str
    email: EmailStr
    first_name: str
    last_name: Optional[str] = None
    avatar: Optional[str] = None
    access_token: str
    refresh_token: str

