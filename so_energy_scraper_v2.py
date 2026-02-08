#!/usr/bin/env python3
"""
So Energy Tariff Scraper v2 - STEALTH EDITION
Based on British Gas scraper architecture.
Scrapes https://www.so.energy/our-tariffs for all 14 DNO regions.

Flow (from recording):
1. Navigate to https://www.so.energy/our-tariffs
2. Enter postcode
3. Click "Find Tariffs"
4. Open "Filters" accordion
5. Uncheck "Variable" checkbox (keep only Fixed tariffs)
6. Click each tariff card to expand details
7. Extract unit rates, standing charges, tariff name, exit fees, Eco 7 rates

Table structure per card:
┌──────────────────┬──────────────┬─────────────────┬───────────┬────────────┐
│                  │ Unit Rate    │ Standing charge │ Day rate  │ Night rate │
├──────────────────┼──────────────┼─────────────────┼───────────┼────────────┤
│ Eco 7 Electricity│              │ 42.03p / day    │ 30.36p    │ 16.06p     │
│ Electricity      │ 25.18p / kWh │ 41.74p / day    │           │            │
│ Gas              │ 5.38p / kWh  │ 34.52p / day    │           │            │
└──────────────────┴──────────────┴─────────────────┴───────────┴────────────┘
Payment type: Direct Debit   Billing: Online   Exit fee: £50 / fuel
"""

import json
import csv
import re
import random
import time
import math
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# ============================================
# CONFIGURATION
# ============================================

DNO_POSTCODES_ALL = {
    "Eastern": "IP4 5ET",
    "East Midlands": "DE23 6JJ",
    "London": "N5 2SD",
    "North Wales & Merseyside": "L3 2BN",
    "West Midlands": "SY2 6HL",
    "North East": "NE2 1UY",
    "North West": "PR4 2NB",
    "South East": "BN2 7HQ",
    "Southern": "BH6 4AS",
    "South Wales": "CF14 2DY",
    "South West": "PL9 7BS",
    "Yorkshire": "YO31 1DT",
    "North Scotland": "AB24 3EN",
    "South Scotland": "G20 6NQ",
}

SO_TARIFFS_URL = "https://www.so.energy/our-tariffs"

# Pool of realistic user agents
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
]

VIEWPORTS = [
    {"width": 1920, "height": 1080},
    {"width": 1536, "height": 864},
    {"width": 1440, "height": 900},
    {"width": 1366, "height": 768},
    {"width": 1680, "height": 1050},
    {"width": 1600, "height": 900},
]

# ============================================
# STEALTH SCRIPTS
# ============================================

STEALTH_SCRIPTS = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

Object.defineProperty(navigator, 'plugins', {
    get: () => {
        const plugins = [
            { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
            { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' },
            { name: 'Native Client', filename: 'internal-nacl-plugin', description: '' }
        ];
        plugins.length = 3;
        return plugins;
    }
});

Object.defineProperty(navigator, 'languages', { get: () => ['en-GB', 'en-US', 'en'] });
Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });

const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) => (
    parameters.name === 'notifications' ?
        Promise.resolve({ state: Notification.permission }) :
        originalQuery(parameters)
);

window.chrome = { runtime: {}, loadTimes: function() {}, csi: function() {}, app: {} };

Object.defineProperty(navigator, 'connection', {
    get: () => ({ effectiveType: '4g', rtt: 50, downlink: 10, saveData: false })
});

const originalGetContext = HTMLCanvasElement.prototype.getContext;
HTMLCanvasElement.prototype.getContext = function(type, attributes) {
    const context = originalGetContext.call(this, type, attributes);
    if (type === '2d') {
        const originalFillText = context.fillText;
        context.fillText = function(...args) {
            args[1] += Math.random() * 0.001;
            return originalFillText.apply(this, args);
        };
    }
    return context;
};

const getParameter = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function(parameter) {
    if (parameter === 37445) return 'Intel Inc.';
    if (parameter === 37446) return 'Intel Iris OpenGL Engine';
    return getParameter.call(this, parameter);
};

