from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class Company(Base):
    __tablename__ = "companies"

    __table_args__ = (
        UniqueConstraint(
            "exchange",
            "ticker_symbol",
            name="uq_company_exchange_ticker",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    company_name: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True
    )
    ticker_symbol: Mapped[str] = mapped_column(
        String(32), nullable=False
    )
    exchange: Mapped[str] = mapped_column(
        String(100), nullable=False
    )
    country: Mapped[str] = mapped_column(
        String(100), nullable=False
    )
    sector: Mapped[str | None] = mapped_column(
        String(150), nullable=True
    )
    industry: Mapped[str | None] = mapped_column(
        String(150), nullable=True
    )
    currency: Mapped[str | None] = mapped_column(
        String(10), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    research_jobs: Mapped[list["ResearchJob"]] = relationship(
        back_populates="company"
    )


class ResearchJob(Base):
    __tablename__ = "research_jobs"

    __table_args__ = (
        Index("ix_research_user_created", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    user_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True
    )
    company_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(30), default="pending", nullable=False
    )
    research_period_start: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    research_period_end: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    company: Mapped["Company"] = relationship(
        back_populates="research_jobs"
    )
    agent_runs: Mapped[list["AgentRun"]] = relationship(
        back_populates="research_job"
    )


class AgentRun(Base):
    __tablename__ = "agent_runs"

    __table_args__ = (
        UniqueConstraint(
            "research_job_id",
            "agent_type",
            name="uq_agent_job_type",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    research_job_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("research_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    agent_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(30), default="pending", nullable=False
    )
    input_data: Mapped[dict | None] = mapped_column(
        JSON, nullable=True
    )
    output_data: Mapped[dict | None] = mapped_column(
        JSON, nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    research_job: Mapped["ResearchJob"] = relationship(
        back_populates="agent_runs"
    )
