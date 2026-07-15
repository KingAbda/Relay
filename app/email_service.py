"""Transactional email backend with honest delivery results and no secret logging."""

from __future__ import annotations

from email.message import EmailMessage
import os
import smtplib
import ssl


class EmailDeliveryError(RuntimeError):
    """Raised when a transactional message was not accepted by the backend."""


def send_transactional_email(app, *, to: str, subject: str, body: str) -> None:
    backend = app.config["RELAY_EMAIL_BACKEND"]
    if backend == "memory":
        app.extensions.setdefault("relay_outbox", []).append(
            {"to": to, "subject": subject, "body": body}
        )
        return
    if backend == "disabled":
        raise EmailDeliveryError("Transactional email is not configured")

    host = os.environ.get("RELAY_SMTP_HOST", "").strip()
    username = os.environ.get("RELAY_SMTP_USERNAME", "").strip()
    password = os.environ.get("RELAY_SMTP_PASSWORD", "")
    sender = os.environ.get("RELAY_EMAIL_FROM", "").strip()
    try:
        port = int(os.environ.get("RELAY_SMTP_PORT", "587"))
    except ValueError as exc:
        raise EmailDeliveryError("RELAY_SMTP_PORT is invalid") from exc
    if not host or not sender:
        raise EmailDeliveryError("SMTP host and sender are required")

    message = EmailMessage()
    message["From"] = sender
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)

    try:
        with smtplib.SMTP(host, port, timeout=10) as client:
            client.starttls(context=ssl.create_default_context())
            if username:
                client.login(username, password)
            client.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        raise EmailDeliveryError("The email provider did not accept the message") from exc
