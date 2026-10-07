from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(80))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="user", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    challenges: Mapped[list["Challenge"]] = relationship(back_populates="creator")
    participations: Mapped[list["Participation"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Challenge(Base):
    __tablename__ = "challenges"
    __table_args__ = (CheckConstraint("target_value > 0", name="ck_challenge_target"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text)
    sport: Mapped[str] = mapped_column(String(50), index=True)
    unit: Mapped[str] = mapped_column(String(30))
    target_value: Mapped[int] = mapped_column(Integer)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    creator: Mapped[User] = relationship(back_populates="challenges")
    participations: Mapped[list["Participation"]] = relationship(back_populates="challenge", cascade="all, delete-orphan")


class Participation(Base):
    __tablename__ = "participations"
    __table_args__ = (UniqueConstraint("user_id", "challenge_id", name="uq_participation_user_challenge"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    challenge_id: Mapped[int] = mapped_column(ForeignKey("challenges.id"), index=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    user: Mapped[User] = relationship(back_populates="participations")
    challenge: Mapped[Challenge] = relationship(back_populates="participations")
    entries: Mapped[list["ProgressEntry"]] = relationship(back_populates="participation", cascade="all, delete-orphan")


class ProgressEntry(Base):
    __tablename__ = "progress_entries"
    __table_args__ = (CheckConstraint("value > 0", name="ck_progress_value"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    participation_id: Mapped[int] = mapped_column(ForeignKey("participations.id"), index=True)
    value: Mapped[int] = mapped_column(Integer)
    note: Mapped[str] = mapped_column(String(240), default="")
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    participation: Mapped[Participation] = relationship(back_populates="entries")
