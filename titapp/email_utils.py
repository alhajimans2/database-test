import smtplib
from email.message import EmailMessage

from flask import current_app


def send_email_message(recipient: str, subject: str, body: str) -> tuple[bool, str]:
    if not recipient:
        return False, 'Missing email recipient.'

    if not current_app.config.get('MAIL_ENABLED', False):
        current_app.logger.info('MAIL_ENABLED is false. Email not sent to %s', recipient)
        return False, 'Email service is disabled.'

    message = EmailMessage()
    message['Subject'] = subject
    message['From'] = current_app.config.get('MAIL_FROM', 'no-reply@tit.local')
    message['To'] = recipient
    message.set_content(body)

    server = current_app.config.get('MAIL_SERVER', '').strip()
    port = int(current_app.config.get('MAIL_PORT', 587))
    username = current_app.config.get('MAIL_USERNAME', '').strip()
    password = current_app.config.get('MAIL_PASSWORD', '')
    use_tls = bool(current_app.config.get('MAIL_USE_TLS', True))
    use_ssl = bool(current_app.config.get('MAIL_USE_SSL', False))

    if not server:
        return False, 'MAIL_SERVER is not configured.'

    try:
        smtp = smtplib.SMTP_SSL(server, port, timeout=15) if use_ssl else smtplib.SMTP(server, port, timeout=15)
        with smtp:
            if use_tls and not use_ssl:
                smtp.starttls()
            if username:
                smtp.login(username, password)
            smtp.send_message(message)
        return True, 'Email sent.'
    except Exception as error:
        current_app.logger.warning('Email send failed: %s', error)
        return False, f'Email send failed: {error}'
