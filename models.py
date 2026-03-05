from typing import List, Literal, Optional

from pydantic import BaseModel


class Company(BaseModel):
    name: str
    website: Optional[str] = None
    industry: Optional[str] = None
    employee_count: Optional[int] = None
    revenue: Optional[str] = None
    location: Optional[str] = None


class Lead(BaseModel):
    first_name: str
    last_name: str
    email: Optional[str] = None
    job_title: Optional[str] = None
    linkedin_url: Optional[str] = None
    page_visited: Optional[str] = None
    company: Company


class QualificationResult(BaseModel):
    classification: Literal["High ICP", "Potential ICP", "Not ICP"]
    intent_level: Literal["High", "Medium", "Low"]
    reasons: List[str]
    email_subject: str
    email_body: str


LeadStatus = Literal[
    "pending_review",
    "emailed",
    "follow_up_1_sent",
    "follow_up_2_sent",
    "follow_up_3_sent",
    "replied",
    "rejected",
    "not_icp",
]


class LeadRecord(BaseModel):
    id: int
    email: Optional[str] = None
    linkedin_url: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    job_title: Optional[str] = None
    company_name: Optional[str] = None
    company_website: Optional[str] = None
    company_industry: Optional[str] = None
    company_employee_count: Optional[int] = None
    company_revenue: Optional[str] = None
    company_location: Optional[str] = None
    page_visited: Optional[str] = None
    classification: Optional[str] = None
    intent_level: Optional[str] = None
    reasons_json: Optional[str] = None
    initial_email_subject: Optional[str] = None
    initial_email_body: Optional[str] = None
    status: str
    email_sent_at: Optional[str] = None
    follow_up_1_sent_at: Optional[str] = None
    follow_up_2_sent_at: Optional[str] = None
    follow_up_3_sent_at: Optional[str] = None
    replied_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
