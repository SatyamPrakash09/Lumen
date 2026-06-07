from datetime import datetime, UTC
import uuid

from fastapi_users_db_sqlalchemy import SQLAlchemyBaseUserTableUUID
from fastapi import HTTPException
from sqlalchemy import (
    Uuid,
    Column,
    String,
    Integer,
    DateTime,
    Text,
    ForeignKey,
    Uuid
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


# ==================================
# User
# ==================================

class User(SQLAlchemyBaseUserTableUUID, Base):
    __tablename__ = "users"

    niat_id = Column(
        String,
        nullable=False,
        unique=True,
        index=True
    )

    first_name = Column(
        String,
        nullable=False
    )

    last_name = Column(String)

    avatar = Column(String)

    refresh_token = Column(String)

    access_token = Column(String)

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC)
    )

    # Relationships

    chat_sessions = relationship(
        "ChatSession",
        back_populates="user",
        cascade="all, delete-orphan"
    )

    documents = relationship(
        "Documents",
        back_populates="user",
        cascade="all, delete-orphan"
    )


# ==================================
# Chat Session
# ==================================

class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(
        Uuid,
        primary_key=True,
        index=True,
        default=uuid.uuid4
    )

    session_id = Column(
        String,
        unique=True,
        nullable=False,
        index=True
    )

    user_id = Column(
        Uuid,
        ForeignKey(
            "users.id",
            ondelete="CASCADE"
        ),
        nullable=False
    )

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC)
    )

    # Relationships

    user = relationship(
        "User",
        back_populates="chat_sessions"
    )

    messages = relationship(
        "Messages",
        back_populates="chat_session",
        cascade="all, delete-orphan"
    )


# ==================================
# Messages
# ==================================

class Messages(Base):
    __tablename__ = "messages"

    id = Column(
        Uuid,
        primary_key=True,
        index=True,
        default=uuid.uuid4
    )

    session_id = Column(
        String,
        ForeignKey(
            "chat_sessions.session_id",
            ondelete="CASCADE"
        ),
        nullable=False
    )

    sender = Column(
        String,
        nullable=False
    )

    content = Column(
        Text,
        nullable=False
    )

    timestamp = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC)
    )

    # Relationships

    chat_session = relationship(
        "ChatSession",
        back_populates="messages"
    )


# ==================================
# Documents
# ==================================

class Documents(Base):
    __tablename__ = "documents"

    id = Column( 
        Uuid,
        primary_key=True,
        index=True,
        default=uuid.uuid4
    )

    user_id = Column(
        Uuid,
        ForeignKey(
            "users.id",
            ondelete="CASCADE"
        ),
        nullable=False
    )

    file_name = Column(
        String,
        nullable=False
    )

    file_path = Column(
        String,
        nullable=False
    )

    file_type = Column(String)

    file_size = Column(Integer)

    status = Column(
        String,
        default="pending"
    )

    total_chunks = Column(
        Integer,
        default=0
    )

    uploaded_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC)
    )

    # Relationships

    user = relationship(
        "User",
        back_populates="documents"
    )