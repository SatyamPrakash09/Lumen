from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime
import uuid


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


# ==================================
# Chat Session Schemas
# ==================================

class CreateSessionSchema(BaseSchema):
    title: Optional[str] = "New Chat"


class ChatSessionResponseSchema(BaseSchema):
    id: uuid.UUID
    session_id: str
    title: Optional[str]
    embedding_status: str
    created_at: datetime

    class Config:
        from_attributes = True


# ==================================
# Document Schemas
# ==================================

class DocumentResponseSchema(BaseSchema):
    id: uuid.UUID
    file_name: str
    file_type: Optional[str]
    file_size: Optional[int]
    status: str
    total_chunks: int
    session_id: Optional[str]
    uploaded_at: datetime

    class Config:
        from_attributes = True


# ==================================
# Chat / Citation Schemas
# ==================================

class Citation(BaseSchema):
    """
    A single cited source — document chunk, web page, or Wikipedia article.

    type values:
      'document'  — from uploaded files (RAG)
      'web'       — from DuckDuckGo web search
      'wikipedia' — from Wikipedia
    """
    type: str                        # 'document' | 'web' | 'wikipedia'
    title: str                       # filename, page title, or article name
    snippet: Optional[str] = None    # short excerpt from the source
    page: Optional[int] = None       # page number (PDF documents)
    chunk_index: Optional[int] = None  # chunk number within the document
    url: Optional[str] = None        # web / Wikipedia URL


class ChatRequestSchema(BaseSchema):
    query: str


class AgentResponseSchema(BaseSchema):
    """Response from the LangGraph ReAct agent (RAG + web verify)."""
    answer: str
    citations: list[Citation]    # structured, typed citation objects
    sources: list[str]           # convenience: unique source titles / URLs
    tools_used: list[str]        # tools the agent invoked
    session_id: str


class MessageResponseSchema(BaseSchema):
    id: uuid.UUID
    session_id: str
    sender: str
    content: str
    timestamp: datetime

    class Config:
        from_attributes = True


