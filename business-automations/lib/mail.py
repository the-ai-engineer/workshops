"""Send an email over SMTP. With Gmail, SMTP_PASSWORD is an app password."""
import os
import smtplib
from email.message import EmailMessage


def send(to: str, subject: str, body: str) -> None:
    message = EmailMessage()
    message["From"] = os.environ["SMTP_USER"]
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)

    with smtplib.SMTP_SSL(os.environ.get("SMTP_HOST", "smtp.gmail.com"), 465) as smtp:
        smtp.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
        smtp.send_message(message)
