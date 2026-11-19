from database import SessionLocal
from models import AgentRun
from schemas import AgentRunUpdate
from crud import update_agent_run
from agents.market_data import fetch_market_data
from utils.json_sanitizer import sanitize_json


def run_market_agent(agent_run_id: int, ticker_symbol: str, as_of_date=None):

    db = SessionLocal()

    try:
        # Find the requested agent record
        agent = db.query(AgentRun).filter(
            AgentRun.id == agent_run_id
        ).first()

        if agent is None:
            raise ValueError(f"Agent run {agent_run_id} was not found.")

        if agent.agent_type != "market_data":
            raise ValueError("This agent is not a market_data agent.")

        if agent.status != "pending":
            raise ValueError(
                f"Agent must be pending. Current status: {agent.status}"
            )

        # Mark agent as running
        update_agent_run(
            db,
            agent_run_id,
            AgentRunUpdate(status="running")
        )

        # Fetch market data
        result = sanitize_json(fetch_market_data(ticker_symbol, as_of_date=as_of_date))

        # Save results in MySQL
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
        print(f"Trading days: {result['total_trading_days']}")
        print("Market data saved to MySQL.")

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
    run_market_agent(
        agent_run_id=9,
        ticker_symbol="AAPL"
    )
