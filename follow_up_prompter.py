import anthropic
from pydantic import BaseModel


class FollowUpEmail(BaseModel):
    subject: str
    body: str


FOLLOW_UP_ANGLES = {
    1: (
        "Day 3 follow-up",
        "Lead with tariff and supply chain disruption urgency. Reference the current tariff environment "
        "creating unpredictable landed costs and the risk of not having visibility into where exposure sits "
        "across their supplier network. Be specific and timely — this is a hot moment for supply chain leaders.",
    ),
    2: (
        "Day 7 follow-up",
        "Lead with a concrete Nauta proof point: customers using Nauta have seen up to 80% reduction in "
        "detention and demurrage charges. Tie this to the real cost of D&D at their scale (enterprise). "
        "Make it feel like a missed opportunity if they don't take 15 minutes to learn more.",
    ),
    3: (
        "Day 14 final touch",
        "Soft, low-pressure final follow-up. Acknowledge they're busy. Leave the door open. "
        "No hard sell — just a brief note that the offer stands whenever timing is right. "
        "Keep it warm and human. Under 60 words.",
    ),
}

SYSTEM_PROMPT = """You are Gabriela, Head of Growth at Nauta, writing short follow-up emails.

Nauta is an AI-native supply chain operating system.
Tagline: "Anticipate risk and optimize performance with Nauta."
Website: getnauta.com

Rules:
- Always write as Gabriela, Head of Growth at Nauta.
- Sound warm and human, not automated or salesy.
- Reference the original email as context — this is a thread reply, not a cold email.
- Keep each follow-up under 100 words (Day 14 under 60 words).
- Always end with the Calendly link: https://calendly.com/d/cs45-yr4-656
- Do NOT repeat the same phrasing from the original email.
- Each follow-up should feel like a natural next message in a thread."""


def generate_followup(lead_record: dict, followup_number: int) -> dict:
    """
    Generate a follow-up email for a given lead record.

    Args:
        lead_record: Dict from database (leads table row)
        followup_number: 1, 2, or 3

    Returns:
        {"subject": str, "body": str}
    """
    angle_label, angle_instructions = FOLLOW_UP_ANGLES.get(
        followup_number, FOLLOW_UP_ANGLES[3]
    )

    original_subject = lead_record.get("initial_email_subject", "")
    original_body = lead_record.get("initial_email_body", "")

    lead_context = f"""
Lead:
- Name: {lead_record.get('first_name', '')} {lead_record.get('last_name', '')}
- Title: {lead_record.get('job_title') or 'Unknown'}
- Company: {lead_record.get('company_name') or 'Unknown'}
- Industry: {lead_record.get('company_industry') or 'Unknown'}
- Company size: {lead_record.get('company_employee_count') or 'Unknown'} employees
- Page visited on getnauta.com: {lead_record.get('page_visited') or 'Unknown'}

Original email sent:
Subject: {original_subject}
Body:
{original_body}
"""

    prompt = f"""Write follow-up #{followup_number} ({angle_label}) for this lead.

Angle: {angle_instructions}

{lead_context}

Write the follow-up as if you're replying in the same email thread (subject should start with "Re: ").
The body should feel like a natural continuation — brief, personal, with a clear reason to reply."""

    client = anthropic.Anthropic()
    response = client.messages.parse(
        model="claude-opus-4-6",
        max_tokens=512,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
        output_format=FollowUpEmail,
    )

    result = response.parsed_output
    return {"subject": result.subject, "body": result.body}
