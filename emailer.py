"""
emailer.py
----------
Sends the "You're hired" email through Brevo's HTTPS API.

Why not Gmail SMTP? Render's free web services block outbound SMTP
ports (25/465/587), so smtplib can't connect. Brevo's HTTP API goes over
normal HTTPS (port 443), which is allowed.

Environment variables:
    BREVO_API_KEY       API key from Brevo (SMTP & API -> API Keys)
    MAIL_SENDER_EMAIL   the sender address verified in Brevo
    MAIL_SENDER_NAME    display name (default: Job Match)
    APP_URL             public site URL, e.g. https://jobsystem-f1od.onrender.com

If BREVO_API_KEY / MAIL_SENDER_EMAIL are missing, sending is skipped
(logged only) so approving a listing never breaks because of email.
"""

import json
import os
import threading
import urllib.error
import urllib.request
from html import escape

BREVO_URL = "https://api.brevo.com/v3/smtp/email"


def _send(to_email: str, to_name: str, subject: str, html: str, text: str) -> None:
    api_key = os.environ.get("BREVO_API_KEY")
    sender_email = os.environ.get("MAIL_SENDER_EMAIL")
    if not api_key or not sender_email:
        print("[emailer] BREVO_API_KEY / MAIL_SENDER_EMAIL not set; email skipped.")
        return

    payload = {
        "sender": {"name": os.environ.get("MAIL_SENDER_NAME", "Job Match"), "email": sender_email},
        "to": [{"email": to_email, "name": to_name}],
        "subject": subject,
        "htmlContent": html,
        "textContent": text,
    }
    req = urllib.request.Request(
        BREVO_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"api-key": api_key, "content-type": "application/json", "accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            print(f"[emailer] sent to {to_email} (HTTP {resp.status})")
    except urllib.error.HTTPError as e:
        print(f"[emailer] Brevo error {e.code}: {e.read().decode('utf-8', 'ignore')}")
    except Exception as e:  # network problems etc.
        print(f"[emailer] failed: {e}")


def send_hired_email(to_email: str, username: str, job_title: str, company: str,
                     start_date: str, login_url: str) -> None:
    """Fire-and-forget: runs in a background thread so the admin's click
    returns immediately and an email problem can never block approval."""
    subject = "You're hired! - Job Match"
    text = (
        f"Hi {username},\n\n"
        f"Congratulations! The admin approved your listing \"{job_title}\" at {company}.\n"
        f"Your start date is {start_date}.\n\n"
        f"Log in to Job Match to see the details: {login_url}\n"
    )
    html = f"""
    <div style="font-family:Segoe UI,Arial,sans-serif;max-width:520px;margin:auto">
      <h2 style="color:#7c3aed">You're hired! \U0001F389</h2>
      <p>Hi <strong>{escape(username)}</strong>,</p>
      <p>The admin approved your listing <strong>{escape(job_title)}</strong>
         at <strong>{escape(company)}</strong>.</p>
      <p>Your start date is <strong>{escape(start_date)}</strong>.</p>
      <p><a href="{escape(login_url)}"
            style="display:inline-block;background:#7c3aed;color:#fff;padding:12px 18px;
                   border-radius:8px;text-decoration:none;font-weight:700">Log in to Job Match</a></p>
      <p style="color:#777;font-size:12px">Or open: {escape(login_url)}</p>
    </div>"""
    threading.Thread(target=_send, args=(to_email, username, subject, html, text), daemon=True).start()
