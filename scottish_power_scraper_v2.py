#!/usr/bin/env python3
"""
Scottish Power Tariff Scraper v2
- Playwright-based with stealth mode
- PROPER WAITS for slow-loading pages
- Human-like behavior simulation
- All 14 DNO regions
- Outputs JSON + CSV matching BG/E.ON/OVO format

Flow:
1. Enter postcode → Wait for address dropdown
2. Select address → Wait for energy type page
3. Select "Electricity and gas" → Wait
4. Select "Direct Debit" → Wait
5. Click Continue → Wait for tariff options page
6. Select cheapest tariff → Wait for tariff details
7. Extract rates
"""

import json
import csv
import re
import random
import time
import os
from datetime import datetime
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# ============================================
# CONFIGURATION
# ============================================

DNO_POSTCODES = {
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

SP_QUOTE_URL = "https://www.scottishpower.co.uk/energy/address"

# Postcodes needing different starting address indices
POSTCODE_START_INDEX = {
    "BN2 7HQ": 10,
    "AB24 3EN": 5,
    "G20 6NQ": 5,
}

# User agents pool - Firefox
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (X11; Linux x86_64; rv:126.0) Gecko/20100101 Firefox/126.0",
]

VIEWPORTS = [
    {"width": 1920, "height": 1080},
    {"width": 1536, "height": 864},
    {"width": 1440, "height": 900},
    {"width": 1366, "height": 768},
]

# ============================================
# STEALTH SCRIPTS
# ============================================

STEALTH_SCRIPTS = """
// Firefox stealth - simpler than Chrome
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
console.log('Stealth mode activated');
"""


# ============================================
# HUMAN BEHAVIOR SIMULATION
# ============================================

def human_delay(min_ms=500, max_ms=2000):
    """Random delay with human-like distribution."""
    delay = random.betavariate(2, 5) * (max_ms - min_ms) + min_ms
    time.sleep(delay / 1000)


def long_delay():
    """Longer delay for page transitions."""
    time.sleep(random.uniform(3, 6))


def human_typing_delay():
    """Return realistic typing delay in ms."""
    if random.random() < 0.1:
        return random.randint(200, 400)
    return random.randint(50, 150)


def simulate_mouse_movement(page, target_x, target_y):
    """Simulate natural mouse movement."""
    steps = random.randint(5, 15)
    current_x = random.randint(400, 600)
    current_y = random.randint(300, 400)
    
    for i in range(steps):
        progress = (i + 1) / steps
        noise_x = random.gauss(0, 5)
        noise_y = random.gauss(0, 5)
        new_x = current_x + (target_x - current_x) * progress + noise_x
        new_y = current_y + (target_y - current_y) * progress + noise_y
        page.mouse.move(new_x, new_y)
        time.sleep(random.uniform(0.01, 0.03))


def random_scroll(page):
    """Perform random scrolling."""
    scroll_amount = random.randint(100, 300)
    page.mouse.wheel(0, scroll_amount)
    human_delay(300, 800)


# ============================================
# RATE EXTRACTION
# ============================================

