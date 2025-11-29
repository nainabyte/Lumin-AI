# backend/app/api/db/models.py
"""
Strong SQLAlchemy declarative models used by the app.
Defines: User, Conversations, Messages, DataSources (table-per-upload)
"""

from datetime import datetime
from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    Boolean,
    ForeignKey,
    Text,
    JSON,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(80), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(256), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    conversations = relationship("Conversations", back_populates="user", cascade="all, delete-orphan")
    messages = relationship("Messages", back_populates="user", cascade="all, delete-orphan")


class Conversations(Base):
    __tablename__ = "conversations"
    __table_args__ = (UniqueConstraint("id", "user_id", name="uq_conversation_user"),)

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(250), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    metadata = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", back_populates="conversations")
    messages = relationship("Messages", back_populates="conversation", cascade="all, delete-orphan")


class Messages(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    role = Column(String(32), nullable=False)  # e.g. "assistant" or "user"
    content = Column(JSON, nullable=False)     # storing messages as JSON for flexibility
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    conversation = relationship("Conversations", back_populates="messages")
    user = relationship("User", back_populates="messages")


class DataSources(Base):
    """
    Represents uploaded dataset metadata. Each new upload can create a new row.
    The actual table data can be stored in a separate schema/table by the pipeline.
    """
    __tablename__ = "data_sources"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(250), nullable=False, index=True)
    table_name = Column(String(250), nullable=False, unique=True)  # physical table where data was inserted
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    rows = Column(Integer, nullable=True)
    metadata = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # relationship(s) omitted to avoid circular import complexity; can be added if needed
