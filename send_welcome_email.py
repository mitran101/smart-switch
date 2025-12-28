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
                # Extract filename from onclick="window.open('Q1-Cap.html','_blank')"
                link = onclick.split("'")[1]
                full_url = f"https://switch-pilot.com/{link}"
            else:
                continue
            
            # Extract title
            h3 = topic.find('h3')
            if h3:
                title = h3.get_text(strip=True)
            else:
                continue
            
            # Extract description (first <p> tag)
            p_tags = topic.find_all('p')
            description = ""
            if len(p_tags) > 0:
                # First p is usually the description, skip date paragraph
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
    msg['From'] = f"SwitchPilot Flight Crew <flightcrew@switch-pilot.com>"
    msg['To'] = to_email
    msg['Subject'] = "Welcome to SwitchPilot ✈️⚡"
    
    html = f"""
    <html>
      <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 600px; margin: 0 auto; color: #1a1a2e;">
        <div style="background: linear-gradient(135deg, #6366f1, #ec4899); padding: 35px 20px; text-align: center; border-radius: 10px 10px 0 0;">
          <h1 style="color: white; font-size: 1.8rem; margin: 0;">✈️⚡ Welcome to SwitchPilot</h1>
        </div>
        
        <div style="padding: 35px 25px; background: #ffffff; border-radius: 0 0 10px 10px;">
          <p style="font-size: 1.05rem; color: #1a1a2e; margin-bottom: 1.5rem;">Hey there! 👋</p>
          
          <p style="color: #4a5568; line-height: 1.6; margin-bottom: 1.5rem;">
            Welcome to SwitchPilot. Thanks for joining us.
          </p>
          
          <h2 style="color: #6366f1; font-size: 1.3rem; margin-top: 2rem; margin-bottom: 1rem;">Our Story</h2>
          
          <p style="color: #4a5568; line-height: 1.6; margin-bottom: 1rem;">
            We're two people working in the UK energy industry.
          </p>
          
          <p style="color: #4a5568; line-height: 1.6; margin-bottom: 1rem;">
            When we joined, we didn't understand energy bills. At all.
          </p>
          
          <p style="color: #4a5568; line-height: 1.6; margin-bottom: 1rem;">
            Now? We can't unsee what we've learned.
          </p>
          
          <p style="color: #4a5568; line-height: 1.6; margin-bottom: 1.5rem;">
            Did you know you're paying wind farms to turn off? Or funding a nuclear plant before it's even built? Or that 65% of UK households are overpaying on Standard Variable Tariffs?
          </p>
          
          <p style="color: #4a5568; line-height: 1.6; margin-bottom: 1.5rem;">
            Most people don't know what they're paying for. We didn't either until we got inside the industry.
          </p>
          
          <h2 style="color: #6366f1; font-size: 1.3rem; margin-top: 2rem; margin-bottom: 1rem;">What We're Building</h2>
          
          <p style="color: #4a5568; line-height: 1.6; margin-bottom: 1rem;">
            We're building a <strong>free auto-switching service</strong> that truly empowers the customer. But more than that, we're building a <strong>community that educates and empowers consumers</strong>.
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
            We want to engage with people and educate you. Because here's the thing: an informed consumer makes the market more competitive, forces suppliers to offer better deals, and when more people engage, Ofgem listens and makes changes.
          </p>
          
          <p style="color: #4a5568; line-height: 1.6; margin-bottom: 1rem;">
            We want to find out what frustrates you. Help you understand what you're paying for. And the best part? We're building this WITH you, so you help us shape the product.
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
            Whilst we build a service that works for you, check out our <strong>Tariff Tracker</strong> to find the cheapest energy tariffs on the market. We update this every weekday.
          </p>
          
          <div style="text-align: center; margin: 30px 0;">
            <a href="https://switch-pilot.com/tariff-tracker.html" style="background: linear-gradient(135deg, #6366f1, #ec4899); color: white; padding: 14px 28px; text-decoration: none; border-radius: 8px; font-weight: bold; display: inline-block; margin-bottom: 15px;">
              Check Live Tariff Tracker →
            </a>
          </div>
          
          <div style="background: #f0f4ff; padding: 20px; border-radius: 8px; border-left: 4px solid #6366f1; margin: 25px 0;">
            <p style="color: #1a1a2e; line-height: 1.6; margin: 0; font-weight: 600;">
              What frustrates YOU about energy bills?
            </p>
            <p style="color: #4a5568; line-height: 1.6; margin: 10px 0 0 0;">
              <a href="https://switch-pilot.com/community.html" style="color: #6366f1; text-decoration: none; font-weight: 600;">Join our Community</a> to discuss, learn from others, and share your experiences — or simply reply to this email and we'll get back to you.
            </p>
          </div>
          
          <p style="color: #6366f1; font-size: 1.1rem; margin-top: 30px; font-weight: 600;">
            ⚡✈️ The SwitchPilot Team
          </p>
          
          <p style="color: #9ca3af; font-size: 0.9rem; margin-top: 20px; font-style: italic;">
            P.S. - <a href="https://switch-pilot.com#game" style="color: #6366f1; text-decoration: none;">Play our game</a> while we build your service 🎮
          </p>
          
          <div style="text-align: center; margin-top: 30px; padding-top: 20px; border-top: 1px solid #e0e4ea;">
            <a href="https://switch-pilot.com" style="color: #6366f1; text-decoration: none; font-size: 0.9rem; font-weight: 600;">
              Visit SwitchPilot →
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
