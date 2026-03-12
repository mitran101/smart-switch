import smtplib
import os
import sys
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests
from bs4 import BeautifulSoup

WEBAPP_URL = "https://script.google.com/macros/s/AKfycbysh_5S6Lloh7UsQ4zhyTJEs0Ja13XfJUwFj9rUEUPlQZoGIyFtpJvz3jPZmcjVwdlf_g/exec"

def fetch_recent_articles():
    """Fetch recent articles from the SwitchInsights hub page"""
    try:
        response = requests.get('https://www.switch-pilot.com/switchinsights/', timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')
        articles = []

        # Featured article
        featured = soup.find('div', class_='featured-card')
        if featured:
            a = featured.find('a', class_='featured-cta')
            h2 = featured.find('h2')
            desc = featured.find('p', class_='desc')
            if a and h2:
                href = a.get('href', '')
                full_url = f"https://www.switch-pilot.com/switchinsights/{href}" if not href.startswith('http') else href
                articles.append({
                    'title': h2.get_text(strip=True),
                    'url': full_url,
                    'description': desc.get_text(strip=True) if desc else ''
                })

        # Article grid cards
        for card in soup.find_all('a', class_='article-card'):
            if len(articles) >= 3:
                break
            h3 = card.find('h3')
            desc = card.find('p', class_='card-desc')
            href = card.get('href', '')
            if h3 and href:
                full_url = f"https://www.switch-pilot.com/switchinsights/{href}" if not href.startswith('http') else href
                articles.append({
                    'title': h3.get_text(strip=True),
                    'url': full_url,
                    'description': desc.get_text(strip=True) if desc else ''
                })

        return articles[:3] if articles else get_fallback_articles()

    except Exception as e:
        print(f"Warning: Could not fetch articles from SwitchInsights: {e}")
        return get_fallback_articles()

def get_fallback_articles():
    return [
        {
            'title': '📉 April Bills Are Dropping to £1,641',
            'url': 'https://www.switch-pilot.com/switchinsights/q2-2026-price-cap.html',
            'description': "The saving is half what the Government is claiming. Here's what it actually means."
        },
        {
            'title': '📈 UK Gas Prices Have Nearly Doubled This Week',
            'url': 'https://www.switch-pilot.com/switchinsights/gas-price-shock-middle-east-2026.html',
            'description': "We break down what's driving the surge and what it means for your bill."
        },
        {
            'title': '⚡ Why UK Electricity Bills Follow Gas Prices',
            'url': 'https://www.switch-pilot.com/switchinsights/why-uk-electricity-bills-follow-gas-prices.html',
            'description': "You're paying gas prices even when half our power comes from wind and solar."
        }
    ]

def send_newsletter_welcome_email(to_email):
    smtp_server = "smtp.office365.com"
    smtp_port = 587
    sender_email = os.getenv('MICROSOFT_EMAIL')
    password = os.getenv('MICROSOFT_PASSWORD')

    articles = fetch_recent_articles()

    token = base64.b64encode(to_email.encode()).decode()
    unsubscribe_url = f"{WEBAPP_URL}?unsubscribe={token}"

    articles_html = ""
    for article in articles:
        articles_html += f"""
            <tr>
              <td style="padding:10px 0;border-bottom:1px solid #f0f0f0;">
                <a href="{article['url']}" style="color:#A855F7;text-decoration:none;font-weight:600;font-size:0.95rem;">{article['title']}</a>
                <p style="color:#666;font-size:0.87rem;margin:4px 0 0;line-height:1.5;">{article['description']}</p>
              </td>
            </tr>
        """

    msg = MIMEMultipart('alternative')
    msg['From'] = "SwitchInsights <team@switch-pilot.com>"
    msg['To'] = to_email
    msg['Subject'] = "Welcome to SwitchInsights - your first read is waiting"

    html = f"""
    <html>
      <head>
        <meta name="color-scheme" content="light">
        <meta name="supported-color-schemes" content="light">
      </head>
      <body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:600px;margin:0 auto;color:#1a1a2e;background:#f4f4f7;padding:32px 16px;">
        <div style="background:#ffffff;border-radius:12px;overflow:hidden;">

          <!-- Header -->
          <div style="background:linear-gradient(135deg,#A855F7,#EC4899);padding:28px 40px;text-align:center;">
            <img src="https://mitran101.github.io/smart-switch/switchinsightslogo.png" alt="SwitchInsights" width="130" style="display:block;width:130px;height:auto;margin:0 auto 10px;">
            <span style="font-size:0.8rem;font-weight:600;color:rgba(255,255,255,0.85);letter-spacing:0.07em;text-transform:uppercase;">Weekly Energy Insights</span>
          </div>

          <!-- Body -->
          <div style="padding:36px 40px;">
            <p style="font-size:1.05rem;color:#1a1a2e;margin:0 0 16px;">Hey 👋</p>

            <p style="color:#4a5568;line-height:1.7;margin:0 0 16px;">
              You're now subscribed to SwitchInsights - plain-English breakdowns of what's really happening in UK energy, written by people who work inside the industry.
            </p>

            <p style="color:#4a5568;line-height:1.7;margin:0 0 24px;">
              No jargon. No spin. No sponsored content. Just the kind of explainers we wish existed when we were first trying to understand our own bills.
            </p>

            <hr style="border:none;border-top:1px solid #f0f0f0;margin:0 0 24px;">

            <p style="color:#888;font-size:0.72rem;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;margin:0 0 14px;">Start reading</p>

            <table cellpadding="0" cellspacing="0" width="100%" style="margin-bottom:28px;">
              {articles_html}
            </table>

            <div style="text-align:center;margin:28px 0;">
              <a href="https://www.switch-pilot.com/switchinsights/" style="background:linear-gradient(135deg,#A855F7,#EC4899);color:#fff;text-decoration:none;font-weight:700;font-size:0.95rem;padding:14px 32px;border-radius:30px;display:inline-block;">See all articles &rarr;</a>
            </div>

            <hr style="border:none;border-top:1px solid #f0f0f0;margin:0 0 24px;">

            <!-- Soft SwitchPilot mention -->
            <div style="background:#f8f4ff;border-radius:10px;padding:16px 20px;margin-bottom:28px;">
              <p style="color:#7c3aed;font-size:0.72rem;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;margin:0 0 6px;">From the same team</p>
              <p style="color:#4a5568;font-size:0.88rem;line-height:1.6;margin:0;">
                We're also building <a href="https://www.switch-pilot.com?utm_source=newsletter_welcome&utm_medium=email&utm_campaign=welcome" style="color:#A855F7;font-weight:600;text-decoration:none;">SwitchPilot</a> - a free service that automatically switches you to the cheapest energy deal, so you never have to think about it. <a href="https://www.switch-pilot.com?utm_source=newsletter_welcome&utm_medium=email&utm_campaign=welcome" style="color:#A855F7;font-weight:600;text-decoration:none;">Take a look &rarr;</a>
              </p>
            </div>

            <div style="background:#f0f4ff;padding:18px 20px;border-radius:8px;border-left:4px solid #A855F7;margin-bottom:28px;">
              <p style="color:#1a1a2e;font-weight:600;margin:0 0 6px;font-size:0.95rem;">Got a question or topic suggestion?</p>
              <p style="color:#4a5568;font-size:0.88rem;line-height:1.6;margin:0;">Just reply to this email. We read everything.</p>
            </div>

            <p style="color:#A855F7;font-size:1rem;font-weight:600;margin:0;">The SwitchInsights team</p>
          </div>

          <!-- Footer -->
          <div style="padding:20px 40px;border-top:1px solid #f0f0f0;text-align:center;">
            <p style="color:#bbb;font-size:0.75rem;line-height:1.8;margin:0;">
              SwitchInsights is published by SwitchPilot Ltd &bull; <a href="mailto:team@switch-pilot.com" style="color:#bbb;text-decoration:none;">team@switch-pilot.com</a><br>
              <a href="{unsubscribe_url}" style="color:#bbb;">Unsubscribe</a> &nbsp;&bull;&nbsp; <a href="https://www.switch-pilot.com/privacy-policy.html" style="color:#bbb;text-decoration:none;">Privacy Policy</a>
            </p>
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
        print(f"Sent newsletter welcome email to {to_email}")
        return True
    except Exception as e:
        print(f"Failed to send email: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) > 1:
        send_newsletter_welcome_email(sys.argv[1])
    else:
        print("Usage: python send_newsletter_welcome_email.py email@example.com")