def extract_tariff_rates(page_text: str) -> dict:
    """Extract rates from Scottish Power tariff details page."""
    rates = {}
    
    print(f"    📄 Page text length: {len(page_text)} chars")
    
    # Tariff name patterns
    tariff_patterns = [
        r'(\d\s*Year\s*Fixed[^\n]*)',  # "1 Year Fixed", "2 Year Fixed"
        r'(Fixed\s*\d+\s*Year[^\n]*)',  # "Fixed 1 Year"
        r'(Exclusive Online Fixed[^\n]*)',
        r'(Standard Variable[^\n]*)',
        r'(Fixed Price[^\n]*\d{4})',
        r'(ScottishPower[^\n]*Tariff[^\n]*)',
        r'(Fixed\s+(?:Price\s+)?[A-Za-z]+\s+\d{4})',
        r'(Online\s*Fixed[^\n]*)',
        r'(Variable[^\n]*Tariff[^\n]*)',
    ]
    
    for pattern in tariff_patterns:
        match = re.search(pattern, page_text, re.I)
        if match:
            tariff_name = match.group(1).strip()
            tariff_name = re.sub(r'\s+', ' ', tariff_name)
            if len(tariff_name) > 5:
                rates['tariff_name'] = tariff_name
                break
    
    # Exit fee
    exit_patterns = [
        r'Exit\s*fee[:\s]*£(\d+(?:\.\d+)?)\s*(per\s*fuel)?',
        r'Cancellation\s*fee[:\s]*£(\d+(?:\.\d+)?)',
        r'£(\d+(?:\.\d+)?)\s*(?:per\s*fuel\s*)?exit\s*fee',
        r'Early\s*termination[:\s]*£(\d+(?:\.\d+)?)',
    ]
    
    for pattern in exit_patterns:
        match = re.search(pattern, page_text, re.I)
        if match:
            amount = match.group(1)
            per_fuel = match.group(2) if len(match.groups()) > 1 else None
            rates['exit_fee'] = f"£{amount} per fuel" if per_fuel else f"£{amount}"
            break
    
    if 'exit_fee' not in rates:
        if re.search(r'no\s*exit\s*fee|£0\s*exit|exit\s*fee.*?£?0', page_text, re.I):
            rates['exit_fee'] = "£0"
    
    # Split page into Electricity and Gas sections for accurate extraction
    # Electricity section
    elec_section_match = re.search(
        r'Electricity(.*?)(?=Gas\b|$)',
        page_text, re.I | re.S
    )
    elec_text = elec_section_match.group(1) if elec_section_match else ""
    
    # Gas section
    gas_section_match = re.search(
        r'Gas\b(.*?)(?=Electricity|$)',
        page_text, re.I | re.S
    )
    gas_text = gas_section_match.group(1) if gas_section_match else ""
    
    # Electricity unit rate
    elec_unit_patterns = [
        r'Unit\s*rate[:\s]*(\d+\.?\d*)\s*p(?:\s*per\s*kWh)?',
        r'(\d+\.?\d*)\s*p\s*per\s*kWh',
        r'(\d+\.?\d*)\s*p/kWh',
        r'(\d+\.\d{2,})\s*p',  # e.g., 24.50p
    ]
    
    for pattern in elec_unit_patterns:
        match = re.search(pattern, elec_text, re.I)
        if match:
            val = float(match.group(1))
            if 10 < val < 50:  # Sanity check for unit rates
                rates['elec_unit_rate_p'] = val
                break
    
    # Electricity standing charge
    elec_sc_patterns = [
        r'Standing\s*charge[:\s]*(\d+\.?\d*)\s*p(?:\s*per\s*day)?',
        r'(\d+\.?\d*)\s*p\s*per\s*day',
        r'(\d+\.?\d*)\s*p/day',
    ]
    
    for pattern in elec_sc_patterns:
        match = re.search(pattern, elec_text, re.I)
        if match:
            val = float(match.group(1))
            if 20 < val < 80:  # Sanity check for standing charges
                rates['elec_standing_p'] = val
                break
    
    # Gas unit rate
    for pattern in elec_unit_patterns:
        match = re.search(pattern, gas_text, re.I)
        if match:
            val = float(match.group(1))
            if 3 < val < 20:  # Gas is cheaper than elec
                rates['gas_unit_rate_p'] = val
                break
    
    # Gas standing charge
    for pattern in elec_sc_patterns:
        match = re.search(pattern, gas_text, re.I)
        if match:
            val = float(match.group(1))
            if 20 < val < 50:
                rates['gas_standing_p'] = val
                break
    
    # If no sections found, try generic extraction
    if not rates.get('elec_unit_rate_p') and not rates.get('gas_unit_rate_p'):
        print(f"    ⚠ Section-based extraction failed, trying generic patterns...")
        all_rates = re.findall(r'(\d+\.\d+)\s*p', page_text)
        if all_rates:
            print(f"    📊 Found prices: {all_rates[:10]}")
    
    return rates


def validate_rates(rates: dict) -> bool:
    """Sanity check extracted rates."""
    warnings = []
    
    elec_unit = rates.get('elec_unit_rate_p')
    if elec_unit:
        if elec_unit > 50 or elec_unit < 10:
            warnings.append(f"Elec unit {elec_unit}p outside typical range")
    
    gas_unit = rates.get('gas_unit_rate_p')
    if gas_unit:
        if gas_unit > 20 or gas_unit < 3:
            warnings.append(f"Gas unit {gas_unit}p outside typical range")
    
    elec_sc = rates.get('elec_standing_p')
    if elec_sc:
        if elec_sc > 70 or elec_sc < 20:
            warnings.append(f"Elec standing {elec_sc}p outside typical range")
    
    gas_sc = rates.get('gas_standing_p')
    if gas_sc:
        if gas_sc > 50 or gas_sc < 20:
            warnings.append(f"Gas standing {gas_sc}p outside typical range")
    
    if warnings:
        print(f"    ⚠️  Validation: {'; '.join(warnings)}")
    
    return len(warnings) == 0


# ============================================
# BROWSER SETUP
# ============================================

def create_stealth_context(browser):
    """Create browser context with stealth settings."""
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
        }
    )
    
    context.add_init_script(STEALTH_SCRIPTS)
    return context, user_agent, viewport


# ============================================
# MAIN SCRAPING LOGIC
# ============================================

