from collections.abc import Generator

from datetime import datetime

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from crud import (
    create_company,
    get_companies,
    get_company_by_ticker,
    create_research_job,
    get_research_jobs,
    get_research_job_by_id,
    create_agent_runs,
    update_agent_run,
)
from database import SessionLocal
from models import AgentRun, ResearchJob
from services.research_orchestrator import REQUIRED_AGENTS, run_research_job
from schemas import (
    CompanyCreate,
    CompanyResponse,
    ResearchJobCreate,
    ResearchJobResponse,
    ResearchReportResponse,
    AgentRunResponse,
    AgentRunUpdate,
)

app = FastAPI(
    title="FinSight AI",
    description="Multi-Agent Financial Research Platform",
    version="0.2.0",
)

# Allow the vanilla frontend when served from a local development server.
# The API remains unauthenticated as before; restrict browser origins to loopback.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Accept", "Content-Type"],
)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()


@app.get("/")
def home():
    return {
        "application": "FinSight AI",
        "status": "running",
        "message": "Welcome to FinSight AI!",
    }


@app.get("/health")
def health(db: Session = Depends(get_db)):
    try:
        db.connection()
        return {
            "status": "healthy",
            "database": "connected",
        }
    except Exception:
        raise HTTPException(
            status_code=503,
            detail="Database unavailable",
        )


@app.post(
    "/api/companies",
    response_model=CompanyResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_company(
    company_data: CompanyCreate,
    db: Session = Depends(get_db),
):
    existing_company = get_company_by_ticker(
        db,
        company_data.ticker_symbol,
        company_data.exchange,
    )

    if existing_company:
        raise HTTPException(
            status_code=409,
            detail="This company ticker and exchange are already registered.",
        )

    try:
        return create_company(db, company_data)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="A company with this ticker and exchange already exists.",
        )


