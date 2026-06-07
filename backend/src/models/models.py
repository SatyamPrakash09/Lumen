from datetime import datetime, UTC
import uuid

from fastapi_users_db_sqlalchemy import SQLAlchemyBaseUserTableUUID
from sqlalchemy import (
    Uuid,
    Column,
    String,
    Integer,
    DateTime,
    Text,
    ForeignKey,
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

    title = Column(
        String,
        nullable=True,
        default="New Chat"
    )

    # embedding_status tracks if ALL session documents are embedded:
    # pending | processing | ready | failed
    embedding_status = Column(
        String,
        nullable=False,
        default="pending"
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

    session_documents = relationship(
        "Documents",
        back_populates="session",
        cascade="all, delete-orphan",
        foreign_keys="Documents.session_id"
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

    # Optional: link to a specific chat session
    session_id = Column(
        String,
        ForeignKey(
            "chat_sessions.session_id",
            ondelete="CASCADE"
        ),
        nullable=True,
        index=True
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

    # pending | processing | ready | failed
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

    session = relationship(
        "ChatSession",
        back_populates="session_documents",
        foreign_keys=[session_id]
    )