def scrape_sp_tariffs(browser, postcode: str, region: str, attempt: int = 1,
                      tried_addresses: set = None) -> tuple:
    """Navigate Scottish Power quote journey and extract tariffs."""
    
    if tried_addresses is None:
        tried_addresses = set()
    
    result = {
        "supplier": "scottish_power",
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
        
        print(f"    🕵️ Stealth: {viewport['width']}x{viewport['height']}")
        
        # ============================================
        # STEP 1: Load Scottish Power quote page
        # ============================================
        print(f"\n  [STEP 1] Loading Scottish Power website...")
        
        human_delay(1000, 2000)
        page.goto(SP_QUOTE_URL, timeout=60000, wait_until="domcontentloaded")
        
        # Wait for page to fully load
        print(f"    Waiting for page to fully load...")
        human_delay(3000, 5000)
        
        print(f"    ✓ Page loaded")
        
        # Handle cookies
        try:
            cookie_selectors = [
                'button:has-text("Accept")',
                'button:has-text("Accept all")',
                '#onetrust-accept-btn-handler',
                '[id*="accept"]',
            ]
            for selector in cookie_selectors:
                try:
                    btn = page.locator(selector).first
                    if btn.is_visible(timeout=3000):
                        human_delay(500, 1000)
                        btn.click()
                        print(f"    ✓ Accepted cookies")
                        human_delay(1000, 2000)
                        break
                except:
                    continue
        except:
            pass
        
        # ============================================
        # STEP 2: Enter postcode
        # ============================================
        print(f"\n  [STEP 2] Entering postcode: {postcode}")
        
        # Find postcode input - wait for it explicitly
        postcode_selectors = [
            'input[name*="postcode" i]',
            'input[placeholder*="postcode" i]',
            'input[id*="postcode" i]',
            '#postcode',
            'input[type="text"]',
        ]
        
        postcode_input = None
        for selector in postcode_selectors:
            try:
                page.wait_for_selector(selector, timeout=10000)
                inp = page.locator(selector).first
                if inp.is_visible(timeout=3000):
                    postcode_input = inp
                    print(f"    ✓ Found postcode input: {selector}")
                    break
            except:
                continue
        
        if not postcode_input:
            page.screenshot(path=f"screenshots/sp_{region.replace(' ', '_')}_no_postcode.png")
            raise Exception("Could not find postcode input")
        
        # Click and type postcode
        box = postcode_input.bounding_box()
        if box:
            simulate_mouse_movement(page, box['x'] + box['width']/2, box['y'] + box['height']/2)
        
        human_delay(500, 800)
        postcode_input.click()
        human_delay(300, 500)
        
        # Clear and type
        postcode_input.fill('')
        for char in postcode:
            postcode_input.type(char, delay=human_typing_delay())
        
        print(f"    ✓ Typed postcode")
        
        # Wait for address dropdown to populate
        print(f"    Waiting for address lookup...")
        human_delay(3000, 5000)
        
        # ============================================
        # STEP 3: Select address
        # ============================================
        print(f"\n  [STEP 3] Selecting address...")
        
        # Wait for address dropdown to appear
        address_selectors = [
            'select#address',
            'select[name*="address" i]',
            'select',
            '[role="listbox"]',
        ]
        
        address_select = None
        for selector in address_selectors:
            try:
                page.wait_for_selector(selector, timeout=15000)
                sel = page.locator(selector).first
                if sel.is_visible(timeout=5000):
                    address_select = sel
                    print(f"    ✓ Found address dropdown: {selector}")
                    break
            except:
                continue
        
        if not address_select:
            page.screenshot(path=f"screenshots/sp_{region.replace(' ', '_')}_no_dropdown.png")
            raise Exception("Address dropdown did not appear")
        
        human_delay(1000, 2000)
        
        # Get options
        options = address_select.locator('option').all()
        print(f"    Found {len(options)} addresses")
        
        # Find valid residential address
        start_idx = POSTCODE_START_INDEX.get(postcode, 1)
        selected = False
        skip_words = ['flat', 'apartment', 'floor', 'unit', 'suite', 'apt', 'room', 'basement']
        
        for i in range(start_idx, min(len(options), start_idx + 15)):
            if i in tried_addresses:
                continue
            try:
                text = options[i].text_content().strip()
                if not text or not text[0].isdigit():
                    continue
                if any(w in text.lower() for w in skip_words):
                    continue
                
                print(f"    Selecting: {text[:50]}...")
                tried_addresses.add(i)
                address_select.select_option(index=i)
                selected = True
                break
            except:
                continue
        
        if not selected:
            address_select.select_option(index=1)
            tried_addresses.add(1)
        
        print(f"    ✓ Address selected")
        
        # IMPORTANT: Wait for next page section to load
        print(f"    Waiting for energy options to load...")
        human_delay(4000, 6000)
        
        # Take screenshot
        page.screenshot(path=f"screenshots/sp_{region.replace(' ', '_')}_after_address.png")
        
        # ============================================
        # CHECK: "We need more information" or MPAN blocker
        # ============================================
        page_text = page.inner_text('body').lower()
        
        # Debug: print snippet of page text
        print(f"    📄 Page check: {page_text[:200]}...")
        
        max_address_retries = 8
        address_retry_count = 0
        
        # Check for MPAN prompt (same page - just pick different address)
        def has_mpan_prompt(text):
            triggers = ['mpan', 'mprn', 'meter point', 'select your meter', 'which meter', 'confirm your meter details', 'electricity meter', 'gas meter', 'enter a valid']
            found = [t for t in triggers if t in text]
            if found:
                print(f"    🔍 MPAN triggers found: {found}")
            return len(found) > 0
        
        # Check for "need more info" page (need to click back)
        def has_info_blocker(text):
            return any(b in text for b in ['we need more information', 'request a call back']) and 'call us' in text
        
        # Handle MPAN - just pick different address from same page
        while has_mpan_prompt(page_text) and address_retry_count < max_address_retries:
            address_retry_count += 1
            print(f"    ⚠ MPAN prompt detected - selecting different address ({address_retry_count}/{max_address_retries})...")
            
            # Re-find address dropdown (same page)
            address_select = None
            for selector in ['select#address', 'select[name*="address" i]', 'select']:
                try:
                    sel = page.locator(selector).first
                    if sel.is_visible(timeout=3000):
                        address_select = sel
                        break
                except:
                    continue
            
            if not address_select:
                print(f"    ✗ Could not find address dropdown")
                break
            
            # Get options and try next address
            options = address_select.locator('option').all()
            next_selected = False
            
            for i in range(start_idx + address_retry_count, min(len(options), start_idx + 20)):
                if i in tried_addresses:
                    continue
                try:
                    text = options[i].text_content().strip()
                    if not text or not text[0].isdigit():
                        continue
                    if any(w in text.lower() for w in skip_words):
                        continue
                    
                    print(f"    Trying: {text[:50]}...")
                    tried_addresses.add(i)
                    address_select.select_option(index=i)
                    next_selected = True
                    break
                except:
                    continue
            
            if not next_selected:
                print(f"    ✗ No more valid addresses to try")
                break
            
            human_delay(4000, 6000)
            page_text = page.inner_text('body').lower()
        
        # Handle "We need more information" page - need to click back
        while has_info_blocker(page_text) and address_retry_count < max_address_retries:
            address_retry_count += 1
            print(f"    ⚠ 'We need more information' page - clicking back ({address_retry_count}/{max_address_retries})...")
            
            # Click Back or Change button
            back_clicked = False
            for selector in ['a:has-text("Back")', 'text="Back"', 'text="Change"', 'button:has-text("Back")', 'a[href*="back"]']:
                try:
                    btn = page.locator(selector).first
                    if btn.is_visible(timeout=3000):
                        btn.click()
                        back_clicked = True
                        print(f"    ✓ Clicked Back/Change")
                        break
                except:
                    continue
            
            if not back_clicked:
                print(f"    ✗ Could not click Back")
                break
            
            human_delay(3000, 5000)
            
            # Re-find address dropdown
            address_select = None
            for selector in ['select#address', 'select[name*="address" i]', 'select']:
                try:
                    sel = page.locator(selector).first
                    if sel.is_visible(timeout=5000):
                        address_select = sel
                        break
                except:
                    continue
            
            if not address_select:
                print(f"    ✗ Could not find address dropdown after going back")
                break
            
            # Get options and try next address
            options = address_select.locator('option').all()
            next_selected = False
            
            for i in range(start_idx + address_retry_count, min(len(options), start_idx + 20)):
                if i in tried_addresses:
                    continue
                try:
                    text = options[i].text_content().strip()
                    if not text or not text[0].isdigit():
                        continue
                    if any(w in text.lower() for w in skip_words):
                        continue
                    
                    print(f"    Trying: {text[:50]}...")
                    tried_addresses.add(i)
                    address_select.select_option(index=i)
                    next_selected = True
                    break
                except:
                    continue
            
            if not next_selected:
                print(f"    ✗ No more valid addresses to try")
                break
            
            human_delay(4000, 6000)
            page_text = page.inner_text('body').lower()
        
        if has_mpan_prompt(page_text) or has_info_blocker(page_text):
            raise Exception(f"All addresses blocked after {address_retry_count} attempts")
        
        # ============================================
        # STEP 4: Select energy type (Electricity and Gas)
        # ============================================
        print(f"\n  [STEP 4] Selecting energy type...")
        
        # Wait for energy type section to appear
        energy_indicators = [
            'text="What energy do you need?"',
            'text="Electricity and gas"',
            'text=/energy.*need/i',
            ':has-text("Electricity and gas")',
        ]
        
        energy_section_found = False
        for indicator in energy_indicators:
            try:
                page.wait_for_selector(indicator, timeout=15000)
                print(f"    ✓ Energy section loaded (found: {indicator})")
                energy_section_found = True
                break
            except:
                continue
        
        if not energy_section_found:
            print(f"    ⚠ Energy section not detected, checking page...")
            page.screenshot(path=f"screenshots/sp_{region.replace(' ', '_')}_no_energy.png")
            page_text = page.inner_text('body')
            print(f"    Page preview: {page_text[:300]}...")
        
        human_delay(1500, 2500)
        
        # Click "Electricity and gas"
        energy_options = [
            'text="Electricity and gas"',
            'label:has-text("Electricity and gas")',
            '[value*="dual" i]',
            '[value*="both" i]',
            'input[type="radio"] + label:has-text("Electricity and gas")',
        ]
        
        energy_selected = False
        for selector in energy_options:
            try:
                option = page.locator(selector).first
                if option.is_visible(timeout=3000):
                    human_delay(500, 800)
                    option.click()
                    print(f"    ✓ Selected electricity and gas")
                    energy_selected = True
                    break
            except:
                continue
        
        if not energy_selected:
            print(f"    ⚠ Could not click energy option, trying to continue anyway...")
        
        human_delay(2000, 3000)
        
        # ============================================
        # CHECK AGAIN: MPAN might appear after energy selection
        # ============================================
        page_text = page.inner_text('body').lower()
        
        while has_mpan_prompt(page_text) and address_retry_count < max_address_retries:
            address_retry_count += 1
            print(f"    ⚠ MPAN prompt detected after energy selection - trying different address ({address_retry_count}/{max_address_retries})...")
            
            # Scroll up to find address dropdown (same page)
            page.keyboard.press("Home")
            human_delay(500, 1000)
            
            # Re-find address dropdown
            address_select = None
            for selector in ['select#address', 'select[name*="address" i]', 'select']:
                try:
                    sel = page.locator(selector).first
                    if sel.is_visible(timeout=3000):
                        address_select = sel
                        break
                except:
                    continue
            
            if not address_select:
                print(f"    ✗ Could not find address dropdown")
                break
            
            # Get options and try next address
            options = address_select.locator('option').all()
            next_selected = False
            
            for i in range(start_idx + address_retry_count, min(len(options), start_idx + 20)):
                if i in tried_addresses:
                    continue
                try:
                    text = options[i].text_content().strip()
                    if not text or not text[0].isdigit():
                        continue
                    if any(w in text.lower() for w in skip_words):
                        continue
                    
                    print(f"    Trying: {text[:50]}...")
                    tried_addresses.add(i)
                    address_select.select_option(index=i)
                    next_selected = True
                    break
                except:
                    continue
            
            if not next_selected:
                print(f"    ✗ No more valid addresses to try")
                break
            
            human_delay(4000, 6000)
            
            # Re-select energy type
            for selector in energy_options:
                try:
                    option = page.locator(selector).first
                    if option.is_visible(timeout=3000):
                        human_delay(500, 800)
                        option.click()
                        break
                except:
                    continue
            
            human_delay(2000, 3000)
            page_text = page.inner_text('body').lower()
        
        if has_mpan_prompt(page_text):
            raise Exception(f"All addresses require MPAN after {address_retry_count} attempts")
        
        # ============================================
        # STEP 5: Click Continue after energy selection
        # ============================================
        print(f"\n  [STEP 5] Clicking Continue after energy selection...")
        
        continue_selectors_1 = [
            'button:has-text("Continue")',
            'button:has-text("Next")',
            'button[type="submit"]',
        ]
        
        continue_clicked_1 = False
        for selector in continue_selectors_1:
            try:
                btn = page.locator(selector).first
                if btn.is_visible(timeout=5000):
                    btn.scroll_into_view_if_needed()
                    human_delay(800, 1200)
                    btn.click()
                    print(f"    ✓ Clicked Continue")
                    continue_clicked_1 = True
                    break
            except:
                continue
        
        if not continue_clicked_1:
            print(f"    ⚠ Could not find Continue button, trying Enter...")
            page.keyboard.press("Enter")
        
        # Wait for payment page to load
        print(f"    Waiting for payment options page...")
        human_delay(5000, 8000)
        
        page.screenshot(path=f"screenshots/sp_{region.replace(' ', '_')}_payment_page.png")
        
        # ============================================
        # CHECK: Business address popup - go back and try different address
        # ============================================
        page_text = page.inner_text('body').lower()
        
        while ('business address' in page_text or 'looks like a business' in page_text) and address_retry_count < max_address_retries:
            address_retry_count += 1
            print(f"    ⚠ Business address detected - going back to try different address ({address_retry_count}/{max_address_retries})...")
            
            # Click Back
            back_clicked = False
            for selector in ['a:has-text("Back")', 'text="Back"', 'button:has-text("Back")']:
                try:
                    btn = page.locator(selector).first
                    if btn.is_visible(timeout=3000):
                        btn.click()
                        back_clicked = True
                        print(f"    ✓ Clicked Back")
                        break
                except:
                    continue
            
            if not back_clicked:
                print(f"    ✗ Could not click Back")
                break
            
            human_delay(3000, 5000)
            
            # Go back again to address page (might need 2 backs)
            page_text_check = page.inner_text('body').lower()
            if 'what energy' in page_text_check:
                # We're on energy page, need to go back once more
                for selector in ['a:has-text("Back")', 'text="Back"', 'button:has-text("Back")']:
                    try:
                        btn = page.locator(selector).first
                        if btn.is_visible(timeout=3000):
                            btn.click()
                            print(f"    ✓ Clicked Back again to address page")
                            break
                    except:
                        continue
                human_delay(3000, 5000)
            
            # Re-find address dropdown
            address_select = None
            for selector in ['select#address', 'select[name*="address" i]', 'select']:
                try:
                    sel = page.locator(selector).first
                    if sel.is_visible(timeout=5000):
                        address_select = sel
                        break
                except:
                    continue
            
            if not address_select:
                print(f"    ✗ Could not find address dropdown")
                break
            
            # Get options and try next address
            options = address_select.locator('option').all()
            next_selected = False
            
            for i in range(start_idx + address_retry_count, min(len(options), start_idx + 20)):
                if i in tried_addresses:
                    continue
                try:
                    text = options[i].text_content().strip()
                    if not text or not text[0].isdigit():
                        continue
                    if any(w in text.lower() for w in skip_words):
                        continue
                    
                    print(f"    Trying: {text[:50]}...")
                    tried_addresses.add(i)
                    address_select.select_option(index=i)
                    next_selected = True
                    break
                except:
                    continue
            
            if not next_selected:
                print(f"    ✗ No more valid addresses to try")
                break
            
            human_delay(4000, 6000)
            
            # Re-do energy selection and continue
            page_text = page.inner_text('body').lower()
            
            # Check for blockers again before continuing
            if has_mpan_prompt(page_text):
                continue  # Will loop and try another address
            
            # Select energy type again
            for selector in energy_options:
                try:
                    option = page.locator(selector).first
                    if option.is_visible(timeout=3000):
                        human_delay(500, 800)
                        option.click()
                        print(f"    ✓ Re-selected electricity and gas")
                        break
                except:
                    continue
            
            human_delay(2000, 3000)
            
            # Click Continue again
            for selector in continue_selectors_1:
                try:
                    btn = page.locator(selector).first
                    if btn.is_visible(timeout=5000):
                        btn.scroll_into_view_if_needed()
                        human_delay(800, 1200)
                        btn.click()
                        print(f"    ✓ Clicked Continue")
                        break
                except:
                    continue
            
            human_delay(5000, 8000)
            page_text = page.inner_text('body').lower()
        
        if 'business address' in page_text or 'looks like a business' in page_text:
            raise Exception(f"All addresses flagged as business after {address_retry_count} attempts")
        
        # ============================================
        # STEP 6: Select payment method (Direct Debit)
        # ============================================
        print(f"\n  [STEP 6] Selecting payment method...")
        
        # Wait for payment options
        payment_indicators = [
            'text="Direct Debit"',
            'text=/pay.*Direct Debit/i',
            'text=/payment.*method/i',
        ]
        
        for indicator in payment_indicators:
            try:
                page.wait_for_selector(indicator, timeout=10000)
                print(f"    ✓ Payment section loaded")
                break
            except:
                continue
        
        human_delay(1000, 2000)
        
        # Click Direct Debit option
        payment_selectors = [
            'text="Direct Debit"',
            'text="I pay by Direct Debit"',
            'label:has-text("Direct Debit")',
            ':has-text("Direct Debit or when I get a bill")',
            '[value*="direct" i]',
        ]
        
        payment_selected = False
        for selector in payment_selectors:
            try:
                option = page.locator(selector).first
                if option.is_visible(timeout=3000):
                    human_delay(500, 800)
                    option.click()
                    print(f"    ✓ Selected Direct Debit")
                    payment_selected = True
                    break
            except:
                continue
        
        if not payment_selected:
            print(f"    ⚠ Could not click payment option, trying to continue...")
        
        human_delay(2000, 3000)
        
        # Take screenshot before continue
        page.screenshot(path=f"screenshots/sp_{region.replace(' ', '_')}_before_continue.png")
        
        # ============================================
        # STEP 7: Click Continue after payment selection
        # ============================================
        print(f"\n  [STEP 7] Clicking Continue after payment selection...")
        
        continue_selectors = [
            'button:has-text("Continue")',
            'button:has-text("Get quote")',
            'button:has-text("See tariffs")',
            'button:has-text("Next")',
            'button[type="submit"]',
        ]
        
        continue_clicked = False
        for selector in continue_selectors:
            try:
                btn = page.locator(selector).first
                if btn.is_visible(timeout=5000):
                    btn.scroll_into_view_if_needed()
                    human_delay(800, 1200)
                    btn.click()
                    print(f"    ✓ Clicked Continue")
                    continue_clicked = True
                    break
            except:
                continue
        
        if not continue_clicked:
            print(f"    ⚠ Could not find Continue button, trying Enter...")
            page.keyboard.press("Enter")
        
        # IMPORTANT: Wait for tariff options page to load
        print(f"    Waiting for tariff options page...")
        human_delay(5000, 8000)
        
        # ============================================
        # STEP 8: Select cheapest tariff
        # ============================================
        print(f"\n  [STEP 8] Selecting tariff...")
        
        # Wait for tariff cards to appear
        tariff_indicators = [
            'text="Select tariff"',
            'button:has-text("Select tariff")',
            'text=/tariff.*options/i',
            'text=/Your.*tariff/i',
            ':has-text("per year")',
        ]
        
        tariff_page_found = False
        for indicator in tariff_indicators:
            try:
                page.wait_for_selector(indicator, timeout=20000)
                print(f"    ✓ Tariff page loaded (found: {indicator})")
                tariff_page_found = True
                break
            except:
                continue
        
        if not tariff_page_found:
            page.screenshot(path=f"screenshots/sp_{region.replace(' ', '_')}_no_tariffs.png")
            page_text = page.inner_text('body')
            print(f"    ⚠ Tariff page not detected")
            print(f"    Page preview: {page_text[:400]}...")
            # Continue anyway - might be a different layout
        
        human_delay(2000, 3000)
        page.screenshot(path=f"screenshots/sp_{region.replace(' ', '_')}_tariff_options.png")
        
        # Click "Select tariff" button (first one = cheapest)
        select_btn_selectors = [
            'button:has-text("Select tariff")',
            'button:has-text("Select")',
            'a:has-text("Select tariff")',
            '[class*="tariff"] button',
        ]
        
        tariff_selected = False
        for selector in select_btn_selectors:
            try:
                btns = page.locator(selector).all()
                if btns:
                    btns[0].scroll_into_view_if_needed()
                    human_delay(800, 1200)
                    btns[0].click()
                    print(f"    ✓ Selected tariff (clicked first option)")
                    tariff_selected = True
                    break
            except:
                continue
        
        if not tariff_selected:
            print(f"    ⚠ Could not click Select tariff button")
            page.screenshot(path=f"screenshots/sp_{region.replace(' ', '_')}_no_select_btn.png")
        
        # Wait for tariff details page to load
        print(f"    Waiting for tariff details page...")
        human_delay(5000, 8000)
        
        # ============================================
        # STEP 9: Extract rates
        # ============================================
        print(f"\n  [STEP 9] Extracting rates...")
        
        # Wait for details to load
        details_indicators = [
            'text=/Unit rate/i',
            'text=/Standing charge/i',
            'text=/Tariff Details/i',
            'text=/pence per kWh/i',
        ]
        
        for indicator in details_indicators:
            try:
                page.wait_for_selector(indicator, timeout=15000)
                print(f"    ✓ Details page loaded")
                break
            except:
                continue
        
        human_delay(2000, 3000)
        
        # Take screenshot
        page.screenshot(path=f"screenshots/sp_{region.replace(' ', '_')}_details.png")
        
        # Get page text
        page_text = page.inner_text('body')
        
        # Save debug file
        with open(f"debug_sp_{postcode.replace(' ', '_')}.txt", "w", encoding="utf-8") as f:
            f.write(page_text)
        print(f"    📄 Saved debug text")
        
        # Extract rates
        rates = extract_tariff_rates(page_text)
        
        if rates:
            validate_rates(rates)
            result['tariffs'].append(rates)
            print(f"    ✓ Extracted rates:")
            for k, v in rates.items():
                print(f"      {k}: {v}")
        else:
            print(f"    ✗ No rates found")
            result['error'] = "No rates extracted"
        
        result['url'] = page.url
        
    except PlaywrightTimeout as e:
        print(f"    ✗ Timeout: {e}")
        result['error'] = f"Timeout: {str(e)}"
        try:
            page.screenshot(path=f"screenshots/sp_{region.replace(' ', '_')}_timeout.png")
        except:
            pass
    except Exception as e:
        print(f"    ✗ Error: {e}")
        result['error'] = str(e)
        try:
            page.screenshot(path=f"screenshots/sp_{region.replace(' ', '_')}_error.png")
        except:
            pass
    finally:
        if context:
            context.close()
    
    return result, tried_addresses


def scrape_with_retry(browser, postcode: str, region: str, max_retries: int = 3) -> dict:
    """Scrape with exponential backoff retry."""
    tried = set()
    
    for attempt in range(1, max_retries + 1):
        print(f"\n  🔄 Attempt {attempt}/{max_retries}")
        
        result, tried = scrape_sp_tariffs(browser, postcode, region, attempt, tried)
        
        if result.get('tariffs'):
            return result
        
        if attempt < max_retries:
            wait_time = 30 * (2 ** (attempt - 1)) + random.randint(0, 15)
            print(f"\n  ⏳ Waiting {wait_time}s before retry...")
            time.sleep(wait_time)
    
    return result


# ============================================
# MAIN RUNNER
# ============================================

def run_scraper(headless: bool = False, test_postcode: str = None, 
                wait_secs: int = 20, max_retries: int = 3):
    """Main scraper runner."""
    
    results = []
    consecutive_failures = 0  # Track consecutive failures for early abort
    early_abort = False
    
    if test_postcode:
        postcodes = {k: v for k, v in DNO_POSTCODES.items() if v == test_postcode}
        if not postcodes:
            postcodes = {"Test": test_postcode}
    else:
        postcodes = DNO_POSTCODES
    
    with sync_playwright() as p:
        browser = p.firefox.launch(
            headless=headless,
            slow_mo=50,
        )
        print("  🦊 Firefox browser launched")
        
        # Process in batches of 3
        items = list(postcodes.items())
        batches = [items[i:i+3] for i in range(0, len(items), 3)]
        
        for batch_idx, batch in enumerate(batches):
            if early_abort:
                break
                
            print(f"\n{'#'*60}")
            print(f"  BATCH {batch_idx + 1}/{len(batches)} - {len(batch)} regions")
            print('#'*60)
            
            for i, (region, postcode) in enumerate(batch):
                print(f"\n{'='*60}")
                print(f"  SCRAPING: {region} ({postcode}) [{i+1}/{len(batch)}]")
                print('='*60)
                
                result = scrape_with_retry(browser, postcode, region, max_retries)
                results.append(result)
                
                # Save partial results
                if result.get('tariffs'):
                    with open("sp_tariffs_partial.json", "w") as f:
                        json.dump(results, f, indent=2)
                    print(f"  ✓ Success! (Saved)")
                    consecutive_failures = 0  # Reset on success
                else:
                    print(f"  ✗ Failed after {max_retries} attempts")
                    consecutive_failures += 1
                
                # EARLY ABORT: If first 3 regions all fail, scraper is broken
                if consecutive_failures >= 3 and len(results) <= 4:
                    print(f"\n  🛑 EARLY ABORT: First {consecutive_failures} regions failed consecutively")
                    print(f"  → Scraper appears broken on this environment")
                    print(f"  → Run manually on local machine")
                    early_abort = True
                    break
                
                # Wait between regions
                if i < len(batch) - 1:
                    actual_wait = wait_secs + random.randint(-5, 10)
                    print(f"\n  ⏳ Waiting {actual_wait}s before next region...")
                    time.sleep(actual_wait)
            
            if early_abort:
                break
            
            # Longer wait between batches
            if batch_idx < len(batches) - 1:
                batch_wait = 60 + random.randint(0, 30)
                print(f"\n  🔄 Batch complete! Waiting {batch_wait}s...")
                time.sleep(batch_wait)
        
        browser.close()
    
    if early_abort:
        print(f"\n  ⚠️ Scraper aborted early with {len(results)} partial results")
    
    return results


def save_results(results: list):
    """Save to JSON and CSV."""
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # JSON
    json_file = f"sp_tariffs_{timestamp}.json"
    with open(json_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved: {json_file}")
    
    # CSV
    csv_file = f"sp_tariffs_{timestamp}.csv"
    rows = []
    
    for r in results:
        base = {
            "supplier": "scottish_power",
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
                    "exit_fee": t.get("exit_fee", ""),
                    "elec_unit_rate_p": t.get("elec_unit_rate_p"),
                    "elec_standing_p": t.get("elec_standing_p"),
                    "gas_unit_rate_p": t.get("gas_unit_rate_p"),
                    "gas_standing_p": t.get("gas_standing_p"),
                })
                rows.append(row)
        else:
            row = base.copy()
            row["error"] = r.get("error", "No tariffs found")
            rows.append(row)
    
    fieldnames = [
        "supplier", "region", "postcode", "scraped_at", "attempt",
        "tariff_name", "exit_fee",
        "elec_unit_rate_p", "elec_standing_p",
        "gas_unit_rate_p", "gas_standing_p",
        "error"
    ]
    
    with open(csv_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)
    print(f"Saved: {csv_file}")
    
    # Summary
    print("\n" + "="*130)
    print("RESULTS SUMMARY")
    print("="*130)
    print(f"{'Region':<20} {'Tariff':<30} {'Exit Fee':<12} {'Elec Unit':<10} {'Elec SC':<10} {'Gas Unit':<10} {'Gas SC':<10}")
    print("-"*130)
    
    success_count = 0
    for r in results:
        if r.get("tariffs"):
            success_count += 1
            t = r["tariffs"][0]
            tariff_name = t.get('tariff_name', 'N/A')[:29]
            print(f"{r['region']:<20} {tariff_name:<30} {t.get('exit_fee', 'N/A'):<12} {str(t.get('elec_unit_rate_p', 'N/A')):<10} {str(t.get('elec_standing_p', 'N/A')):<10} {str(t.get('gas_unit_rate_p', 'N/A')):<10} {str(t.get('gas_standing_p', 'N/A')):<10}")
        else:
            print(f"{r['region']:<20} {'ERROR':<30} {'':<12} {r.get('error', 'Unknown')[:40]}")
    
    print(f"\nSuccess rate: {success_count}/{len(results)} ({100*success_count/len(results):.1f}%)")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Scottish Power Tariff Scraper v2")
    parser.add_argument("--headless", action="store_true", help="Run headless")
    parser.add_argument("--test", type=str, help="Test single postcode")
    parser.add_argument("--wait", type=int, default=20, help="Seconds between regions (default: 20)")
    parser.add_argument("--retries", type=int, default=3, help="Max retries per region (default: 3)")
    args = parser.parse_args()
    
    os.makedirs("screenshots", exist_ok=True)
    
    print("="*60)
    print("SCOTTISH POWER TARIFF SCRAPER v2")
    print("="*60)
    print("🕵️ Stealth mode with proper waits")
    print("📋 Extracts: Tariff name, exit fee, unit rates, standing charges")
    print(f"⏱️ Wait: ~{args.wait}s between regions, ~60s between batches")
    print(f"🔄 Max retries: {args.retries}")
    print(f"📦 Regions: {len(DNO_POSTCODES)}")
    print("")
    print("Press Ctrl+C to stop")
    
    results = run_scraper(
        headless=args.headless,
        test_postcode=args.test,
        wait_secs=args.wait,
        max_retries=args.retries
    )
    save_results(results)
    
    print("\nDone!")


if __name__ == "__main__":
    main()
