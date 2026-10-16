from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, Date, DateTime, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from bot.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    full_name: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(32), default="cook")
    station: Mapped[str | None] = mapped_column(String(128), nullable=True)
    rate_type: Mapped[str] = mapped_column(String(8), default="day")
    rate_amount: Mapped[float] = mapped_column(Numeric(10, 2), default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Invite(Base):
    __tablename__ = "invites"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255))
    station: Mapped[str | None] = mapped_column(String(128), nullable=True)
    role: Mapped[str] = mapped_column(String(32), default="cook")
    created_by: Mapped[int] = mapped_column(BigInteger)
    is_used: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class SalaryEntry(Base):
    __tablename__ = "salary_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)
    entry_type: Mapped[str] = mapped_column(String(16))
    value: Mapped[float] = mapped_column(Numeric(10, 2))
    amount: Mapped[float] = mapped_column(Numeric(12, 2))
    entry_date: Mapped[date] = mapped_column(Date, index=True)
    year: Mapped[int] = mapped_column(Integer)
    month: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class SalaryReport(Base):
    __tablename__ = "salary_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, index=True)
    year: Mapped[int] = mapped_column(Integer)
    month: Mapped[int] = mapped_column(Integer)
    total_shifts: Mapped[float] = mapped_column(Numeric(10, 2))
    total_penalty: Mapped[float] = mapped_column(Numeric(12, 2))
    total_advance: Mapped[float] = mapped_column(Numeric(12, 2))
    total_accrued: Mapped[float] = mapped_column(Numeric(12, 2))
    remainder: Mapped[float] = mapped_column(Numeric(12, 2))
    details: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON с деталями
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
