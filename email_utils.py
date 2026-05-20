"""
email_utils.py — IMS Email Service
Sends transactional emails (welcome, notifications) via Gmail SMTP.

Setup:
  1. Enable 2-Step Verification on your Gmail account.
  2. Generate an App Password: https://myaccount.google.com/apppasswords
  3. Set the following environment variables, or edit the fallback defaults below:
       IMS_EMAIL_SENDER  — your Gmail address (e.g. you@gmail.com)
       IMS_EMAIL_PASSWORD — the 16-char App Password (no spaces)

  Alternatively, create a .env file and load it before launching uvicorn.
"""

import smtplib
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# ---------------------------------------------------------------------------
# Configuration — edit these or set the matching env vars
# ---------------------------------------------------------------------------
SMTP_HOST     = "smtp.gmail.com"
SMTP_PORT     = 587

# Manually load from a local .env file if it exists in the workspace
try:
    if os.path.exists(".env"):
        with open(".env", "r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if stripped and not stripped.startswith("#") and "=" in stripped:
                    key, val = stripped.split("=", 1)
                    os.environ[key.strip()] = val.strip().strip('"').strip("'")
except Exception as parse_err:
    print(f"[email_utils] Notice: Could not read local .env file: {parse_err}")

SENDER_EMAIL  = os.environ.get("IMS_EMAIL_SENDER",   "")   # e.g. yourname@gmail.com
SENDER_PASS   = os.environ.get("IMS_EMAIL_PASSWORD", "")   # 16-char App Password
SENDER_NAME   = "IMS – Inventory Management"


# ---------------------------------------------------------------------------
# HTML Email Templates
# ---------------------------------------------------------------------------
def _welcome_html(full_name: str, email: str) -> str:
    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Welcome to IMS</title>
</head>
<body style="margin:0;padding:0;background:#f0f6f3;font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f0f6f3;padding:40px 0;">
    <tr>
      <td align="center">
        <table width="560" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:20px;overflow:hidden;box-shadow:0 8px 40px rgba(26,46,38,0.10);">

          <!-- Header -->
          <tr>
            <td style="background:linear-gradient(135deg,hsl(164,43%,8%) 0%,hsl(164,43%,18%) 100%);padding:40px 48px;text-align:center;">
              <h1 style="margin:0;font-size:2.4rem;font-weight:800;color:#ffffff;letter-spacing:-1px;">📦 IMS</h1>
              <p style="margin:8px 0 0;color:rgba(255,255,255,0.55);font-size:0.9rem;letter-spacing:0.5px;">INVENTORY MANAGEMENT SYSTEM</p>
            </td>
          </tr>

          <!-- Body -->
          <tr>
            <td style="padding:44px 48px 32px;">
              <h2 style="margin:0 0 8px;font-size:1.5rem;font-weight:700;color:hsl(164,43%,16%);">
                Welcome aboard, {full_name}! 🎉
              </h2>
              <p style="margin:0 0 24px;color:#5a7a6e;font-size:0.97rem;line-height:1.7;">
                Your IMS account has been successfully created. You now have access to the full inventory management portal — 
                track orders, browse the product catalog, and manage your stock from one seamless interface.
              </p>

              <!-- Account Summary Card -->
              <table width="100%" cellpadding="0" cellspacing="0" style="background:hsl(160,10%,96%);border-radius:12px;margin-bottom:28px;">
                <tr>
                  <td style="padding:20px 24px;">
                    <p style="margin:0 0 6px;font-size:0.75rem;font-weight:700;text-transform:uppercase;letter-spacing:1px;color:#8aab9e;">Account Details</p>
                    <p style="margin:0;color:hsl(164,30%,18%);font-weight:600;">{full_name}</p>
                    <p style="margin:2px 0 0;color:#5a7a6e;font-size:0.9rem;">{email}</p>
                    <p style="margin:6px 0 0;display:inline-block;background:hsl(140,52%,90%);color:hsl(140,52%,30%);padding:3px 10px;border-radius:20px;font-size:0.75rem;font-weight:700;">✓ Active</p>
                  </td>
                </tr>
              </table>

              <!-- CTA Button -->
              <table cellpadding="0" cellspacing="0" width="100%">
                <tr>
                  <td align="center" style="padding-bottom:28px;">
                    <a href="http://127.0.0.1:8000/login" style="display:inline-block;background:hsl(164,43%,22%);color:#ffffff;text-decoration:none;padding:14px 40px;border-radius:12px;font-weight:700;font-size:0.95rem;letter-spacing:0.3px;">
                      Go to Login →
                    </a>
                  </td>
                </tr>
              </table>

              <hr style="border:none;border-top:1px solid hsl(164,15%,92%);margin-bottom:24px;">

              <p style="margin:0;color:#8aab9e;font-size:0.82rem;line-height:1.6;">
                If you did not create this account, please disregard this message — no action is required.<br>
                For support, contact your system administrator.
              </p>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="background:hsl(160,10%,96%);padding:20px 48px;text-align:center;">
              <p style="margin:0;color:#8aab9e;font-size:0.75rem;">
                © 2025 IMS – Inventory Management System &nbsp;|&nbsp; CSE 370 Portfolio Project
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def send_welcome_email(to_email: str, full_name: str) -> bool:
    """
    Send a welcome email to a newly registered user.
    Returns True on success, False on failure (misconfigured or SMTP error).
    """
    if not SENDER_EMAIL or not SENDER_PASS:
        print(
            "[email_utils] WARNING: IMS_EMAIL_SENDER / IMS_EMAIL_PASSWORD not set. "
            "Skipping welcome email."
        )
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"🎉 Welcome to IMS, {full_name}!"
        msg["From"]    = f"{SENDER_NAME} <{SENDER_EMAIL}>"
        msg["To"]      = to_email

        plain = (
            f"Hi {full_name},\n\n"
            "Your IMS account has been created successfully!\n"
            f"Email: {to_email}\n\n"
            "Log in at: http://127.0.0.1:8000/login\n\n"
            "— The IMS Team"
        )
        msg.attach(MIMEText(plain, "plain"))
        msg.attach(MIMEText(_welcome_html(full_name, to_email), "html"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASS)
            server.sendmail(SENDER_EMAIL, to_email, msg.as_string())

        print(f"[email_utils] Welcome email sent → {to_email}")
        return True

    except smtplib.SMTPAuthenticationError:
        print("[email_utils] ERROR: SMTP authentication failed. Check your App Password.")
    except smtplib.SMTPException as e:
        print(f"[email_utils] SMTP error: {e}")
    except Exception as e:
        print(f"[email_utils] Unexpected error sending email: {e}")

    return False
