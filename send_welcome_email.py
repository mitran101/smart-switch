import smtplib
import os
import sys
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests
from bs4 import BeautifulSoup

UTM = "utm_source=switchpilot&utm_medium=email&utm_campaign=welcome"

def fetch_recent_articles():
    try:
        response = requests.get('https://www.switch-pilot.com/', timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        insights_section = soup.find('section', id='insights')
        if not insights_section:
            return get_fallback_articles()
        topics = insights_section.find_all('div', class_='topic')
        articles = []
        for topic in topics[:3]:
            onclick = topic.get('onclick', '')
            if 'window.open' in onclick:
                slug = onclick.split("'")[1]
                # slug is e.g. /switchinsights/foo.html
                full_url = f"https://www.switch-pilot.com{slug}?{UTM}"
            else:
                continue
            h3 = topic.find('h3')
            title = h3.get_text(strip=True) if h3 else ''
            if not title:
                continue
            description = ''
            for p in topic.find_all('p'):
                text = p.get_text(strip=True)
                if not text.startswith('📅'):
                    description = text
                    break
            articles.append({'title': title, 'url': full_url, 'description': description})
        return articles if len(articles) == 3 else get_fallback_articles()
    except Exception as e:
        print(f"Warning: could not fetch articles: {e}")
        return get_fallback_articles()

def get_fallback_articles():
    return [
        {
            'title': '📊 Do Energy Suppliers Really Make a Fortune from You?',
            'url': f'https://www.switch-pilot.com/switchinsights/supplier-profits-analysis.html?{UTM}',
            'description': 'Only £44 of your £1,641 annual bill goes to supplier profit. Ofgem data reveals where the rest actually goes.'
        },
        {
            'title': '📈 UK Gas Prices Have Nearly Doubled This Week. Here\'s What It Means for Your Bills',
            'url': f'https://www.switch-pilot.com/switchinsights/gas-price-shock-middle-east-2026.html?{UTM}',
            'description': 'Middle East conflict has sent UK wholesale gas prices soaring. We explain what it means for the October cap.'
        },
        {
            'title': '📉 April Bills Are Dropping to £1,641 - But the Saving Is Half What the Government Is Claiming',
            'url': f'https://www.switch-pilot.com/switchinsights/q2-2026-price-cap.html?{UTM}',
            'description': 'The £150 figure the government keeps quoting? After rising network charges it\'s closer to £92.'
        },
    ]

def build_articles_html(articles):
    rows = ''
    for article in articles:
        rows += f"""
            <tr>
              <td style="padding: 14px 0; border-bottom: 1px solid #e0e4ea;">
                <a href="{article['url']}" style="color: #1a1a2e; text-decoration: none; font-weight: 600; font-size: 0.95rem; line-height: 1.4; display: block; margin-bottom: 4px;">{article['title']}</a>
                <span style="color: #6b7280; font-size: 0.85rem; line-height: 1.5;">{article['description']}</span>
              </td>
            </tr>
        """
    return rows

def send_welcome_email(to_email):
    smtp_server = "smtp.office365.com"
    smtp_port = 587
    sender_email = os.getenv('MICROSOFT_EMAIL')
    password = os.getenv('MICROSOFT_PASSWORD')

    articles = fetch_recent_articles()
    articles_html = build_articles_html(articles)

    msg = MIMEMultipart('alternative')
    msg['From'] = "SwitchPilot Team <team@switch-pilot.com>"
    msg['To'] = to_email
    msg['Subject'] = "You're in - SwitchPilot"

    html = f"""
    <html>
      <head>
        <meta name="color-scheme" content="light">
        <meta name="supported-color-schemes" content="light">
      </head>
      <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 600px; margin: 0 auto; color: #1a1a2e;">

        <div style="background: linear-gradient(135deg, #6366f1, #ec4899); padding: 30px 24px; border-radius: 10px 10px 0 0; text-align: center;">
          <img src="https://mitran101.github.io/smart-switch/logo.png" alt="SwitchPilot logo" width="110" style="display: block; width: 110px; height: auto; margin: 0 auto 10px;">
          <span style="font-size: 22px; font-weight: 700; color: #ffffff !important; -webkit-text-fill-color: #ffffff; letter-spacing: -0.3px;">Welcome to SwitchPilot</span>
        </div>

        <div style="padding: 35px 25px; background: #ffffff; border-radius: 0 0 10px 10px;">

          <!-- Opening -->
          <p style="font-size: 1.05rem; color: #1a1a2e; margin-bottom: 1.5rem;">Hey there! 👋</p>

          <p style="color: #4a5568; line-height: 1.6; margin-bottom: 1rem;">
            Welcome to SwitchPilot. We've got your details and we're already looking at what deals are available in your area.
          </p>

          <p style="color: #4a5568; line-height: 1.6; margin-bottom: 1rem;">
            We'll be in touch with a personalised savings estimate for your area - and when we're ready to switch, we'll ask for a bit more info to get you set up properly. For now, you don't need to do anything.
          </p>

          <p style="color: #4a5568; line-height: 1.6; margin-bottom: 2rem;">
            We're energy industry professionals building a <strong>free auto-switching service</strong> that makes suppliers compete for your business - so you always end up on the best deal available, with exclusive tariffs you won't find anywhere else and <strong>10% cashback</strong> from the fee suppliers pay us.
          </p>

          <!-- Primary CTA -->
          <div style="background: #f0f4ff; border-radius: 10px; padding: 24px; margin-bottom: 2rem; text-align: center;">
            <p style="color: #1a1a2e; font-size: 1rem; line-height: 1.6; margin: 0 0 1.2rem 0;">
              Curious what you should actually be paying? Our free calculator estimates your energy bill based on your home and usage - takes about a minute.
            </p>
            <a href="https://www.switch-pilot.com/energy-bill-calculator.html?{UTM}" style="background: linear-gradient(135deg, #6366f1, #ec4899); color: white; padding: 13px 26px; text-decoration: none; border-radius: 8px; font-weight: bold; display: inline-block; font-size: 0.95rem;">
              Calculate My Bill
            </a>
          </div>

          <!-- Useful tools -->
          <p style="color: #1a1a2e; font-weight: 700; font-size: 0.9rem; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.8rem;">Useful Tools</p>
          <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom: 2rem;">
            <tr>
              <td style="padding: 10px 0; border-bottom: 1px solid #e0e4ea;">
                <a href="https://www.switch-pilot.com/?{UTM}#bill-breakdown" style="color: #6366f1; text-decoration: none; font-weight: 600; font-size: 0.95rem;">Bill Breakdown</a>
                <span style="color: #6b7280; font-size: 0.9rem;"> - see exactly where every pound of your bill goes</span>
              </td>
            </tr>
            <tr>
              <td style="padding: 10px 0;">
                <a href="https://www.switch-pilot.com/tariff-tracker.html?{UTM}" style="color: #6366f1; text-decoration: none; font-weight: 600; font-size: 0.95rem;">Tariff Tracker</a>
                <span style="color: #6b7280; font-size: 0.9rem;"> - check the cheapest deals in your area right now</span>
              </td>
            </tr>
          </table>

          <!-- SwitchInsights articles -->
          <p style="color: #1a1a2e; font-weight: 700; font-size: 0.9rem; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.8rem;">Latest from SwitchInsights</p>
          <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom: 1rem;">
            {articles_html}
          </table>
          <p style="margin-bottom: 2rem;">
            <a href="https://www.switch-pilot.com/archive.html?{UTM}" style="color: #6366f1; text-decoration: none; font-weight: 600; font-size: 0.9rem;">Read more on SwitchInsights →</a>
          </p>

          <!-- Sign-off -->
          <p style="color: #4a5568; line-height: 1.6; margin-bottom: 1.5rem;">
            Got a question or something that frustrates you about your energy bill? Just reply - we read everything.
          </p>

          <p style="color: #6366f1; font-size: 1.1rem; font-weight: 600; margin-bottom: 0;">
            The SwitchPilot Team
          </p>

          <div style="text-align: center; margin-top: 30px; padding-top: 20px; border-top: 1px solid #e0e4ea;">
            <a href="https://www.switch-pilot.com/?{UTM}" style="color: #6366f1; text-decoration: none; font-size: 0.9rem; font-weight: 600;">
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
