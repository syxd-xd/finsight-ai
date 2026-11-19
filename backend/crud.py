from utils.json_sanitizer import sanitize_json
from schemas import CompanyCreate, ResearchJobCreate
from models import AgentRun, Company, ResearchJob
from sqlalchemy.orm import Session
from sqlalchemy import select
from datetime import datetime, timezone



# Keep the JSON sanitizer already implemented in your project.
# If its exported function has a different name, use that exact name.


AGENT_TYPES = [
    "financial_statement",
    "news_research",
    "market_data",
    "risk_analysis",
    "competitor_analysis",
    "investment_decision",
    "report_generation",
]


def utc_now():
    return datetime.now(timezone.utc)


# --------------------------------------------------
# COMPANY FUNCTIONS
# --------------------------------------------------

def get_company_by_ticker(
    db: Session,
    ticker_symbol: str,
    exchange: str,
):
    statement = select(Company).where(
        Company.ticker_symbol == ticker_symbol.upper(),
        Company.exchange == exchange,
    )

    return db.scalar(statement)


def create_company(
    db: Session,
    company_data: CompanyCreate,
):
    data = company_data.model_dump()
    data["ticker_symbol"] = data["ticker_symbol"].upper()

    company = Company(**data)

    try:
        db.add(company)
        db.commit()
        db.refresh(company)

    except Exception:
        db.rollback()
        raise

    return company


def get_companies(
    db: Session,
    skip: int = 0,
    limit: int = 50,
):
    statement = (
        select(Company)
        .order_by(Company.id.desc())
        .offset(skip)
        .limit(limit)
    )

    return list(db.scalars(statement).all())


# --------------------------------------------------
# RESEARCH JOB FUNCTIONS
# --------------------------------------------------

def create_research_job(
    db: Session,
    job_data: ResearchJobCreate,
):
    company = db.get(Company, job_data.company_id)

    if company is None:
        return None

    if job_data.research_period_start > job_data.research_period_end:
        raise ValueError(
            "Research start date cannot be after the end date."
        )

    job = ResearchJob(
        company_id=job_data.company_id,
        research_period_start=job_data.research_period_start,
        research_period_end=job_data.research_period_end,
        status="pending",
    )

    try:
        db.add(job)
        db.commit()
        db.refresh(job)

    except Exception:
        db.rollback()
        raise

    return job


def get_research_jobs(
    db: Session,
    skip: int = 0,
    limit: int = 50,
):
    statement = (
        select(ResearchJob)
        .order_by(ResearchJob.id.desc())
        .offset(skip)
        .limit(limit)
    )

    return list(db.scalars(statement).all())


def get_research_job_by_id(
    db: Session,
    job_id: int,
):
    return db.get(ResearchJob, job_id)


# --------------------------------------------------
# AGENT INITIALIZATION
# --------------------------------------------------

def create_agent_runs(
    db: Session,
    research_job_id: int,
):
    research_job = db.get(ResearchJob, research_job_id)

    if research_job is None:
        return None

    existing_runs = list(
        db.scalars(
            select(AgentRun).where(
                AgentRun.research_job_id == research_job_id
            )
        ).all()
    )

    # Do not modify historical or already-started jobs.
    if research_job.status != "pending":
        return existing_runs

    existing_types = {
        run.agent_type for run in existing_runs
    }

    new_runs = [
        AgentRun(
            research_job_id=research_job_id,
            agent_type=agent_type,
            status="pending",
        )
        for agent_type in AGENT_TYPES
        if agent_type not in existing_types
    ]

    try:
        db.add_all(new_runs)
        db.commit()

    except Exception:
        db.rollback()
        raise

    return list(
        db.scalars(
            select(AgentRun)
            .where(
                AgentRun.research_job_id == research_job_id
            )
            .order_by(AgentRun.id)
        ).all()
    )


# --------------------------------------------------
# AGENT UPDATE
# --------------------------------------------------

def update_agent_run(
    db: Session,
    agent_run_id: int,
    update_data,
):
    agent = db.get(AgentRun, agent_run_id)

    if agent is None:
        return None

    # Completed or failed agents cannot be restarted.
    if agent.status in {"completed", "failed"}:
        raise ValueError(
            "This agent has already finished and cannot be updated."
        )

    new_status = update_data.status

    if new_status == "running":

        if agent.status != "pending":
            raise ValueError(
                "Only pending agents can transition to running."
            )

        agent.started_at = utc_now()

    elif new_status in {"completed", "failed"}:

        if agent.status != "running":
            raise ValueError(
                "An agent must be running before it can finish."
            )

        agent.completed_at = utc_now()

    else:
        raise ValueError("Invalid agent status.")

    agent.status = new_status

    # Preserve existing output if no new output was supplied.
    if update_data.output_data is not None:
        agent.output_data = sanitize_json(
            update_data.output_data
        )

    # Preserve existing error information unless updated.
    if update_data.error_message is not None:
        agent.error_message = update_data.error_message

    try:
        db.commit()
        db.refresh(agent)

        sync_research_job_status(
            db,
            agent.research_job_id,
        )

    except Exception:
        db.rollback()
        raise

    return agent


# --------------------------------------------------
# RESEARCH JOB STATUS SYNCHRONIZATION
# --------------------------------------------------

def sync_research_job_status(
    db: Session,
    research_job_id: int,
):
    job = db.get(ResearchJob, research_job_id)

    if job is None:
        return None

    agent_runs = list(
        db.scalars(
            select(AgentRun).where(
                AgentRun.research_job_id == research_job_id
            )
        ).all()
    )

    if not agent_runs:
        job.status = "pending"
        job.started_at = None
        job.completed_at = None

    else:
        statuses = [
            agent.status for agent in agent_runs
        ]

        if any(status == "failed" for status in statuses):

            job.status = "failed"
            job.completed_at = utc_now()

        elif all(status == "completed" for status in statuses):

            job.status = "completed"
            job.completed_at = utc_now()

        elif (
            any(status == "running" for status in statuses)
            or any(status == "completed" for status in statuses)
        ):

            job.status = "running"

            if job.started_at is None:
                job.started_at = utc_now()

            job.completed_at = None

        else:
            job.status = "pending"
            job.started_at = None
            job.completed_at = None

    try:
        db.commit()
        db.refresh(job)

    except Exception:
        db.rollback()
        raise

    return job



