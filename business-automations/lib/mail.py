"""Send an email over SMTP, or save one as a Gmail draft over IMAP.
With Gmail, SMTP_PASSWORD is an app password."""
import imaplib
import os
import smtplib
import time
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


def save_draft(to: list[str], subject: str, body: str) -> None:
    """Put an email in Gmail's Drafts folder for a person to check and send."""
    message = EmailMessage()
    message["From"] = os.environ["SMTP_USER"]
    message["To"] = ", ".join(to)
    message["Subject"] = subject
    message.set_content(body)

    with imaplib.IMAP4_SSL(os.environ.get("IMAP_HOST", "imap.gmail.com")) as imap:
        imap.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
        imap.append("[Gmail]/Drafts", "\\Draft", imaplib.Time2Internaldate(time.time()), message.as_bytes())
