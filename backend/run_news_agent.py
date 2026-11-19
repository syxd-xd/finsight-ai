from database import SessionLocal
from models import AgentRun
from schemas import AgentRunUpdate
from crud import update_agent_run
from agents.news_research import fetch_company_news


def run_news_agent(agent_run_id: int, company_name: str, ticker_symbol: str, news_period_start=None, news_period_end=None):

    db = SessionLocal()

    try:
        agent = db.query(AgentRun).filter(
            AgentRun.id == agent_run_id
        ).first()

        if agent is None:
            raise ValueError(f"Agent run {agent_run_id} was not found.")

        if agent.agent_type != "news_research":
            raise ValueError("This agent is not a news_research agent.")

        if agent.status != "pending":
            raise ValueError(
                f"Agent must be pending before execution. Current status: {agent.status}"
            )

        # Mark agent as running
        update_agent_run(
            db,
            agent_run_id,
            AgentRunUpdate(status="running")
        )

        # Fetch company news
        result = fetch_company_news(
            company_name=company_name,
            ticker_symbol=ticker_symbol,
            news_period_start=news_period_start,
            news_period_end=news_period_end,
        )

        # Save news data in MySQL
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
        print(f"Articles retrieved: {len(result['articles'])}")
        print("News articles saved to MySQL.")

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
    run_news_agent(
        agent_run_id=8,
        company_name="Apple Inc.",
        ticker_symbol="AAPL"
    )
