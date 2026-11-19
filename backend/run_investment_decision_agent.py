"""Runner for the investment decision agent."""

from sqlalchemy import select

from agents.investment_decision import assess_investment
from crud import update_agent_run
from database import SessionLocal
from models import AgentRun, ResearchJob
from schemas import AgentRunUpdate


RESEARCH_AGENT_TYPES = (
    "financial_statement",
    "news_research",
    "market_data",
    "risk_analysis",
    "competitor_analysis",
)


def run_investment_decision_agent(agent_run_id: int):
    db = SessionLocal()
    try:
        agent = db.get(AgentRun, agent_run_id)
        if agent is None:
            raise ValueError(f"Agent run {agent_run_id} was not found.")
        if agent.agent_type != "investment_decision":
            raise ValueError("This is not an investment_decision agent.")
        if agent.status != "pending":
            raise ValueError(f"Agent must be pending. Current status: {agent.status}")

        research_job_id = agent.research_job_id
        research_job = db.get(ResearchJob, research_job_id)
        if research_job is None:
            raise ValueError(f"Research job {research_job_id} was not found.")

        update_agent_run(db, agent_run_id, AgentRunUpdate(status="running"))

        outputs = {}
        for agent_type in RESEARCH_AGENT_TYPES:
            prior = db.scalar(
                select(AgentRun).where(
                    AgentRun.research_job_id == research_job_id,
                    AgentRun.agent_type == agent_type,
                )
            )
            if prior is None or prior.status != "completed":
                raise ValueError(f"Required {agent_type} agent is not completed.")
            if prior.output_data is None:
                raise ValueError(f"Required {agent_type} agent has no output data.")
            outputs[agent_type] = prior.output_data

        result = assess_investment(
            financial_data=outputs["financial_statement"],
            news_data=outputs["news_research"],
            market_data=outputs["market_data"],
            risk_data=outputs["risk_analysis"],
            competitor_data=outputs["competitor_analysis"],
        )
        update_agent_run(
            db,
            agent_run_id,
            AgentRunUpdate(status="completed", output_data=result),
        )
        print(f"Investment Decision Agent {agent_run_id} completed successfully.")
        print(f"Assessment: {result['investment_assessment']}")
        print(f"Overall score: {result['overall_score']}")
        return result
    except Exception as exc:
        db.rollback()
        agent = db.get(AgentRun, agent_run_id)
        if agent is not None and agent.status == "running":
            update_agent_run(
                db,
                agent_run_id,
                AgentRunUpdate(status="failed", error_message=str(exc)),
            )
        raise
    finally:
        db.close()


if __name__ == "__main__":
    run_investment_decision_agent(agent_run_id=13)
