"""Run five research agents, an investment decision, and the final report."""

from datetime import datetime

from sqlalchemy import select

from database import SessionLocal
from models import AgentRun, Company, ResearchJob
from run_competitor_agent import run_competitor_agent
from run_investment_decision_agent import run_investment_decision_agent
from run_financial_agent import run_financial_agent
from run_market_agent import run_market_agent
from run_news_agent import run_news_agent
from run_report_agent import run_report_agent
from run_risk_agent import run_risk_agent


REQUIRED_AGENTS = (
    "financial_statement",
    "news_research",
    "market_data",
    "risk_analysis",
    "competitor_analysis",
    "investment_decision",
    "report_generation",
)


def run_research_job(research_job_id: int) -> None:
    """Execute a pending research job. Each runner owns its own DB session."""
    db = SessionLocal()
    try:
        research_job = db.get(ResearchJob, research_job_id)
        if research_job is None:
            raise ValueError(f"Research job {research_job_id} was not found.")

        company = db.get(Company, research_job.company_id)
        if company is None:
            raise ValueError("Company associated with this job was not found.")

        agents = list(
            db.scalars(
                select(AgentRun).where(
                    AgentRun.research_job_id == research_job_id
                )
            ).all()
        )
        agent_map = {agent.agent_type: agent for agent in agents}

        missing = [kind for kind in REQUIRED_AGENTS if kind not in agent_map]
        if missing:
            raise ValueError(
                "Research agents have not all been initialized. Missing: "
                + ", ".join(missing)
            )

        if research_job.status not in {"pending", "running"}:
            raise ValueError(
                f"Research job must be pending before execution. "
                f"Current status: {research_job.status}"
            )

        non_pending = [
            f"{kind} ({agent_map[kind].status})"
            for kind in REQUIRED_AGENTS
            if agent_map[kind].status != "pending"
        ]
        if non_pending:
            raise ValueError(
                "All research agents must be pending before execution: "
                + ", ".join(non_pending)
            )

        if research_job.research_period_end is None:
            raise ValueError(
                "A research period end date is required to determine the fiscal year."
            )

        # Copy scalar values before closing the lookup session. The agent runners
        # open and manage their own database sessions.
        ids = {kind: agent_map[kind].id for kind in REQUIRED_AGENTS}
        ticker = company.ticker_symbol
        company_name = company.company_name
        fiscal_year = research_job.research_period_end.year
        news_start = research_job.research_period_start.date().isoformat() if research_job.research_period_start else None
        news_end = research_job.research_period_end.date().isoformat()
        market_as_of = research_job.research_period_end.date()

        research_job.status = "running"
        research_job.started_at = research_job.started_at or datetime.utcnow()
        research_job.completed_at = None
        research_job.error_message = None
        db.commit()
    finally:
        db.close()

    try:
        run_financial_agent(ids["financial_statement"], ticker, fiscal_year)
        run_news_agent(ids["news_research"], company_name, ticker, news_start, news_end)
        run_market_agent(ids["market_data"], ticker, market_as_of)
        run_risk_agent(ids["risk_analysis"])
        run_competitor_agent(ids["competitor_analysis"], ticker)
        run_investment_decision_agent(ids["investment_decision"])
        run_report_agent(ids["report_generation"])
        completion_db = SessionLocal()
        try:
            job = completion_db.get(ResearchJob, research_job_id)
            if job is not None:
                job.status = "completed"
                job.completed_at = datetime.utcnow()
                job.error_message = None
                completion_db.commit()
        finally:
            completion_db.close()
    except Exception as exc:
        # Runners record their own agent failure. Persist the corresponding job
        # error as well, including errors raised before an agent could start.
        failure_db = SessionLocal()
        try:
            job = failure_db.get(ResearchJob, research_job_id)
            if job is not None:
                job.status = "failed"
                job.completed_at = datetime.utcnow()
                job.error_message = str(exc)
                failure_db.commit()
        except Exception:
            failure_db.rollback()
            raise
        finally:
            failure_db.close()
        raise
