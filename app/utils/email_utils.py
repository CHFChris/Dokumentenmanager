import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.core.config import settings

def send_mail(to_email: str, subject: str, html_body: str, text_body: str | None = None):
    """Sendet eine E-Mail via SMTP. Fällt bei Fehlern auf Konsolen-Log zurück."""
    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = f"{getattr(settings, 'MAIL_FROM_NAME', 'System')} <{settings.MAIL_FROM}>"
        msg["To"] = to_email
        msg["Subject"] = subject

        if text_body:
            msg.attach(MIMEText(text_body, "plain"))
        msg.attach(MIMEText(html_body, "html"))

        # SMTP Verbindung
        server = smtplib.SMTP(settings.MAIL_SERVER, settings.MAIL_PORT)
        if getattr(settings, "MAIL_USE_TLS", True):
            server.starttls()

        server.login(settings.MAIL_USERNAME, settings.MAIL_PASSWORD)
        server.sendmail(settings.MAIL_FROM, [to_email], msg.as_string())
        server.quit()
        print(f"[MAIL] Gesendet an {to_email}: {subject}")
        return True
    except Exception as ex:
        # Fallback: Ausgabe in Konsole
        print(f"[MAIL-ERROR] {ex}\n---\nBetreff: {subject}\nAn: {to_email}\n{text_body or html_body}")
        return False
