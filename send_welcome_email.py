import smtplib
import os
import sys
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests
from bs4 import BeautifulSoup

def fetch_recent_articles():
    """Fetch recent articles from the website's Recent Insights section"""
    try:
        response = requests.get('https://switch-pilot.com/', timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Find the insights section
        insights_section = soup.find('section', class_='insights')
        if not insights_section:
            return get_fallback_articles()
        
        # Find all topic divs
        topics = insights_section.find_all('div', class_='topic')
        
        articles = []
        for topic in topics[:3]:  # Get top 3 articles
            # Extract link from onclick attribute
            onclick = topic.get('onclick', '')
            if 'window.open' in onclick:
                link = onclick.split("'")[1]
                full_url = f"https://switch-pilot.com/{link}"
            else:
                continue
            
            h3 = topic.find('h3')
            if h3:
                title = h3.get_text(strip=True)
            else:
                continue
            
            p_tags = topic.find_all('p')
            description = ""
            if len(p_tags) > 0:
                for p in p_tags:
                    text = p.get_text(strip=True)
                    if not text.startswith('📅'):
                        description = text
                        break
            
            articles.append({
                'title': title,
                'url': full_url,
                'description': description
            })
        
        return articles if articles else get_fallback_articles()
        
    except Exception as e:
        print(f"Warning: Could not fetch articles from website: {e}")
        return get_fallback_articles()

def get_fallback_articles():
    """Fallback articles if website fetch fails"""
    return [
        {
            'title': '🔆 Q1-26 Price Cap Breakdown',
            'url': 'https://switch-pilot.com/Q1-Cap.html',
            'description': "Bills only rose £3, but what's the deeper picture?"
        },
        {
            'title': '⚛️ Nuclear RAB Charge',
            'url': 'https://switch-pilot.com/nuclear-rab.html',
            'description': "You're paying for Sizewell C before it exists"
        },
        {
            'title': '🔆 Warm Home Discount Expansion',
            'url': 'https://switch-pilot.com/article.html',
            'description': '£15-22 added to your bill this winter'
        }
    ]

def send_welcome_email(to_email):
    smtp_server = "smtp.office365.com"
    smtp_port = 587
    sender_email = os.getenv('MICROSOFT_EMAIL')
    password = os.getenv('MICROSOFT_PASSWORD')
    
    # Fetch recent articles
    articles = fetch_recent_articles()
    
    # Build article list HTML
    articles_html = ""
    for article in articles:
        articles_html += f"""
            <li><a href="{article['url']}" style="color: #6366f1; text-decoration: none; font-weight: 600;">{article['title']}</a> - {article['description']}</li>
        """
    
    msg = MIMEMultipart('alternative')
    msg['From'] = f"SwitchPilot Team <team@switch-pilot.com>"
    msg['To'] = to_email
    msg['Subject'] = "You're in - here's how UK energy really works"
    
    html = f"""
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
            We'll be in touch with a personalised savings estimate for your area — and when we're ready to switch, we'll ask for a bit more info to get you set up properly. For now, you don't need to do anything.
          </p>
          
          <h2 style="color: #6366f1; font-size: 1.3rem; margin-top: 2rem; margin-bottom: 1rem;">Our Story</h2>
          
          <p style="color: #4a5568; line-height: 1.6; margin-bottom: 1rem;">
            We're two people working in the UK energy industry.
          </p>
          
          <p style="color: #4a5568; line-height: 1.6; margin-bottom: 1rem;">
            When we joined, we didn't understand much. But now we've learned things that have shocked us.
          </p>
          
          <p style="color: #4a5568; line-height: 1.6; margin-bottom: 1.5rem;">
            Did you know you're paying wind farms to turn off? Or covering other people's bad debts through your bill? Or that 65% of UK households are overpaying on Standard Variable Tariffs?
          </p>
          
          <p style="color: #4a5568; line-height: 1.6; margin-bottom: 1rem;">
            Most people don't know what they're paying for. We didn't either until we got inside the industry.
          </p>
          
          <p style="color: #4a5568; line-height: 1.6; margin-bottom: 1.5rem;">
            It shocked us. And it sparked a mission - to create more transparency and give power back to consumers.
          </p>
          
          <h2 style="color: #6366f1; font-size: 1.3rem; margin-top: 2rem; margin-bottom: 1rem;">What We're Building</h2>
          
          <p style="color: #4a5568; line-height: 1.6; margin-bottom: 1rem;">
            We're building a <strong>free auto-switching service</strong> that puts you on the best deal possible based on your preferences (and consent, of course!). But more than that, we're building a <strong>movement that educates and empowers consumers</strong>.
          </p>
          
          <p style="color: #4a5568; line-height: 1.6; margin-bottom: 1rem;">
            You're part of an <strong>exclusive early access group</strong> who will help us shape SwitchPilot and launch us to our goal: smarter switching for everyone.
          </p>
          
          <p style="color: #4a5568; line-height: 1.6; margin-bottom: 1rem;">
            We surveyed 200 people. Here's what we found:
          </p>
          
          <div style="background: #f0f4ff; padding: 20px; border-radius: 8px; margin: 20px 0;">
            <ul style="color: #4a5568; line-height: 1.8; margin: 0; padding-left: 20px;">
              <li><strong>77.5%</strong> want auto-switching</li>
              <li><strong>73%</strong> of "content" customers still want switching when friction is removed</li>
              <li><strong>61%</strong> don't understand their bills</li>
              <li><strong>48%</strong> haven't switched in 5+ years</li>
            </ul>
          </div>
          
          <p style="color: #4a5568; line-height: 1.6; margin-bottom: 1rem;">
            But surveys are just surveys. We want to build this <strong>WITH you</strong> - not just based on numbers, but through real conversations, shared frustrations, and your input every step of the way.
          </p>
          
          <p style="color: #4a5568; line-height: 1.6; margin-bottom: 1rem;">
            An informed consumer makes the market more competitive and forces suppliers to offer better deals. When more people engage, Ofgem listens and makes changes.
          </p>
          
          <p style="color: #1a1a2e; line-height: 1.6; margin-bottom: 2rem; font-weight: 600;">
            Let's build this together.
          </p>
          
          <h2 style="color: #6366f1; font-size: 1.3rem; margin-top: 2rem; margin-bottom: 1rem;">Start Here</h2>
          
          <p style="color: #4a5568; line-height: 1.6; margin-bottom: 1rem;">
            While we build, catch up on what's happening in UK energy:
          </p>
          
          <ul style="color: #4a5568; line-height: 1.8; margin-bottom: 1.5rem;">
            {articles_html}
          </ul>
          
          <p style="color: #4a5568; line-height: 1.6; margin-bottom: 1rem;">
            Every week, we'll send you plain English breakdowns of what's really going on.
          </p>
          
          <p style="color: #4a5568; line-height: 1.6; margin-bottom: 1.5rem;">
            Want to understand your own bill better? Check out our <a href="https://switch-pilot.com#bill-breakdown" style="color: #6366f1; text-decoration: none; font-weight: 600;">Bill Breakdown Tool</a> that shows you exactly where your money goes.
          </p>
          
          <p style="color: #4a5568; line-height: 1.6; margin-bottom: 1rem;">
            Whilst we build a service that works for you, check out our <strong>Tariff Tracker</strong> to find the cheapest deals. We update this every weekday.
          </p>
          
          <div style="text-align: center; margin: 30px 0;">
            <a href="https://switch-pilot.com/tariff-tracker.html" style="background: linear-gradient(135deg, #6366f1, #ec4899); color: white; padding: 14px 28px; text-decoration: none; border-radius: 8px; font-weight: bold; display: inline-block; margin-bottom: 15px;">
              Check Live Tariff Tracker
            </a>
          </div>
          
          <div style="background: #f0f4ff; padding: 20px; border-radius: 8px; border-left: 4px solid #6366f1; margin: 25px 0;">
            <p style="color: #1a1a2e; line-height: 1.6; margin: 0 0 0.5rem 0; font-weight: 600;">
              Got Questions or Feedback?
            </p>
            <p style="color: #4a5568; line-height: 1.6; margin: 0;">
              Just reply to this email. We read everything and love hearing what frustrates you about energy bills.
            </p>
          </div>
          
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
