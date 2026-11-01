"""Outbound email via SMTP (stdlib smtplib). Disabled when SMTP_HOST is not configured."""

import logging
import smtplib
from email.message import EmailMessage

from .config import get_settings

logger = logging.getLogger("clinicflow")


def send_email(to: str, subject: str, body: str) -> bool:
    """Returns True if the email was handed to the SMTP server, False otherwise."""
    s = get_settings()
    if not s.smtp_host:
        logger.info("SMTP not configured - skipping email to %s", to)
        return False
    msg = EmailMessage()
    msg["From"] = s.smtp_from or s.smtp_user or "no-reply@clinicflow.local"
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15) as server:
            if s.smtp_tls:
                server.starttls()
            if s.smtp_user:
                server.login(s.smtp_user, s.smtp_password)
            server.send_message(msg)
        logger.info("Email sent to %s (%s)", to, subject)
        return True
    except Exception:
        logger.exception("Failed to send email to %s", to)
        return False