@app.get(
    "/api/companies",
    response_model=list[CompanyResponse],
)
def list_companies(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    if skip < 0 or not 1 <= limit <= 100:
        raise HTTPException(
            status_code=400,
            detail="skip must be non-negative and limit must be between 1 and 100.",
        )

    return get_companies(db, skip=skip, limit=limit)


@app.get(
    "/api/companies/{ticker_symbol}",
    response_model=CompanyResponse,
)
def find_company(
    ticker_symbol: str,
    exchange: str,
    db: Session = Depends(get_db),
):
    company = get_company_by_ticker(
        db,
        ticker_symbol,
        exchange,
    )

    if company is None:
        raise HTTPException(
            status_code=404,
            detail="Company not found.",
        )

    return company


@app.post(
    "/api/research-jobs",
    response_model=ResearchJobResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_research_job(
    job_data: ResearchJobCreate,
    db: Session = Depends(get_db),
):
    job = create_research_job(db, job_data)

    if job is None:
        raise HTTPException(
            status_code=404,
            detail="Company not found. Register the company first.",
        )

    return job


@app.get(
    "/api/research-jobs",
    response_model=list[ResearchJobResponse],
)
def list_research_jobs(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    if skip < 0 or not 1 <= limit <= 100:
        raise HTTPException(
            status_code=400,
            detail="skip must be non-negative and limit must be between 1 and 100.",
        )

    return get_research_jobs(db, skip=skip, limit=limit)


@app.get(
    "/api/research-jobs/{job_id}",
    response_model=ResearchJobResponse,
)
def read_research_job(
    job_id: int,
    db: Session = Depends(get_db),
):
    job = get_research_job_by_id(db, job_id)

    if job is None:
        raise HTTPException(
            status_code=404,
            detail="Research job not found.",
        )

    return job


@app.get(
    "/api/research-jobs/{job_id}/report",
    response_model=ResearchReportResponse,
)
def read_research_report(
    job_id: int,
    db: Session = Depends(get_db),
):
    job = get_research_job_by_id(db, job_id)

    if job is None:
        raise HTTPException(
            status_code=404,
            detail="Research job not found.",
        )

    report_run = db.scalar(
        select(AgentRun).where(
            AgentRun.research_job_id == job_id,
            AgentRun.agent_type == "report_generation",
        )
    )

    if report_run is None or report_run.status in {"pending", "running"}:
        raise HTTPException(
            status_code=409,
            detail="The consolidated report is not available yet; report generation is pending or running.",
        )

    if report_run.status == "failed":
        reason = report_run.error_message or "No failure details were recorded."
        raise HTTPException(
            status_code=500,
            detail=f"Report generation failed: {reason}",
        )

    if report_run.status != "completed":
        raise HTTPException(
            status_code=409,
            detail=f"Report generation has an unsupported status: {report_run.status}.",
        )

    if report_run.output_data is None:
        raise HTTPException(
            status_code=500,
            detail="Report generation completed without storing report output.",
        )

    return {
        "research_job_id": job.id,
        "company_name": job.company.company_name,
        "ticker_symbol": job.company.ticker_symbol,
        "research_job_status": job.status,
        "report": report_run.output_data,
    }


@app.get(
    "/api/research-jobs/{job_id}/agents",
    response_model=list[AgentRunResponse],
)
def list_research_job_agents(
    job_id: int,
    db: Session = Depends(get_db),
):
    try:
        job = get_research_job_by_id(db, job_id)

        if job is None:
            raise HTTPException(
                status_code=404,
                detail="Research job not found.",
            )

        agent_runs = list(
            db.scalars(
                select(AgentRun).where(AgentRun.research_job_id == job_id)
            ).all()
        )
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=503,
            detail="Unable to retrieve research agents because the database is unavailable.",
        ) from exc

    execution_order = {
        agent_type: index
        for index, agent_type in enumerate(REQUIRED_AGENTS)
    }
    agent_runs.sort(
        key=lambda run: (
            execution_order.get(run.agent_type, len(execution_order)),
            run.id,
        )
    )
    return agent_runs


@app.post(
    "/api/research-jobs/{job_id}/run",
    response_model=ResearchJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_research_job(
    job_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Queue the seven-agent workflow and return the job's running state."""
    job = db.get(ResearchJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Research job not found.")

    if job.status != "pending":
        raise HTTPException(
            status_code=409,
            detail=f"Only pending research jobs can be started (current status: {job.status}).",
        )

    agents = list(
        db.scalars(
            select(AgentRun).where(AgentRun.research_job_id == job_id)
        ).all()
    )
    agent_map = {agent.agent_type: agent for agent in agents}
    missing = [kind for kind in REQUIRED_AGENTS if kind not in agent_map]
    if missing:
        raise HTTPException(
            status_code=409,
            detail="Initialize all research agents before starting. Missing: "
            + ", ".join(missing),
        )
    non_pending = [
        kind for kind in REQUIRED_AGENTS if agent_map[kind].status != "pending"
    ]
    if non_pending:
        raise HTTPException(
            status_code=409,
            detail="All research agents must be pending. Not pending: "
            + ", ".join(non_pending),
        )
    if job.research_period_end is None:
        raise HTTPException(
            status_code=422,
            detail="A research period end date is required to determine the fiscal year.",
        )

    job.status = "running"
    job.started_at = job.started_at or datetime.utcnow()
    job.completed_at = None
    job.error_message = None
    db.commit()
    db.refresh(job)
    background_tasks.add_task(run_research_job, job_id)
    return job


@app.post(
    "/api/research-jobs/{job_id}/agents",
    response_model=list[AgentRunResponse],
)
def initialize_research_agents(
    job_id: int,
    db: Session = Depends(get_db),
):
    agent_runs = create_agent_runs(db, job_id)

    if agent_runs is None:
        raise HTTPException(
            status_code=404,
            detail="Research job not found.",
        )

    return agent_runs


@app.patch(
    "/api/agent-runs/{agent_run_id}",
    response_model=AgentRunResponse,
)
def modify_agent_run(
    agent_run_id: int,
    update_data: AgentRunUpdate,
    db: Session = Depends(get_db),
):
    try:
        agent = update_agent_run(
            db,
            agent_run_id,
            update_data,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        )

    if agent is None:
        raise HTTPException(
            status_code=404,
            detail="Agent run not found.",
        )

    return agent
