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
    msg['From'] = f"SwitchPilot Team <{sender_email}>"
    msg['To'] = to_email
    msg['Subject'] = "Welcome to the SwitchPilot Flight Crew! ✈️⚡"
    
    user_name = to_email.split('@')[0].title()
    
    html = f"""
    <html>
      <body style="font-family: -apple-system, sans-serif; max-width: 600px; margin: 0 auto;">
        <div style="background: linear-gradient(135deg, #6366f1, #ec4899); padding: 40px; text-align: center; border-radius: 10px 10px 0 0;">
          <h1 style="color: white; font-size: 2rem; margin: 0;">✈️ Welcome Aboard, {user_name}!</h1>
        </div>
        
        <div style="padding: 30px; background: #f9fafb;">
          <p style="font-size: 1.1rem; color: #1a1a2e;">Thanks for joining the pilot program!</p>
          
          <p style="color: #4a5568; line-height: 1.6;">
            You're now part of an exclusive group helping us build the UK's first truly customer-first energy switching service.
          </p>
          
          <div style="background: white; padding: 20px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #6366f1;">
            <h3 style="margin-top: 0; color: #6366f1;">What happens next?</h3>
            <ul style="color: #4a5568; line-height: 1.8;">
              <li>📊 <strong>Weekly insights</strong> straight to your inbox</li>
              <li>🎯 <strong>Early access</strong> when we launch</li>
              <li>💡 <strong>Insider knowledge</strong> from EDF analysts</li>
              <li>🚀 <strong>Shape the product</strong> with your feedback</li>
            </ul>
          </div>
          
          <p style="color: #4a5568;">
            While we're building, check out our <a href="https://switchpilot.co.uk/tariff-tracker.html" style="color: #6366f1; text-decoration: none; font-weight: bold;">Live Tariff Tracker</a> – updated weekdays with real data across all 14 UK regions.
          </p>
          
          <div style="text-align: center; margin: 30px 0;">
            <a href="https://switchpilot.co.uk" style="background: linear-gradient(135deg, #6366f1, #ec4899); color: white; padding: 15px 30px; text-decoration: none; border-radius: 8px; font-weight: bold; display: inline-block;">
              Visit SwitchPilot →
            </a>
          </div>
          
          <p style="color: #9ca3af; font-size: 0.9rem; margin-top: 30px;">
            Questions? Just reply to this email – we read everything.<br>
            <br>
            Built by energy insiders, for you.<br>
            Mitran & Lyall
          </p>
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
        print(f"✅ Welcome email sent to {to_email}")
        return True
    except Exception as e:
        print(f"❌ Failed to send email: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) > 1:
        send_welcome_email(sys.argv[1])
    else:
        print("Usage: python send_welcome_email.py email@example.com")
