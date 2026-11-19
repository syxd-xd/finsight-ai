from database import SessionLocal
from models import AgentRun
from schemas import AgentRunUpdate
from crud import update_agent_run

from agents.competitor_analysis import analyze_competitors


def run_competitor_agent(
    agent_run_id: int,
    target_ticker: str
):

    db = SessionLocal()

    try:
        agent = db.query(AgentRun).filter(
            AgentRun.id == agent_run_id
        ).first()

        if agent is None:
            raise ValueError(
                f"Agent run {agent_run_id} was not found."
            )

        if agent.agent_type != "competitor_analysis":
            raise ValueError(
                "This is not a competitor_analysis agent."
            )

        if agent.status != "pending":
            raise ValueError(
                f"Agent must be pending. Current status: {agent.status}"
            )

        update_agent_run(
            db,
            agent_run_id,
            AgentRunUpdate(status="running")
        )

        result = analyze_competitors(
            target_ticker=target_ticker
        )

        update_agent_run(
            db,
            agent_run_id,
            AgentRunUpdate(
                status="completed",
                output_data=result
            )
        )

        print(
            f"Competitor Analysis Agent {agent_run_id} "
            "completed successfully."
        )

        print(
            "Target company:",
            result["target_company"]["company_name"]
        )

        print(
            "Successful competitors:",
            result["comparison_summary"]["successful_comparisons"]
        )

        print("Competitor analysis saved to MySQL.")

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

    run_competitor_agent(
        agent_run_id=11,
        target_ticker="AAPL"
    )
