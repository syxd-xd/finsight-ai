from database import SessionLocal
from models import AgentRun, ResearchJob
from schemas import AgentRunUpdate
from crud import update_agent_run
from agents.financial_statement import fetch_financial_statements


def run_financial_agent(agent_run_id: int, ticker_symbol: str, fiscal_year: int):
    db = SessionLocal()

    try:
        # Find the requested agent record
        agent = db.query(AgentRun).filter(
            AgentRun.id == agent_run_id
        ).first()

        if agent is None:
            raise ValueError(f"Agent run {agent_run_id} was not found.")

        if agent.agent_type != "financial_statement":
            raise ValueError("This agent is not a financial_statement agent.")

        if agent.status != "pending":
            raise ValueError(
                f"Agent must be pending before execution. Current status: {agent.status}"
            )

        # Mark the agent as running
        update_agent_run(
            db,
            agent_run_id,
            AgentRunUpdate(status="running")
        )

        # Fetch financial data from SEC EDGAR
        result = fetch_financial_statements(
            ticker_symbol=ticker_symbol,
            fiscal_year=fiscal_year
        )

        # Save the retrieved data and mark the agent as completed
        update_agent_run(
            db,
            agent_run_id,
            AgentRunUpdate(
                status="completed",
                output_data=result
            )
        )

        print(f"Agent {agent_run_id} completed successfully.")
        print(f"Company: {result['company_name']}")
        print(f"Fiscal year: {result['fiscal_year']}")
        print("Financial metrics saved to MySQL.")

    except Exception as exc:
        db.rollback()

        # If the agent was marked running, record the failure.
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
    run_financial_agent(
        agent_run_id=7,
        ticker_symbol="AAPL",
        fiscal_year=2025
    )
