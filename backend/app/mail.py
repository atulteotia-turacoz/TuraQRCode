import smtplib
import ssl
from email.message import EmailMessage


def send_email(config: dict, to: str, subject: str, body: str):
    message = EmailMessage()
    message['Subject'] = subject
    message['From'] = config['from_address']
    message['To'] = to
    message.set_content(body)
    context = ssl.create_default_context()
    if config['security'] == 'ssl':
        server = smtplib.SMTP_SSL(config['host'], config['port'], timeout=15, context=context)
    else:
        server = smtplib.SMTP(config['host'], config['port'], timeout=15)
    with server:
        if config['security'] == 'starttls':
            server.starttls(context=context)
        if config['username']:
            server.login(config['username'], config['password'])
        server.send_message(message)
