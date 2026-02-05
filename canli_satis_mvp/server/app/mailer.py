import os, smtplib
from email.message import EmailMessage

def send_mail(subject: str, body: str, attachments: list[str]):
    host = os.getenv("SMTP_HOST")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER")
    pw = os.getenv("SMTP_PASS")
    to_list = [x.strip() for x in os.getenv("MAIL_TO", "").split(",") if x.strip()]
    if not (host and user and pw and to_list):
        return False, "SMTP not configured"

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = ", ".join(to_list)
    msg.set_content(body)

    for p in attachments:
        with open(p, "rb") as f:
            data = f.read()
        msg.add_attachment(data, maintype="application", subtype="pdf", filename=p.split("/")[-1])

    with smtplib.SMTP(host, port) as s:
        s.starttls()
        s.login(user, pw)
        s.send_message(msg)

    return True, "sent"