console.log('Stealth mode activated');
"""


# ============================================
# HUMAN BEHAVIOR SIMULATION
# ============================================

def human_delay(min_ms=500, max_ms=2000):
    delay = random.betavariate(2, 5) * (max_ms - min_ms) + min_ms
    time.sleep(delay / 1000)

def human_typing_delay():
    if random.random() < 0.1:
        return random.randint(200, 400)
    return random.randint(50, 150)

def simulate_mouse_movement(page, target_x, target_y):
    steps = random.randint(5, 15)
    current_x = random.randint(400, 600)
    current_y = random.randint(300, 400)
    for i in range(steps):
        progress = (i + 1) / steps
        new_x = current_x + (target_x - current_x) * progress + random.gauss(0, 5)
        new_y = current_y + (target_y - current_y) * progress + random.gauss(0, 5)
        page.mouse.move(new_x, new_y)
        time.sleep(random.uniform(0.01, 0.03))

def random_scroll(page):
    scroll_amount = random.randint(100, 300)
    page.mouse.wheel(0, scroll_amount)
    human_delay(300, 800)


# ============================================
# RATE EXTRACTION (v2 - line-by-line parsing)
# ============================================

def extract_tariff_from_text(card_text: str) -> dict:
    """
    Extract rates from an expanded accordion card's inner_text().
    
    The page renders a TABLE, but inner_text() flattens it to lines like:
        Eco 7 Electricity\t\t42.03p / day\t30.36p / kWh\t16.06p / kWh
        Electricity\t25.18p / kWh\t41.74p / day
        Gas\t5.38p / kWh\t34.52p / day
        Payment type\tBilling\tExit fee
        Direct Debit\tOnline\t£50 / fuel
    
    We split by lines and parse each row independently to avoid
    "Eco 7 Electricity" bleeding into the "Electricity" regex.
    """
    data = {}
    
    # --- Tariff name ---
    name_m = re.search(r'(So\s+\w+(?:\s+\w+)*?\s+(?:One|Two|Three)\s+Year)', card_text, re.I)
    if name_m:
        data['tariff_name'] = re.sub(r'\s+', ' ', name_m.group(1).strip())
    
    # --- Duration / type ---
    dm = re.search(r'(\d+)-month\s+(Fixed|Variable)', card_text, re.I)
    if dm:
        data['duration'] = f"{dm.group(1)}-month"
        data['tariff_type'] = dm.group(2).capitalize()
    elif re.search(r'Fixed\s*Rate', card_text, re.I):
        data['tariff_type'] = 'Fixed'
    elif re.search(r'Variable', card_text, re.I):
        data['tariff_type'] = 'Variable'
    
    # --- Split into lines and parse each row ---
    lines = card_text.split('\n')
    
    for line in lines:
        stripped = line.strip()
        lower = stripped.lower()
        
        # ── Eco 7 Electricity row ──
        # Must check BEFORE the plain "Electricity" row
        if ('eco' in lower and '7' in lower) or ('eco' in lower and 'electr' in lower):
            # Standing charge: p / day
            sc_m = re.search(r'(\d+\.?\d*)\s*p\s*/?\s*day', stripped, re.I)
            if sc_m:
                data['eco7_standing_p'] = float(sc_m.group(1))
            
            # Day rate and night rate: find all p/kWh values in order
            kwh_vals = re.findall(r'(\d+\.?\d*)\s*p\s*/?\s*kWh', stripped, re.I)
            if len(kwh_vals) >= 2:
                data['eco7_day_rate_p'] = float(kwh_vals[0])
                data['eco7_night_rate_p'] = float(kwh_vals[1])
            elif len(kwh_vals) == 1:
                data['eco7_day_rate_p'] = float(kwh_vals[0])
        
        # ── Standard Electricity row (NOT Eco 7) ──
        elif lower.startswith('electricity') and 'eco' not in lower:
            kwh_m = re.search(r'(\d+\.?\d*)\s*p\s*/?\s*kWh', stripped, re.I)
            if kwh_m:
                data['elec_unit_rate_p'] = float(kwh_m.group(1))
            day_m = re.search(r'(\d+\.?\d*)\s*p\s*/?\s*day', stripped, re.I)
            if day_m:
                data['elec_standing_p'] = float(day_m.group(1))
        
        # ── Gas row ──
        elif lower.startswith('gas'):
            kwh_m = re.search(r'(\d+\.?\d*)\s*p\s*/?\s*kWh', stripped, re.I)
            if kwh_m:
                data['gas_unit_rate_p'] = float(kwh_m.group(1))
            day_m = re.search(r'(\d+\.?\d*)\s*p\s*/?\s*day', stripped, re.I)
            if day_m:
                data['gas_standing_p'] = float(day_m.group(1))
        
        # ── Exit fee row (appears on a separate line like "Direct Debit\tOnline\t£50 / fuel") ──
        elif '£' in stripped and 'exit' not in lower:
            # This catches the data row under "Payment type / Billing / Exit fee"
            fee_m = re.search(r'£(\d+(?:\.\d+)?)\s*(?:/\s*fuel|per\s*fuel)?', stripped, re.I)
            if fee_m:
                amount = fee_m.group(1)
                if '/fuel' in stripped.lower().replace(' ', '') or 'per fuel' in lower:
                    data['exit_fee'] = f"£{amount} / fuel"
                else:
                    data['exit_fee'] = f"£{amount}"
                
                # Also grab payment type and billing from same line
                if 'direct debit' in lower:
                    data['payment_type'] = 'Direct Debit'
                elif 'prepayment' in lower:
                    data['payment_type'] = 'Prepayment'
                
                if 'online' in lower:
                    data['billing'] = 'Online'
                elif 'paper' in lower:
                    data['billing'] = 'Paper'
    
    # --- Fallback exit fee from labelled row ---
    if 'exit_fee' not in data:
        exit_m = re.search(r'Exit\s*fee\s*[:\s]*£(\d+(?:\.\d+)?)\s*(?:/\s*fuel|per\s*fuel)?', card_text, re.I)
        if exit_m:
            amount = exit_m.group(1)
            context = card_text[exit_m.start():exit_m.end()+20].lower()
            if '/fuel' in context.replace(' ', '') or 'per fuel' in context:
                data['exit_fee'] = f"£{amount} / fuel"
            else:
                data['exit_fee'] = f"£{amount}"
        elif re.search(r'no\s*exit\s*fee', card_text, re.I):
            data['exit_fee'] = "£0"
    
    return data


# ============================================
# NETWORK ERROR DETECTION
# ============================================

def detect_blocking(page) -> tuple:
    try:
        page_text = page.inner_text('body').lower()
        if 'network error' in page_text:
            return True, "network_error"
        if 'access denied' in page_text:
            return True, "access_denied"
        if 'too many requests' in page_text:
            return True, "rate_limited"
        if 'captcha' in page_text or 'verify you are human' in page_text:
            return True, "captcha"
        if 'something went wrong' in page_text:
            return True, "generic_error"
        return False, ""
    except:
        return False, ""


# ============================================
# BROWSER CONTEXT SETUP
# ============================================

def create_stealth_context(browser):
    user_agent = random.choice(USER_AGENTS)
    viewport = random.choice(VIEWPORTS)
    
    context = browser.new_context(
        viewport=viewport,
        user_agent=user_agent,
        locale="en-GB",
        timezone_id="Europe/London",
        geolocation={"latitude": 51.5074, "longitude": -0.1278},
        permissions=["geolocation"],
        color_scheme="light",
        reduced_motion="no-preference",
        has_touch=False,
        is_mobile=False,
        device_scale_factor=1,
        extra_http_headers={
            "Accept-Language": "en-GB,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Upgrade-Insecure-Requests": "1",
            "sec-ch-ua": '"Google Chrome";v="125", "Chromium";v="125", "Not.A/Brand";v="24"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
        }
    )
    
    context.add_init_script(STEALTH_SCRIPTS)
    return context, user_agent, viewport


# ============================================
# MAIN SCRAPING LOGIC
# ============================================

def scrape_so_tariffs(browser, postcode: str, region: str, attempt: int = 1) -> dict:
    """
    Navigate SO Energy tariff page and extract all fixed tariff rates.
    """
    
    result = {
        "supplier": "So Energy",
        "region": region,
        "postcode": postcode,
        "scraped_at": datetime.now().isoformat(),
        "tariffs": [],
        "attempt": attempt,
    }
    
    context = None
    
    try:
        context, user_agent, viewport = create_stealth_context(browser)
        page = context.new_page()
        
        print(f"    🕵️ Stealth: {viewport['width']}x{viewport['height']} | {user_agent[:50]}...")
        
        # ============================================
        # STEP 1: Load SO Energy tariffs page
        # ============================================
        print(f"\n  [STEP 1] Loading So Energy tariffs page...")
        
        human_delay(1000, 3000)
        page.goto(SO_TARIFFS_URL, timeout=60000, wait_until="domcontentloaded")
        human_delay(2000, 4000)
        
        blocked, block_type = detect_blocking(page)
        if blocked:
            raise Exception(f"Blocked on page load: {block_type}")
        
        print(f"    ✓ Page loaded")
        random_scroll(page)
        
        # Handle cookie consent
        try:
            for sel in ['button:has-text("Accept")', 'button:has-text("Accept All")',
                        '#onetrust-accept-btn-handler', '.cookie-accept']:
                try:
                    btn = page.locator(sel).first
                    if btn.is_visible(timeout=2000):
                        human_delay(500, 1200)
                        btn.click()
                        print(f"    ✓ Accepted cookies")
                        human_delay(800, 1500)
                        break
                except:
                    continue
        except:
            pass
        
        # ============================================
        # STEP 2: Enter postcode
        # ============================================
        print(f"\n  [STEP 2] Entering postcode: {postcode}")
        
        postcode_input = None
        for sel in ['input[placeholder*="postcode" i]', 'input[placeholder*="Postcode" i]',
                     'input[name*="postcode" i]', '.quote input', 'input.input']:
            try:
                inp = page.locator(sel).first
                if inp.is_visible(timeout=3000):
                    postcode_input = inp
                    break
            except:
                continue
        
        if not postcode_input:
            page.screenshot(path=f"screenshots/{region.replace(' ', '_')}_no_input.png", full_page=True)
            raise Exception("Could not find postcode input field")
        
        box = postcode_input.bounding_box()
        if box:
            simulate_mouse_movement(page, box['x'] + box['width']/2, box['y'] + box['height']/2)
        
        human_delay(300, 800)
        postcode_input.click()
        human_delay(200, 500)
        postcode_input.fill("")
        human_delay(200, 400)
        
        for char in postcode:
            postcode_input.type(char, delay=human_typing_delay())
        
        human_delay(500, 1200)
        print(f"    ✓ Typed postcode")
        
        # ============================================
        # STEP 3: Click "Find Tariffs"
        # ============================================
        print(f"\n  [STEP 3] Clicking 'Find Tariffs'...")
        
        find_clicked = False
        for sel in ['button:has-text("Find Tariffs")', 'button:has-text("Find tariffs")',
                     '.quote__button', 'button.button:has-text("Find")']:
            try:
                btn = page.locator(sel).first
                if btn.is_visible(timeout=3000):
                    btn.scroll_into_view_if_needed()
                    human_delay(400, 800)
                    btn.click()
                    find_clicked = True
                    print(f"    ✓ Clicked 'Find Tariffs'")
                    break
            except:
                continue
        
        if not find_clicked:
            postcode_input.press("Enter")
            print(f"    ✓ Pressed Enter as fallback")
        
        print(f"    Waiting for tariff results...")
        human_delay(3000, 5000)
        
        blocked, block_type = detect_blocking(page)
        if blocked:
            raise Exception(f"Blocked after Find Tariffs: {block_type}")
        
        # Wait for results section
        try:
            page.locator('.our-tariffs__results, section:has-text("tariff")').first.wait_for(
                state="visible", timeout=15000)
            print(f"    ✓ Tariff results section appeared")
        except:
            print(f"    ⚠ Results section not confirmed, continuing...")
        
        human_delay(1000, 2000)
        
        # ============================================
        # STEP 4: Open Filters and uncheck Variable
        # ============================================
        print(f"\n  [STEP 4] Opening Filters panel...")
        
        try:
            filters_btn = page.locator(
                'button:has-text("Filters"), '
                '.accordion-card__heading:has-text("Filters")'
            ).first
            if filters_btn.is_visible(timeout=5000):
                filters_btn.scroll_into_view_if_needed()
                human_delay(400, 900)
                filters_btn.click()
                print(f"    ✓ Opened Filters")
                human_delay(800, 1500)
        except Exception as e:
            print(f"    ⚠ Could not open Filters: {e}")
        
        # ============================================
        # STEP 5: Uncheck "Variable" (keep only Fixed)
        # ============================================
        print(f"\n  [STEP 5] Unchecking 'Variable' filter...")
        
        try:
            for sel in ['label:has-text("Variable")', '.checkbox:has-text("Variable")',
                        'input[type="checkbox"] + label:has-text("Variable")', 'text="Variable"']:
                try:
                    chk = page.locator(sel).first
                    if chk.is_visible(timeout=3000):
                        human_delay(300, 700)
                        chk.click()
                        print(f"    ✓ Unchecked 'Variable'")
                        human_delay(800, 1500)
                        break
                except:
                    continue
        except Exception as e:
            print(f"    ⚠ Could not uncheck Variable: {e}")
        
        # Also uncheck EV if present
        try:
            for sel in ['label:has-text("EV")', '.checkbox:has-text("EV")']:
                try:
                    chk = page.locator(sel).first
                    if chk.is_visible(timeout=1000):
                        inp = chk.locator('input[type="checkbox"]')
                        if inp.count() > 0 and inp.is_checked():
                            chk.click()
                            print(f"    ✓ Unchecked 'EV'")
                            human_delay(500, 1000)
                except:
                    continue
        except:
            pass
        
        human_delay(1000, 2000)
        page.screenshot(path=f"screenshots/{region.replace(' ', '_')}_filtered.png", full_page=True)
        
        # ============================================
        # STEP 6: Find and expand all tariff accordion cards
        # ============================================
        print(f"\n  [STEP 6] Expanding tariff cards...")
        
        tariff_cards = page.locator(
            '.our-tariffs__results .accordion-card__heading, '
            '.our-tariffs__results button[class*="accordion"], '
            'section:has-text("Current Tariffs") .accordion-card__heading'
        ).all()
        
        if not tariff_cards:
            tariff_cards = page.locator('.accordion-card__heading').all()
        
        # Filter out non-tariff headings (Filters, FAQs etc)
        filtered_cards = []
        for c in tariff_cards:
            try:
                txt = c.inner_text().lower()
                if not any(skip in txt for skip in ['filter', 'faq', 'frequently', 'making switch']):
                    filtered_cards.append(c)
            except:
                continue
        tariff_cards = filtered_cards
        
        print(f"    Found {len(tariff_cards)} tariff card(s) — using first one only")
        
        extracted_tariffs = []
        
        if tariff_cards:
            card = tariff_cards[0]
            try:
                card_title = card.inner_text().strip()
                print(f"\n    [1] Expanding: {card_title[:60]}...")
                
                card.scroll_into_view_if_needed()
                human_delay(400, 900)
                card.click()
                human_delay(1500, 3000)
                
                # Get the expanded card content
                # Try multiple parent levels to capture the full accordion body
                card_text = ""
                for xpath in ['xpath=..', 'xpath=../..', 'xpath=../../..']:
                    try:
                        parent = card.locator(xpath)
                        txt = parent.inner_text()
                        if len(txt) > len(card_text):
                            card_text = txt
                        # Stop if we found rate-like content
                        if 'p / kWh' in txt or 'p/kWh' in txt or 'p / day' in txt:
                            break
                    except:
                        continue
                
                if card_text:
                    debug_file = f"screenshots/{region.replace(' ', '_')}_card_text.txt"
                    with open(debug_file, "w") as f:
                        f.write(card_text)
                    print(f"      📝 Saved card text to {debug_file}")
                    
                    tariff_data = extract_tariff_from_text(card_text)
                    
                    # Use card heading as name if extraction missed it
                    if not tariff_data.get('tariff_name') and card_title:
                        clean = re.split(r'\d+-month|Fixed\s*Rate|Variable\s*Rate', card_title)[0].strip()
                        tariff_data['tariff_name'] = clean if len(clean) > 3 else card_title.split('\n')[0].strip()
                    
                    # Check we got at least one rate
                    has_rates = (tariff_data.get('elec_unit_rate_p') or 
                                 tariff_data.get('gas_unit_rate_p') or
                                 tariff_data.get('eco7_day_rate_p'))
                    
                    if has_rates:
                        extracted_tariffs.append(tariff_data)
                        print(f"      ✓ Elec: {tariff_data.get('elec_unit_rate_p', '-')}p/kWh | "
                              f"SC: {tariff_data.get('elec_standing_p', '-')}p/day")
                        print(f"      ✓ Gas:  {tariff_data.get('gas_unit_rate_p', '-')}p/kWh | "
                              f"SC: {tariff_data.get('gas_standing_p', '-')}p/day")
                        if tariff_data.get('eco7_day_rate_p'):
                            print(f"      ✓ Eco7: Day {tariff_data['eco7_day_rate_p']}p | "
                                  f"Night {tariff_data.get('eco7_night_rate_p', '-')}p | "
                                  f"SC: {tariff_data.get('eco7_standing_p', '-')}p/day")
                        print(f"      ✓ Exit: {tariff_data.get('exit_fee', 'N/A')}")
                    else:
                        print(f"      ⚠ No rates found ({len(card_text)} chars)")
                        print(f"      Preview: {card_text[:200]}...")
                
            except Exception as e:
                print(f"      ✗ Error expanding card: {e}")
        
        # ============================================
        # STEP 7: Fallback - full page text
        # ============================================
        if not extracted_tariffs:
            print(f"\n  [STEP 7] Fallback: extracting from full page text...")
            
            page_text = page.inner_text('body')
            
            # Split by tariff name boundaries
            sections = re.split(r'(?=So\s+\w+\s+(?:One|Two|Three)\s+Year)', page_text)
            
            for section in sections:
                if len(section) < 30:
                    continue
                data = extract_tariff_from_text(section)
                if data.get('elec_unit_rate_p') or data.get('gas_unit_rate_p'):
                    extracted_tariffs.append(data)
            
            if extracted_tariffs:
                print(f"    ✓ Extracted {len(extracted_tariffs)} tariff(s) from full page")
            else:
                print(f"    ✗ No tariffs found")
                with open(f"screenshots/{region.replace(' ', '_')}_pagetext.txt", "w") as f:
                    f.write(page_text)
        
        page.screenshot(path=f"screenshots/{region.replace(' ', '_')}_final.png", full_page=True)
        
        if extracted_tariffs:
            result['tariffs'] = extracted_tariffs
            print(f"\n    ✅ SUCCESS: {len(extracted_tariffs)} tariff(s) for {region}")
        else:
            result['error'] = "No tariff rates could be extracted"
            print(f"\n    ✗ FAILED: No tariffs for {region}")
        
        result['url'] = page.url
        
    except PlaywrightTimeout as e:
        result['error'] = f"Timeout: {str(e)}"
        print(f"\n    ✗ TIMEOUT: {e}")
        try:
            context.pages[0].screenshot(path=f"screenshots/{region.replace(' ', '_')}_error.png")
        except:
            pass
    except Exception as e:
        result['error'] = str(e)
        print(f"\n    ✗ ERROR: {e}")
        try:
            context.pages[0].screenshot(path=f"screenshots/{region.replace(' ', '_')}_error.png")
        except:
            pass
    finally:
        if context:
            context.close()
    
    return result


# ============================================
# RETRY WITH EXPONENTIAL BACKOFF
# ============================================

def scrape_with_retry(browser, postcode: str, region: str, max_attempts: int = 3) -> dict:
    for attempt in range(1, max_attempts + 1):
        print(f"\n  🔄 Attempt {attempt}/{max_attempts}")
        result = scrape_so_tariffs(browser, postcode, region, attempt)
        if result.get('tariffs'):
            return result
        if attempt < max_attempts:
            wait_time = 30 * (2 ** (attempt - 1))
            print(f"\n  ⏳ Failed. Waiting {wait_time}s before retry...")
            time.sleep(wait_time)
    return result


# ============================================
# MAIN RUNNER
# ============================================

def run_scraper(headless: bool = False, test_postcode: str = None,
                wait_secs: int = 20, max_retries: int = 3):
    
    results = []
    consecutive_failures = 0  # Track consecutive failures for warnings
    
    if test_postcode:
        postcodes = {k: v for k, v in DNO_POSTCODES_ALL.items() if v == test_postcode}
        if not postcodes:
            postcodes = {"Test": test_postcode}
    else:
        postcodes = DNO_POSTCODES_ALL
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            slow_mo=30,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-features=IsolateOrigins,site-per-process',
                '--disable-site-isolation-trials',
                '--disable-web-security',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-accelerated-2d-canvas',
                '--no-first-run',
                '--no-zygote',
                '--disable-gpu',
                '--hide-scrollbars',
                '--mute-audio',
                '--disable-background-networking',
                '--disable-background-timer-throttling',
                '--disable-backgrounding-occluded-windows',
                '--disable-breakpad',
                '--disable-component-extensions-with-background-pages',
                '--disable-component-update',
                '--disable-default-apps',
                '--disable-domain-reliability',
                '--disable-extensions',
                '--disable-features=TranslateUI',
                '--disable-hang-monitor',
                '--disable-ipc-flooding-protection',
                '--disable-popup-blocking',
                '--disable-prompt-on-repost',
                '--disable-renderer-backgrounding',
                '--disable-sync',
                '--force-color-profile=srgb',
                '--metrics-recording-only',
                '--password-store=basic',
                '--use-mock-keychain',
            ]
        )
        print("  🌐 Browser launched with stealth mode")
        
        for i, (region, postcode) in enumerate(postcodes.items()):
            print(f"\n{'='*60}")
            print(f"  SCRAPING [{i+1}/{len(postcodes)}]: {region} ({postcode})")
            print('='*60)
            
            result = scrape_with_retry(browser, postcode, region, max_retries)
            results.append(result)
            
            if result.get('tariffs'):
                with open("so_tariffs_partial.json", "w") as f:
                    json.dump(results, f, indent=2)
                print(f"  ✓ Success! (Saved)")
                consecutive_failures = 0
            else:
                print(f"  ✗ Failed after {max_retries} attempts")
                consecutive_failures += 1
            
            # WARNING: Log consecutive failures but continue collecting data
            if consecutive_failures >= 5 and len(results) <= 7:
                print(f"\n  ⚠️  WARNING: {consecutive_failures} consecutive failures")
                print(f"  → Continuing to collect partial data from remaining regions...")
            # Don't break - continue to try all regions
            
            # Wait between regions
            if i < len(postcodes) - 1:
                actual_wait = wait_secs + random.randint(-5, 10)
                print(f"\n  ⏳ Waiting {actual_wait}s...")
                time.sleep(actual_wait)
        
        browser.close()
    
    return results


def save_results(results: list):
    """Save to JSON and CSV."""
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # JSON
    json_file = f"so_tariffs_{timestamp}.json"
    with open(json_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved: {json_file}")
    
    # CSV
    csv_file = f"so_tariffs_{timestamp}.csv"
    rows = []
    
    for r in results:
        base = {
            "supplier": r.get("supplier", "So Energy"),
            "region": r["region"],
            "postcode": r["postcode"],
            "scraped_at": r["scraped_at"],
            "attempt": r.get("attempt", 1),
        }
        
        if r.get("tariffs"):
            for t in r["tariffs"]:
                row = base.copy()
                row.update({
                    "tariff_name": t.get("tariff_name", ""),
                    "tariff_type": t.get("tariff_type", ""),
                    "duration": t.get("duration", ""),
                    "exit_fee": t.get("exit_fee", ""),
                    "payment_type": t.get("payment_type", ""),
                    "billing": t.get("billing", ""),
                    "elec_unit_rate_p": t.get("elec_unit_rate_p"),
                    "elec_standing_p": t.get("elec_standing_p"),
                    "gas_unit_rate_p": t.get("gas_unit_rate_p"),
                    "gas_standing_p": t.get("gas_standing_p"),
                    "eco7_standing_p": t.get("eco7_standing_p"),
                    "eco7_day_rate_p": t.get("eco7_day_rate_p"),
                    "eco7_night_rate_p": t.get("eco7_night_rate_p"),
                })
                rows.append(row)
        else:
            row = base.copy()
            row["error"] = r.get("error", "No tariffs found")
            rows.append(row)
    
    fieldnames = [
        "supplier", "region", "postcode", "scraped_at", "attempt",
        "tariff_name", "tariff_type", "duration", "exit_fee",
        "payment_type", "billing",
        "elec_unit_rate_p", "elec_standing_p",
        "gas_unit_rate_p", "gas_standing_p",
        "eco7_standing_p", "eco7_day_rate_p", "eco7_night_rate_p",
        "error",
    ]
    
    with open(csv_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)
    print(f"Saved: {csv_file}")
    
    # Summary table
    print("\n" + "="*160)
    print("RESULTS SUMMARY")
    print("="*160)
    print(f"{'Region':<22} {'Tariff':<25} {'Type':<8} {'Exit':<12} "
          f"{'Elec p/kWh':<11} {'Elec SC':<9} {'Gas p/kWh':<10} {'Gas SC':<9} "
          f"{'E7 Day':<8} {'E7 Night':<9} {'E7 SC':<8}")
    print("-"*160)
    
    success_count = 0
    for r in results:
        if r.get("tariffs"):
            success_count += 1
            for t in r["tariffs"]:
                print(f"{r['region']:<22} {t.get('tariff_name','N/A')[:24]:<25} "
                      f"{t.get('tariff_type','')[:7]:<8} {t.get('exit_fee','N/A'):<12} "
                      f"{t.get('elec_unit_rate_p','-'):<11} {t.get('elec_standing_p','-'):<9} "
                      f"{t.get('gas_unit_rate_p','-'):<10} {t.get('gas_standing_p','-'):<9} "
                      f"{t.get('eco7_day_rate_p','-'):<8} {t.get('eco7_night_rate_p','-'):<9} "
                      f"{t.get('eco7_standing_p','-'):<8}")
        else:
            print(f"{r['region']:<22} {'ERROR':<25} {'':<8} {'':<12} {r.get('error', 'Unknown')}")
    
    print(f"\nSuccess rate: {success_count}/{len(results)} ({100*success_count/len(results):.1f}%)")


def main():
    import os
    import argparse
    
    parser = argparse.ArgumentParser(description="So Energy Tariff Scraper v2 - Stealth Edition")
    parser.add_argument("--headless", action="store_true", help="Run headless")
    parser.add_argument("--test", type=str, help="Test single postcode (e.g. 'N5 2SD')")
    parser.add_argument("--wait", type=int, default=20, help="Base seconds between regions (default: 20)")
    parser.add_argument("--retries", type=int, default=3, help="Max retries per region (default: 3)")
    args = parser.parse_args()
    
    os.makedirs("screenshots", exist_ok=True)
    
    print("="*60)
    print("SO ENERGY TARIFF SCRAPER v2 - STEALTH EDITION")
    print("="*60)
    print(f"🕵️ Anti-detection: Rotating fingerprints, human simulation")
    print(f"📋 Extracts: Tariff name, type, exit fee, unit rates,")
    print(f"   standing charges, Eco 7 day/night rates")
    print(f"⏱️ Wait: ~{args.wait}s between regions")
    print(f"🔄 Max retries: {args.retries} (with exponential backoff)")
    print(f"🌐 URL: {SO_TARIFFS_URL}")
    print("")
    print("Press Ctrl+C to stop")
    
    results = run_scraper(
        headless=args.headless,
        test_postcode=args.test,
        wait_secs=args.wait,
        max_retries=args.retries
    )
    save_results(results)
    
    input("\nPress Enter to exit...")


if __name__ == "__main__":
    main()
