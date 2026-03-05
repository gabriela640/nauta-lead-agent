import hashlib
import hmac
import json
import os
import threading
from contextlib import asynccontextmanager
from datetime import datetime

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

import database
import scheduler
from gmail import send_email
from models import Company, Lead, QualificationResult
from qualifier import qualify_lead

load_dotenv()

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "")

CLASSIFICATION_EMOJI = {
    "High ICP": "🔥",
    "Potential ICP": "✅",
    "Not ICP": "❌",
}


# ─── Lifespan ───────────────────────────────────────────────────────────────────

def _write_credential_files():
    """On Railway, write credentials from env vars to files."""
    import base64
    token = os.getenv("GMAIL_TOKEN_JSON")
    creds = os.getenv("GMAIL_CREDENTIALS_JSON")
    if token:
        with open("token.json", "w") as f:
            f.write(base64.b64decode(token).decode())
        print("[Startup] token.json written from env var.")
    if creds:
        with open("credentials.json", "w") as f:
            f.write(base64.b64decode(creds).decode())
        print("[Startup] credentials.json written from env var.")

@asynccontextmanager
async def lifespan(app: FastAPI):
    _write_credential_files()
    database.init_db()
    scheduler.start()
    yield
    scheduler.stop()


app = FastAPI(title="NAUTA Lead Qualification Agent", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Webhook signature verification ────────────────────────────────────────────

def verify_signature(payload: bytes, signature: str) -> bool:
    """Verify RB2B webhook HMAC-SHA256 signature."""
    if not WEBHOOK_SECRET:
        return True  # Skip if no secret configured (dev mode)
    expected = hmac.new(
        WEBHOOK_SECRET.encode(), payload, digestmod=hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)


# ─── RB2B payload parser ────────────────────────────────────────────────────────

def parse_rb2b_payload(data: dict) -> Lead:
    """
    Parse an RB2B webhook payload into a Lead object.
    RB2B nests person data under 'person' key, with company nested inside.
    """
    person = data.get("person", data)
    company_data = person.get("company", {})

    # RB2B uses various field names depending on plan/version — handle both
    employee_count = company_data.get("employee_count") or company_data.get("employees")
    if isinstance(employee_count, str):
        # Strip non-numeric chars e.g. "5,000" → 5000
        employee_count = int("".join(filter(str.isdigit, employee_count)) or 0) or None

    return Lead(
        first_name=person.get("first_name", ""),
        last_name=person.get("last_name", ""),
        email=person.get("email"),
        job_title=person.get("job_title") or person.get("title"),
        linkedin_url=person.get("linkedin_url") or person.get("linkedin"),
        page_visited=data.get("page_visited") or data.get("page_url"),
        company=Company(
            name=company_data.get("name") or person.get("company_name", "Unknown"),
            website=company_data.get("website") or company_data.get("domain"),
            industry=company_data.get("industry"),
            employee_count=employee_count,
            revenue=company_data.get("revenue") or company_data.get("annual_revenue"),
            location=(
                company_data.get("location")
                or company_data.get("city")
                or company_data.get("hq_location")
            ),
        ),
    )


# ─── Logging ────────────────────────────────────────────────────────────────────

def log_result(lead: Lead, result: QualificationResult):
    emoji = CLASSIFICATION_EMOJI.get(result.classification, "")
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n{'─' * 60}")
    print(f"[{ts}] New Lead Processed")
    print(f"  {lead.first_name} {lead.last_name} — {lead.job_title} @ {lead.company.name}")
    print(f"  {emoji} {result.classification}  |  Intent: {result.intent_level}")
    print("  Reasons:")
    for r in result.reasons:
        print(f"    • {r}")
    if result.classification != "Not ICP":
        print(f"\n  Subject: {result.email_subject}")
        print(f"  Body:\n{result.email_body}")
    print(f"{'─' * 60}\n")


# ─── Webhook ─────────────────────────────────────────────────────────────────────

@app.post("/webhook")
async def receive_lead(request: Request):
    payload = await request.body()

    # Verify webhook signature
    signature = request.headers.get("X-RB2B-Signature", "")
    if WEBHOOK_SECRET and not verify_signature(payload, signature):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    # Parse JSON body
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    # Map RB2B payload → Lead model
    try:
        lead = parse_rb2b_payload(data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse lead: {e}")

    # Dedup check — return early if lead already exists
    existing_id = database.find_duplicate(lead.email, lead.linkedin_url)
    if existing_id:
        return JSONResponse({"status": "duplicate", "existing_lead_id": existing_id})

    # Return 200 immediately — process in background so RB2B doesn't time out
    def process_lead(lead: Lead, data: dict):
        try:
            result = qualify_lead(lead)
        except Exception as e:
            print(f"[Webhook] Qualification failed for {lead.email}: {e}")
            return

        log_result(lead, result)
        lead_id = database.save_lead(lead, result, data)
        now_str = datetime.utcnow().isoformat()

        if result.classification == "High ICP" and lead.email and SENDER_EMAIL:
            email_sent = send_email(
                to=lead.email,
                subject=result.email_subject,
                body=result.email_body,
                sender=SENDER_EMAIL,
            )
            database.log_email(
                lead_id=lead_id,
                email_type="initial",
                recipient=lead.email,
                subject=result.email_subject,
                body=result.email_body,
                success=email_sent,
            )
            if email_sent:
                database.update_status(lead_id, "emailed", email_sent_at=now_str)
        elif result.classification == "Potential ICP":
            database.update_status(lead_id, "pending_review")
        else:
            database.update_status(lead_id, "not_icp")

    threading.Thread(target=process_lead, args=(lead, data), daemon=True).start()

    return JSONResponse({"status": "received"})


# ─── Lead management endpoints ───────────────────────────────────────────────────

@app.get("/leads")
async def list_leads(
    status: str = Query(None),
    classification: str = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    leads = database.get_leads(
        status=status, classification=classification, limit=limit, offset=offset
    )
    return {"leads": leads, "count": len(leads)}


@app.get("/leads/{lead_id}")
async def get_lead(lead_id: int):
    lead = database.get_lead(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead


@app.post("/leads/{lead_id}/approve")
async def approve_lead(lead_id: int):
    lead = database.get_lead(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    if lead["status"] != "pending_review":
        raise HTTPException(
            status_code=400,
            detail=f"Lead status is '{lead['status']}', expected 'pending_review'",
        )
    if not lead.get("email"):
        raise HTTPException(status_code=400, detail="Lead has no email address")
    if not SENDER_EMAIL:
        raise HTTPException(status_code=500, detail="SENDER_EMAIL not configured")

    success = send_email(
        to=lead["email"],
        subject=lead["initial_email_subject"],
        body=lead["initial_email_body"],
        sender=SENDER_EMAIL,
    )
    now_str = datetime.utcnow().isoformat()
    database.log_email(
        lead_id=lead_id,
        email_type="initial",
        recipient=lead["email"],
        subject=lead["initial_email_subject"],
        body=lead["initial_email_body"],
        success=success,
    )
    if success:
        database.update_status(lead_id, "emailed", email_sent_at=now_str)

    return {"status": "emailed" if success else "send_failed", "lead_id": lead_id}


@app.post("/leads/{lead_id}/reject")
async def reject_lead(lead_id: int):
    lead = database.get_lead(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    database.update_status(lead_id, "rejected")
    return {"status": "rejected", "lead_id": lead_id}


@app.post("/leads/{lead_id}/mark_replied")
async def mark_replied(lead_id: int):
    lead = database.get_lead(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    now_str = datetime.utcnow().isoformat()
    database.update_status(lead_id, "replied", replied_at=now_str)
    return {"status": "replied", "lead_id": lead_id}


@app.get("/leads/{lead_id}/emails")
async def get_lead_emails(lead_id: int):
    lead = database.get_lead(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    emails = database.get_lead_emails(lead_id)
    return {"lead_id": lead_id, "emails": emails, "count": len(emails)}


# ─── Queue shortcut ──────────────────────────────────────────────────────────────

@app.get("/queue")
async def review_queue(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    leads = database.get_leads(status="pending_review", limit=limit, offset=offset)
    return {"leads": leads, "count": len(leads)}


# ─── Dashboard ───────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    with open("dashboard.html") as f:
        return f.read()


# ─── Health ──────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    stats = database.get_db_stats()
    return {
        "status": "ok",
        "service": "NAUTA Lead Qualification Agent",
        "scheduler_running": scheduler.is_running(),
        "db": stats,
    }


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
