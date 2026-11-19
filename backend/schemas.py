from pydantic import BaseModel, ConfigDict, Field, model_validator
from datetime import datetime
from typing import Any, Literal


class CompanyCreate(BaseModel):
    company_name: str = Field(min_length=1, max_length=255)
    ticker_symbol: str = Field(min_length=1, max_length=32)
    exchange: str = Field(min_length=1, max_length=100)
    country: str = Field(min_length=1, max_length=100)
    sector: str | None = None
    industry: str | None = None
    currency: str | None = None


class CompanyResponse(CompanyCreate):
    id: int

    model_config = ConfigDict(from_attributes=True)


class ResearchJobCreate(BaseModel):
    company_id: int = Field(gt=0)
    research_period_start: datetime | None = None
    research_period_end: datetime | None = None

    @model_validator(mode="after")
    def validate_research_period(self):
        if (
            self.research_period_start is not None
            and self.research_period_end is not None
            and self.research_period_start > self.research_period_end
        ):
            raise ValueError(
                "Research period start must be before or equal to the end."
            )
        return self


class ResearchJobResponse(BaseModel):
    id: int
    company_id: int
    status: str
    research_period_start: datetime | None
    research_period_end: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ResearchReportResponse(BaseModel):
    research_job_id: int
    company_name: str
    ticker_symbol: str
    research_job_status: str
    report: dict[str, Any]


class AgentRunResponse(BaseModel):
    id: int
    research_job_id: int
    agent_type: str
    status: str
    input_data: dict | None
    output_data: dict | None
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AgentRunUpdate(BaseModel):
    status: Literal["running", "completed", "failed"]
    output_data: dict | None = None
    error_message: str | None = None
