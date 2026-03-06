import smtplib
import os
import sys
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests

def fetch_newsletter_html():
    """Fetch the newsletter HTML from GitHub Pages"""
    url = "https://mitran101.github.io/smart-switch/switchpilot-newsletter-iran-crisis.html"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"ERROR: Could not fetch newsletter HTML: {e}")
        return None

def send_newsletter(to_email, html_content):
    smtp_server = "smtp.office365.com"
    smtp_port = 587
    sender_email = os.getenv('MICROSOFT_EMAIL')
    password = os.getenv('MICROSOFT_PASSWORD')

    msg = MIMEMultipart('alternative')
    msg['From'] = f"SwitchPilot Team <team@switch-pilot.com>"
    msg['To'] = to_email
    msg['Subject'] = "Gas prices just doubled. Here's what you need to know."

    msg.attach(MIMEText(html_content, 'html'))

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

def send_to_list(emails, html_content):
    sent = 0
    failed = 0
    for email in emails:
        email = email.strip()
        if not email or '@' not in email:
            continue
        if send_newsletter(email, html_content):
            sent += 1
        else:
            failed += 1
    print(f"\nDONE - Sent: {sent} | Failed: {failed} | Total: {sent + failed}")

if __name__ == "__main__":
    html = fetch_newsletter_html()
    if not html:
        sys.exit(1)

    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        # Test mode - send to yourself
        send_newsletter("mitran30@gmail.com", html)
    elif len(sys.argv) > 1 and sys.argv[1] == "--file":
        # Read emails from a file (one per line)
        with open(sys.argv[2], 'r') as f:
            emails = f.readlines()
        send_to_list(emails, html)
    elif len(sys.argv) > 1:
        # Send to a single email
        send_newsletter(sys.argv[1], html)
    else:
        print("Usage:")
        print("  python send_newsletter.py --test              # Send test to yourself")
        print("  python send_newsletter.py email@example.com   # Send to one person")
        print("  python send_newsletter.py --file emails.txt   # Send to list from file")
