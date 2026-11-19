from database import SessionLocal
from models import AgentRun
from schemas import AgentRunUpdate
from crud import update_agent_run

from agents.report_generation import generate_research_report


def run_report_agent(agent_run_id: int):

    db = SessionLocal()

    try:
        # Find report generation agent
        report_agent = db.query(AgentRun).filter(
            AgentRun.id == agent_run_id
        ).first()

        if report_agent is None:
            raise ValueError(
                f"Agent {agent_run_id} was not found."
            )

        if report_agent.agent_type != "report_generation":
            raise ValueError(
                "This is not a report_generation agent."
            )

        if report_agent.status != "pending":
            raise ValueError(
                f"Agent must be pending. Current status: "
                f"{report_agent.status}"
            )

        research_job_id = report_agent.research_job_id

        # Retrieve all five research agents and the completed decision.
        agent_types = [
            "financial_statement",
            "news_research",
            "market_data",
            "risk_analysis",
            "competitor_analysis",
            "investment_decision",
        ]

        agent_outputs = {}

        for agent_type in agent_types:

            previous_agent = db.query(AgentRun).filter(
                AgentRun.research_job_id == research_job_id,
                AgentRun.agent_type == agent_type,
                AgentRun.status == "completed"
            ).first()

            if previous_agent is None:
                raise ValueError(
                    f"{agent_type} agent is not completed."
                )

            if not previous_agent.output_data:
                raise ValueError(
                    f"{agent_type} agent has no output data."
                )

            agent_outputs[agent_type] = previous_agent.output_data

        # Mark report agent as running
        update_agent_run(
            db,
            agent_run_id,
            AgentRunUpdate(status="running")
        )

        # Get company information
        company_name = (
            agent_outputs["financial_statement"]
            .get("company_name", "Unknown Company")
        )

        ticker_symbol = (
            agent_outputs["financial_statement"]
            .get("ticker_symbol", "UNKNOWN")
        )

        # Generate consolidated report
        report = generate_research_report(
            company_name=company_name,
            ticker_symbol=ticker_symbol,
            financial_data=agent_outputs["financial_statement"],
            news_data=agent_outputs["news_research"],
            market_data=agent_outputs["market_data"],
            risk_data=agent_outputs["risk_analysis"],
            competitor_data=agent_outputs["competitor_analysis"],
            investment_data=agent_outputs["investment_decision"],
        )

        # Save report to MySQL
        update_agent_run(
            db,
            agent_run_id,
            AgentRunUpdate(
                status="completed",
                output_data=report
            )
        )

        print("\n===================================")
        print("REPORT GENERATION SUCCESSFUL")
        print("===================================")

        print("Company:", company_name)
        print("Ticker:", ticker_symbol)
        print("Report:", report["report_title"])

        print("\nAll five research agents and the investment decision were collected.")

        print("\nReport successfully saved to MySQL.")

    except Exception as exc:

        db.rollback()

        report_agent = db.query(AgentRun).filter(
            AgentRun.id == agent_run_id
        ).first()

        if report_agent is not None and report_agent.status == "running":

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

    run_report_agent(agent_run_id=12)
