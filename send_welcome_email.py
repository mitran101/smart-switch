import smtplib
import os
import sys
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def send_welcome_email(to_email):
    smtp_server = "smtp.office365.com"
    smtp_port = 587
    sender_email = os.getenv('MICROSOFT_EMAIL')
    password = os.getenv('MICROSOFT_PASSWORD')

    msg = MIMEMultipart('alternative')
    msg['From'] = f"SwitchPilot Team <team@switch-pilot.com>"
    msg['To'] = to_email
    msg['Subject'] = "You're in - SwitchPilot"

    html = """
    <html>
      <head>
        <meta name="color-scheme" content="light">
        <meta name="supported-color-schemes" content="light">
      </head>
      <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 600px; margin: 0 auto; color: #1a1a2e;">
        <div style="background: linear-gradient(135deg, #6366f1, #ec4899); padding: 30px 24px; border-radius: 10px 10px 0 0; text-align: center;">
          <img src="https://mitran101.github.io/smart-switch/logo.png" alt="SwitchPilot" width="110" style="display: block; width: 110px; height: auto; margin: 0 auto 10px;">
          <span style="font-size: 22px; font-weight: 700; color: #ffffff !important; -webkit-text-fill-color: #ffffff; letter-spacing: -0.3px;">Welcome to SwitchPilot</span>
        </div>

        <div style="padding: 35px 25px; background: #ffffff; border-radius: 0 0 10px 10px;">
          <p style="font-size: 1.05rem; color: #1a1a2e; margin-bottom: 1.5rem;">Hey there! 👋</p>

          <p style="color: #4a5568; line-height: 1.6; margin-bottom: 1rem;">
            Welcome to SwitchPilot. We've got your details and we're already looking at what deals are available in your area.
          </p>

          <p style="color: #4a5568; line-height: 1.6; margin-bottom: 1.5rem;">
            We'll be in touch with a personalised savings estimate for your area - and when we're ready to switch, we'll ask for a bit more info to get you set up properly. For now, you don't need to do anything.
          </p>

          <p style="color: #4a5568; line-height: 1.6; margin-bottom: 1.5rem;">
            We're energy industry professionals building a <strong>free auto-switching service</strong> that makes suppliers compete for your business - so you always end up on the best deal available, with exclusive tariffs you won't find anywhere else and <strong>10% cashback</strong> from the fee suppliers pay us. And because an informed consumer is a powerful one, we publish free plain-English breakdowns of what's really going on in UK energy too.
          </p>

          <p style="color: #4a5568; line-height: 1.6; margin-bottom: 2rem;">
            In the meantime, since you've shared your postcode - see exactly where your energy money goes with our Bill Breakdown Tool. It's free and takes about a minute.
          </p>

          <div style="text-align: center; margin: 30px 0;">
            <a href="https://switch-pilot.com#bill-breakdown" style="background: linear-gradient(135deg, #6366f1, #ec4899); color: white; padding: 14px 28px; text-decoration: none; border-radius: 8px; font-weight: bold; display: inline-block;">
              See Where Your Money Goes
            </a>
          </div>

          <p style="color: #4a5568; line-height: 1.6; margin-bottom: 1.5rem;">
            Got a question or something that frustrates you about your energy bill? Just reply to this email - we read everything.
          </p>

          <p style="color: #6366f1; font-size: 1.1rem; margin-top: 30px; font-weight: 600;">
            The SwitchPilot Team
          </p>

          <div style="text-align: center; margin-top: 30px; padding-top: 20px; border-top: 1px solid #e0e4ea;">
            <a href="https://switch-pilot.com" style="color: #6366f1; text-decoration: none; font-size: 0.9rem; font-weight: 600;">
              Visit SwitchPilot
            </a>
          </div>
        </div>
      </body>
    </html>
    """

    msg.attach(MIMEText(html, 'html'))

    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(sender_email, password)
            server.send_message(msg)
        print(f"Sent welcome email to {to_email}")
        return True
    except Exception as e:
        print(f"Failed to send email: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) > 1:
        send_welcome_email(sys.argv[1])
    else:
        print("Usage: python send_welcome_email.py email@example.com")
