from database import SessionLocal
from models import AgentRun
from schemas import AgentRunUpdate
from crud import update_agent_run
from agents.risk_analysis import analyze_financial_risk


def run_risk_agent(agent_run_id: int):

    db = SessionLocal()

    try:
        agent = db.query(AgentRun).filter(
            AgentRun.id == agent_run_id
        ).first()

        if agent is None:
            raise ValueError(f"Agent run {agent_run_id} was not found.")

        if agent.agent_type != "risk_analysis":
            raise ValueError("This agent is not a risk_analysis agent.")

        if agent.status != "pending":
            raise ValueError(
                f"Agent must be pending. Current status: {agent.status}"
            )

        research_job_id = agent.research_job_id

        financial_agent = db.query(AgentRun).filter(
            AgentRun.research_job_id == research_job_id,
            AgentRun.agent_type == "financial_statement",
            AgentRun.status == "completed"
        ).first()

        market_agent = db.query(AgentRun).filter(
            AgentRun.research_job_id == research_job_id,
            AgentRun.agent_type == "market_data",
            AgentRun.status == "completed"
        ).first()

        if financial_agent is None or market_agent is None:
            raise ValueError("Required financial or market data is missing.")

        if not financial_agent.output_data or not market_agent.output_data:
            raise ValueError("Required agent output data is empty.")

        update_agent_run(
            db,
            agent_run_id,
            AgentRunUpdate(status="running")
        )

        print("FINANCIAL METRICS:")
        print(financial_agent.output_data.get("financial_metrics"))
        result = analyze_financial_risk(
            financial_agent.output_data,
            market_agent.output_data
        )

        update_agent_run(
            db,
            agent_run_id,
            AgentRunUpdate(
                status="completed",
                output_data=result
            )
        )

        print(f"Risk Analysis Agent {agent_run_id} completed successfully.")
        print(f"Ticker: {result['ticker_symbol']}")
        print("Risk analysis saved to MySQL.")

    except Exception as exc:
        db.rollback()

        agent = db.query(AgentRun).filter(
            AgentRun.id == agent_run_id
        ).first()

        if agent is not None and agent.status == "running":
            update_agent_run(
                db,
                agent_run_id,
                AgentRunUpdate(
                    status="failed",
                    error_message=str(exc)
                )
            )

        raise

    finally:
        db.close()


if __name__ == "__main__":
    run_risk_agent(agent_run_id=10)
