import smtplib
import os
import sys
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from urllib.parse import quote
import base64
import requests

def fetch_newsletter_html():
    """Fetch the newsletter HTML from Vercel"""
    url = "https://www.switch-pilot.com/switchpilot-newsletter-watts-in-my-bill.html"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"ERROR: Could not fetch newsletter HTML: {e}")
        return None

def personalize_html(html_content, to_email):
    """Replace generic unsubscribe placeholder with personalized one"""
    token = base64.b64encode(to_email.encode('utf-8')).decode('utf-8')
    personal_unsub = f"https://www.switch-pilot.com/unsubscribe.html?token={quote(token)}"
    return html_content.replace("{{unsubscribe_url}}", personal_unsub)

def send_newsletter(to_email, html_content):
    smtp_server = "smtp.office365.com"
    smtp_port = 587
    sender_email = os.getenv('MICROSOFT_EMAIL')
    password = os.getenv('MICROSOFT_PASSWORD')

    # Personalize unsubscribe link for this recipient
    html = personalize_html(html_content, to_email)

    msg = MIMEMultipart('alternative')
    msg['From'] = f"SwitchPilot Team <team@switch-pilot.com>"
    msg['To'] = to_email
    msg['Subject'] = "Your AI Energy Bill Analyser"

    msg.attach(MIMEText(html, 'html'))

    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(sender_email, password)
            server.send_message(msg)
        print(f"Sent to {to_email}")
        return True
    except Exception as e:
        print(f"FAILED {to_email}: {e}")
        return False

# Log is keyed by newsletter URL so each newsletter has its own sent list
NEWSLETTER_URL = "https://www.switch-pilot.com/switchpilot-newsletter-watts-in-my-bill.html"
SENT_LOG = "newsletter_sent_watts-in-my-bill.txt"

def already_sent(email):
    if not os.path.exists(SENT_LOG):
        return False
    with open(SENT_LOG, 'r') as f:
        return email.lower().strip() in [line.lower().strip() for line in f.readlines()]

def mark_sent(email):
    with open(SENT_LOG, 'a') as f:
        f.write(email.lower().strip() + "\n")

def send_to_list(emails, html_content):
    sent = 0
    skipped = 0
    failed = 0
    for email in emails:
        email = email.strip()
        if not email or '@' not in email:
            continue
        if already_sent(email):
            print(f"Skipping {email} - already sent")
            skipped += 1
            continue
        if send_newsletter(email, html_content):
            mark_sent(email)
            sent += 1
        else:
            failed += 1
    print(f"\nDONE - Sent: {sent} | Skipped: {skipped} | Failed: {failed} | Total: {sent + skipped + failed}")

if __name__ == "__main__":
    html = fetch_newsletter_html()
    if not html:
        sys.exit(1)

    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        send_newsletter("mmitran30@gmail.com", html)
    elif len(sys.argv) > 1 and sys.argv[1] == "--file":
        with open(sys.argv[2], 'r') as f:
            emails = f.readlines()
        send_to_list(emails, html)
    elif len(sys.argv) > 1:
        send_newsletter(sys.argv[1], html)
    else:
        print("Usage:")
        print("  python send_newsletter.py --test              # Send test to yourself")
        print("  python send_newsletter.py email@example.com   # Send to one person")
        print("  python send_newsletter.py --file emails.txt   # Send to list from file")
