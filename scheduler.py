import os
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler

import database
from follow_up_prompter import generate_followup
from gmail import send_email

SENDER_EMAIL = os.getenv("SENDER_EMAIL", "")

# Days from initial email_sent_at that trigger each follow-up
FOLLOWUP_THRESHOLDS = {
    1: 3,
    2: 7,
    3: 14,
}

# Status that indicates each follow-up is due
FOLLOWUP_STATUS = {
    1: "emailed",
    2: "follow_up_1_sent",
    3: "follow_up_2_sent",
}

# Column to update after sending each follow-up
FOLLOWUP_TIMESTAMP_COL = {
    1: "follow_up_1_sent_at",
    2: "follow_up_2_sent_at",
    3: "follow_up_3_sent_at",
}

FOLLOWUP_NEXT_STATUS = {
    1: "follow_up_1_sent",
    2: "follow_up_2_sent",
    3: "follow_up_3_sent",
}


def _days_since(ts_str: str) -> float:
    """Return fractional days since an ISO timestamp string (UTC assumed)."""
    try:
        ts = datetime.fromisoformat(ts_str).replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - ts
        return delta.total_seconds() / 86400
    except Exception:
        return 0.0


def process_follow_ups():
    """Hourly job: find leads due for follow-up and send emails."""
    now_str = datetime.utcnow().isoformat()
    print(f"[Scheduler] Running follow-up check at {now_str}")

    sent_count = 0

    for followup_num, required_status in FOLLOWUP_STATUS.items():
        threshold_days = FOLLOWUP_THRESHOLDS[followup_num]
        timestamp_col = FOLLOWUP_TIMESTAMP_COL[followup_num]
        next_status = FOLLOWUP_NEXT_STATUS[followup_num]

        leads = database.get_leads(status=required_status, limit=200)

        for lead in leads:
            # Skip leads that have replied
            if lead.get("replied_at"):
                continue

            # Skip leads with no email address
            if not lead.get("email"):
                continue

            # Check if enough days have passed since initial email
            email_sent_at = lead.get("email_sent_at")
            if not email_sent_at:
                continue

            days_elapsed = _days_since(email_sent_at)
            if days_elapsed < threshold_days:
                continue

            lead_id = lead["id"]
            recipient = lead["email"]

            try:
                followup = generate_followup(lead, followup_num)
                subject = followup["subject"]
                body = followup["body"]

                success = send_email(
                    to=recipient,
                    subject=subject,
                    body=body,
                    sender=SENDER_EMAIL,
                )

                database.log_email(
                    lead_id=lead_id,
                    email_type=f"follow_up_{followup_num}",
                    recipient=recipient,
                    subject=subject,
                    body=body,
                    success=success,
                )

                if success:
                    database.update_status(
                        lead_id,
                        next_status,
                        **{timestamp_col: now_str},
                    )
                    sent_count += 1
                    print(
                        f"[Scheduler] Sent follow-up {followup_num} to lead {lead_id} ({recipient})"
                    )
                else:
                    print(
                        f"[Scheduler] Failed to send follow-up {followup_num} to lead {lead_id}"
                    )

            except Exception as e:
                print(
                    f"[Scheduler] Error processing follow-up {followup_num} for lead {lead_id}: {e}"
                )

    print(f"[Scheduler] Done. Sent {sent_count} follow-up(s).")


_scheduler = BackgroundScheduler()


def start():
    _scheduler.add_job(
        process_follow_ups,
        trigger="interval",
        hours=1,
        id="follow_up_job",
        replace_existing=True,
        next_run_time=datetime.now(),  # run once immediately on startup
    )
    _scheduler.start()
    print("[Scheduler] Started — follow-up job runs every hour.")


def stop():
    _scheduler.shutdown(wait=False)
    print("[Scheduler] Stopped.")


def is_running() -> bool:
    return _scheduler.running
