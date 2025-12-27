#!/usr/bin/env python3
"""
OVO Energy Tariff Scraper v1 - STEALTH EDITION
- Rotating user agents
- Randomized browser fingerprints
- Human-like behavior simulation
- Exponential backoff with fresh browser instances
- Per-postcode address start index (for problem areas)
- Extracts tariff name, exit fee, unit rates, standing charges
- Clicks "View details" to get exact rates from modal
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

OVO_QUOTE_URL = "https://products.ovoenergy.com/journey/switch/get-quote"

# Special postcodes that need different starting address indices
POSTCODE_START_INDEX = {
    "BN2 7HQ": 16,   # Brighton - start at higher index
    "AB24 3EN": 5,   # North Scotland
    "G20 6NQ": 5,    # South Scotland
}

# Pool of realistic user agents
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
]

# Viewport variations
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
// Stealth injection
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

console.log('Stealth mode activated');
"""


# ============================================
# HUMAN BEHAVIOR SIMULATION
# ============================================

def human_delay(min_ms=500, max_ms=2000):
    """Random delay following a human-like distribution."""
    delay = random.betavariate(2, 5) * (max_ms - min_ms) + min_ms
    time.sleep(delay / 1000)


def human_typing_delay():
    """Return a realistic typing delay in ms."""
    if random.random() < 0.1:
        return random.randint(200, 400)
    return random.randint(50, 150)


def simulate_mouse_movement(page, target_x, target_y):
    """Simulate natural mouse movement to a target."""
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
    """Perform random scrolling like a human would."""
    scroll_amount = random.randint(100, 300)
    page.mouse.wheel(0, scroll_amount)
    human_delay(300, 800)


# ============================================
# RATE EXTRACTION FROM MODAL
# ============================================

def extract_rates_from_page(page) -> dict:
    """Extract rates from the tariff selection page (without modal)."""
    rates = {}
    
    try:
        page_text = page.inner_text('body')
        
        # Try to find tariff name
        for pattern in [r'(1\s*Year\s*Fixed)', r'(2\s*Year\s*Fixed)', r'(Simpler\s*Energy)']:
            match = re.search(pattern, page_text, re.I)
            if match:
                rates['tariff_name'] = match.group(1).strip()
                break
        
        # Extract exit fee
        exit_match = re.search(r'£(\d+)\s*exit\s*fee\s*per\s*fuel', page_text, re.I)
        if exit_match:
            rates['exit_fee'] = f"£{exit_match.group(1)} per fuel"
        elif 'no exit fee' in page_text.lower():
            rates['exit_fee'] = "£0"
        
        print(f"    Page extraction got: {rates}")
        
    except Exception as e:
        print(f"    Page extraction error: {e}")
    
    return rates


def extract_rates_from_modal(page) -> dict:
    """Extract rates from the tariff details modal."""
    rates = {}
    
    try:
        # Wait for modal to be fully loaded
        human_delay(1000, 2000)
        
        # Get all text from the modal/dialogue
        modal_selectors = [
            '[role="dialog"]',
            '[class*="dialog"]',
            '[class*="modal"]',
            '[class*="je"]',  # OVO's modal class from steps recorder
        ]
        
        modal_text = ""
        for selector in modal_selectors:
            try:
                modal = page.locator(selector).first
                if modal.is_visible(timeout=2000):
                    modal_text = modal.inner_text()
                    break
            except:
                continue
        
        if not modal_text:
            # Fallback: get page text
            modal_text = page.inner_text('body')
        
        print(f"    📄 Modal text length: {len(modal_text)} chars")
        
        # Save for debugging
        with open("debug_ovo_modal.txt", "w", encoding="utf-8") as f:
            f.write(modal_text)
        
        # Extract tariff name (at the top of modal, e.g., "1 Year Fixed")
        tariff_patterns = [
            r'^(1\s*Year\s*Fixed)',
            r'^(2\s*Year\s*Fixed)',
            r'^(Simpler\s*Energy)',
            r'(1\s*Year\s*Fixed(?:\s*[\+\-][^\n]+)?)',
            r'(2\s*Year\s*Fixed(?:\s*[\+\-][^\n]+)?)',
            r'(Simpler\s*Energy)',
        ]
        
        for pattern in tariff_patterns:
            match = re.search(pattern, modal_text, re.I | re.M)
            if match:
                rates['tariff_name'] = match.group(1).strip()
                break
        
        # Extract tariff length
        length_match = re.search(r'Tariff\s*length[:\s]*(\d+)\s*months?', modal_text, re.I)
        if length_match:
            rates['contract_months'] = int(length_match.group(1))
        
        # Extract exit fee (e.g., "£50 per fuel" or "No exit fees")
        exit_patterns = [
            r'Exit\s*fee[:\s]*£(\d+)\s*per\s*fuel',
            r'Exit\s*fee[:\s]*£(\d+)',
            r'£(\d+)\s*(?:per\s*fuel\s*)?exit\s*fee',
        ]
        
        for pattern in exit_patterns:
            match = re.search(pattern, modal_text, re.I)
            if match:
                rates['exit_fee'] = f"£{match.group(1)} per fuel"
                break
        
        if 'exit_fee' not in rates:
            if re.search(r'no\s*exit\s*fee', modal_text, re.I):
                rates['exit_fee'] = "£0"
        
        # Extract electricity rates
        # Pattern: "Unit rate: 26.90p/kWh" or "26.90p per kWh"
        elec_unit_patterns = [
            r'Electricity.*?Unit\s*rate[:\s]*(\d+\.?\d*)\s*p',
            r'Electricity.*?(\d+\.?\d*)\s*p\s*/?\s*kWh',
            r'Unit\s*rate[:\s]*(\d+\.?\d*)\s*p.*?Electricity',
        ]
        
        # Find Electricity section and extract
        elec_section = re.search(r'Electricity(.*?)(?:Gas|Estimated yearly|$)', modal_text, re.I | re.S)
        if elec_section:
            elec_text = elec_section.group(1)
            
            # Unit rate
            unit_match = re.search(r'Unit\s*rate[:\s]*(\d+\.?\d*)\s*p', elec_text, re.I)
            if unit_match:
                rates['elec_unit_rate_p'] = float(unit_match.group(1))
            
            # Standing charge
            standing_match = re.search(r'Standing\s*charge[:\s]*(\d+\.?\d*)\s*p', elec_text, re.I)
            if standing_match:
                rates['elec_standing_p'] = float(standing_match.group(1))
        
        # Extract gas rates
        gas_section = re.search(r'Gas(.*?)(?:Estimated yearly|$)', modal_text, re.I | re.S)
        if gas_section:
            gas_text = gas_section.group(1)
            
            # Unit rate
            unit_match = re.search(r'Unit\s*rate[:\s]*(\d+\.?\d*)\s*p', gas_text, re.I)
            if unit_match:
                rates['gas_unit_rate_p'] = float(unit_match.group(1))
            
            # Standing charge
            standing_match = re.search(r'Standing\s*charge[:\s]*(\d+\.?\d*)\s*p', gas_text, re.I)
            if standing_match:
                rates['gas_standing_p'] = float(standing_match.group(1))
        
        # Fallback patterns if section-based extraction fails
        if 'elec_unit_rate_p' not in rates:
            # Try generic patterns
            all_unit_rates = re.findall(r'(\d+\.?\d*)\s*p\s*/?\s*kWh', modal_text, re.I)
            if len(all_unit_rates) >= 1:
                rates['elec_unit_rate_p'] = float(all_unit_rates[0])
            if len(all_unit_rates) >= 2:
                rates['gas_unit_rate_p'] = float(all_unit_rates[1])
        
        if 'elec_standing_p' not in rates:
            all_standing = re.findall(r'(\d+\.?\d*)\s*p\s*/?\s*day', modal_text, re.I)
            if len(all_standing) >= 1:
                rates['elec_standing_p'] = float(all_standing[0])
            if len(all_standing) >= 2:
                rates['gas_standing_p'] = float(all_standing[1])
        
    except Exception as e:
        print(f"    ✗ Error extracting rates: {e}")
    
    return rates


# ============================================
# BLOCKING DETECTION
# ============================================

def detect_blocking(page) -> tuple:
    """Detect if we've been blocked or hit an error."""
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
# BROWSER CONTEXT
# ============================================

def create_stealth_context(browser):
    """Create a new browser context with stealth settings."""
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
        }
    )
    
    context.add_init_script(STEALTH_SCRIPTS)
    return context, user_agent, viewport


# ============================================
# MAIN SCRAPING LOGIC
# ============================================

def get_valid_addresses(options, start_idx, tried_addresses):
    """Get list of valid residential addresses (starting with number)."""
    valid = []
    skip_words = ['flat', 'apartment', 'floor', 'unit', 'suite', 'apt', 'room', 'basement']
    
    for i in range(start_idx, len(options)):
        if i in tried_addresses:
            continue
        try:
            text = options[i].inner_text().strip()
            # Must start with a number (residential address)
            if not text or not text[0].isdigit():
                continue
            # Skip flats/apartments
            if any(w in text.lower() for w in skip_words):
                continue
            valid.append((i, text))
        except:
            continue
    
    return valid


def scrape_ovo_tariffs(browser, postcode: str, region: str, attempt: int = 1,
                       tried_addresses: set = None) -> tuple:
    """Navigate OVO quote journey and extract tariff data."""
    
    if tried_addresses is None:
        tried_addresses = set()
    
    result = {
        "region": region,
        "postcode": postcode,
        "scraped_at": datetime.now().isoformat(),
        "tariffs": [],
        "attempt": attempt,
    }
    
    context = None
    
    try:
        # Create fresh stealth context
        context, user_agent, viewport = create_stealth_context(browser)
        page = context.new_page()
        
        print(f"    🕵️ Stealth: {viewport['width']}x{viewport['height']}")
        
        # ============================================
        # STEP 1: Load OVO quote page
        # ============================================
        print(f"\n  [STEP 1] Loading OVO website...")
        
        human_delay(1000, 2000)
        page.goto(OVO_QUOTE_URL, timeout=60000, wait_until="domcontentloaded")
        human_delay(2000, 4000)
        
        # Check for blocking
        blocked, block_type = detect_blocking(page)
        if blocked:
            raise Exception(f"Blocked on page load: {block_type}")
        
        print(f"    ✓ Page loaded")
        
        # Handle cookies if they appear
        try:
            cookie_selectors = [
                'button:has-text("Accept")',
                'button:has-text("Accept all")',
                '[id*="accept"]',
                '[class*="accept"]',
            ]
            for selector in cookie_selectors:
                try:
                    btn = page.locator(selector).first
                    if btn.is_visible(timeout=2000):
                        human_delay(500, 1000)
                        btn.click()
                        print(f"    ✓ Accepted cookies")
                        human_delay(500, 1000)
                        break
                except:
                    continue
        except:
            pass
        
        # ============================================
        # STEP 2: Enter postcode
        # ============================================
        print(f"\n  [STEP 2] Entering postcode: {postcode}")
        
        # Find postcode input
        postcode_selectors = [
            'input[name*="postcode" i]',
            'input[placeholder*="postcode" i]',
            'input[id*="postcode" i]',
            'input[type="text"]',
        ]
        
        postcode_input = None
        for selector in postcode_selectors:
            try:
                inp = page.locator(selector).first
                if inp.is_visible(timeout=3000):
                    postcode_input = inp
                    break
            except:
                continue
        
        if not postcode_input:
            raise Exception("Could not find postcode input")
        
        # Click and type postcode
        box = postcode_input.bounding_box()
        if box:
            simulate_mouse_movement(page, box['x'] + box['width']/2, box['y'] + box['height']/2)
        
        human_delay(300, 600)
        postcode_input.click()
        human_delay(200, 400)
        
        # Clear and type
        postcode_input.fill('')
        for char in postcode:
            postcode_input.type(char, delay=human_typing_delay())
        
        human_delay(500, 1000)
        print(f"    ✓ Typed postcode")
        
        # Click "Find Address" button
        find_btn_selectors = [
            'button:has-text("Find Address")',
            'button:has-text("Find address")',
            'button:has-text("Search")',
            'button[type="submit"]',
        ]
        
        for selector in find_btn_selectors:
            try:
                btn = page.locator(selector).first
                if btn.is_visible(timeout=2000):
                    human_delay(300, 600)
                    btn.click()
                    print(f"    ✓ Clicked Find Address")
                    break
            except:
                continue
        
        human_delay(2000, 4000)
        
        # ============================================
        # STEP 3: Select address from dropdown (KEYBOARD METHOD)
        # ============================================
        print(f"\n  [STEP 3] Selecting address...")
        
        # Get starting index for this postcode
        start_idx = POSTCODE_START_INDEX.get(postcode, 1)
        
        # Wait for address dropdown to appear
        human_delay(2000, 3000)
        
        # Look for the dropdown trigger - OVO shows "X Addresses found"
        dropdown_trigger = None
        trigger_selectors = [
            'text=/\\d+\\s*Addresses found/i',
            '[class*="_select_"]',
            '#address-select-field',
        ]
        
        for selector in trigger_selectors:
            try:
                trigger = page.locator(selector).first
                if trigger.is_visible(timeout=5000):
                    dropdown_trigger = trigger
                    print(f"    ✓ Found dropdown trigger")
                    break
            except:
                continue
        
        if not dropdown_trigger:
            page.screenshot(path=f"screenshots/ovo_{region.replace(' ', '_')}_dropdown_debug.png")
            raise Exception("Could not find address dropdown trigger")
        
        # Click to open dropdown
        human_delay(500, 800)
        dropdown_trigger.click()
        human_delay(1500, 2000)
        
        # Use KEYBOARD navigation - it's more reliable than clicking
        target_idx = start_idx
        while target_idx in tried_addresses:
            target_idx += 1
        
        tried_addresses.add(target_idx)
        print(f"    Selecting address #{target_idx} via keyboard...")
        
        # Arrow down to the desired option (index 0 = first address after header)
        for i in range(target_idx):
            page.keyboard.press("ArrowDown")
            human_delay(150, 250)
        
        # Small pause then press Enter
        human_delay(300, 500)
        page.keyboard.press("Enter")
        print(f"    ✓ Selected address via keyboard")
        
        # Wait for page to process the selection
        human_delay(2500, 4000)
        
        # Check if we need to click a Next/Continue button after address
        print(f"    Checking for Next button...")
        try:
            next_after_addr = page.locator('button:has-text("Next"), button:has-text("Continue")').first
            if next_after_addr.is_visible(timeout=3000):
                human_delay(800, 1200)
                next_after_addr.click()
                print(f"    ✓ Clicked Next after address selection")
                human_delay(2500, 3500)
        except:
            print(f"    (No Next button needed - auto-advanced)")
        
        # Take screenshot to see where we are
        page.screenshot(path=f"screenshots/ovo_{region.replace(' ', '_')}_after_address.png")
        
        # Check for any popups (already customer, business meter, etc.)
        page_text = page.inner_text('body').lower()
        if 'already supply' in page_text or 'existing customer' in page_text:
            print(f"    ⚠ Already customer popup - trying next address...")
            try:
                page.locator('button:has-text("Close")').first.click()
            except:
                pass
            raise Exception("Already customer - need different address")
        
        # ============================================
        # STEP 4: Check for meter issues & Energy usage
        # ============================================
        print(f"\n  [STEP 4] Checking meter setup...")
        
        # Wait for next page to fully load
        print(f"    Waiting for page to load...")
        human_delay(3000, 4000)
        
        # Take screenshot to see current state
        page.screenshot(path=f"screenshots/ovo_{region.replace(' ', '_')}_meter_check.png")
        
        page_text = page.inner_text('body').lower()
        
        # Check for business meter or unsupported meter errors
        meter_errors = [
            'business meter',
            'unable to support your meter setup',
            "can't give you a quote",
            'unable to give you a quote',
            'multi-meter',
        ]
        
        max_address_retries = 5
        address_retry_count = 0
        
        while any(err in page_text for err in meter_errors) and address_retry_count < max_address_retries:
            address_retry_count += 1
            print(f"    ⚠ Meter issue detected - clicking Back to try another address (attempt {address_retry_count})...")
            
            # Click Back button
            try:
                back_btn = page.locator('button:has-text("Back")').first
                if back_btn.is_visible(timeout=3000):
                    back_btn.click()
                    human_delay(1500, 2500)
            except Exception as e:
                print(f"    ✗ Could not click Back: {e}")
                raise Exception("Meter issue - could not go back")
            
            # Re-open address dropdown and select next address via KEYBOARD
            try:
                # Find and click the address dropdown trigger again
                dropdown_trigger = None
                for selector in ['text=/\\d+\\s*Addresses found/i', '[class*="_select_"]', '#address-select-field']:
                    try:
                        trigger = page.locator(selector).first
                        if trigger.is_visible(timeout=3000):
                            dropdown_trigger = trigger
                            break
                    except:
                        continue
                
                if dropdown_trigger:
                    human_delay(800, 1200)
                    dropdown_trigger.click()
                    human_delay(2000, 2500)
                    
                    # Use keyboard to select next address
                    target_idx = start_idx + address_retry_count
                    while target_idx in tried_addresses:
                        target_idx += 1
                    
                    tried_addresses.add(target_idx)
                    print(f"    Trying address #{target_idx} via keyboard...")
                    
                    for i in range(target_idx):
                        page.keyboard.press("ArrowDown")
                        human_delay(150, 250)
                    
                    human_delay(400, 600)
                    page.keyboard.press("Enter")
                    print(f"    ✓ Selected new address")
                    
                    # IMPORTANT: Wait for page to fully process new address
                    print(f"    Waiting for page to load...")
                    human_delay(4000, 5000)
                    
                    # Check if we need to click Next after address selection
                    try:
                        next_btn = page.locator('button:has-text("Next"), button:has-text("Continue")').first
                        if next_btn.is_visible(timeout=2000):
                            human_delay(800, 1200)
                            next_btn.click()
                            print(f"    ✓ Clicked Next")
                            human_delay(3000, 4000)
                    except:
                        pass
                    
                    # Take screenshot to see where we are
                    page.screenshot(path=f"screenshots/ovo_{region.replace(' ', '_')}_retry_{address_retry_count}.png")
                    
                    # Now check page text for meter errors
                    page_text = page.inner_text('body').lower()
                else:
                    raise Exception("Could not find address dropdown after going back")
                    
            except Exception as e:
                raise Exception(f"Failed to select new address: {e}")
        
        if any(err in page_text for err in meter_errors):
            raise Exception(f"All addresses have meter issues after {address_retry_count} attempts")
        
        print(f"    ✓ Meter setup OK")
        
        # ============================================
        # STEP 5: Energy usage page - use defaults
        # ============================================
        print(f"\n  [STEP 5] Energy usage page...")
        
        # Wait for energy usage page to load
        human_delay(2000, 3000)
        
        # Check if we're on the energy usage page
        page_text = page.inner_text('body').lower()
        
        # Look for indicators we're on energy usage page
        if 'energy usage' in page_text or 'how many bedrooms' in page_text or 'how much energy' in page_text:
            print(f"    ✓ On energy usage page")
            
            # Take screenshot
            page.screenshot(path=f"screenshots/ovo_{region.replace(' ', '_')}_energy_usage.png")
            
            # The defaults should be fine (No, 1-2 bedrooms), just click Next
            human_delay(1500, 2500)
            
            # Find and click Next button
            next_clicked = False
            next_btn_selectors = [
                'button:has-text("Next")',
                'button:has-text("Continue")',
                'button:has-text("Get quotes")',
                'button:has-text("See plans")',
                '[class*="button"]:has-text("Next")',
            ]
            
            for selector in next_btn_selectors:
                try:
                    btn = page.locator(selector).first
                    if btn.is_visible(timeout=3000):
                        # Scroll button into view
                        btn.scroll_into_view_if_needed()
                        human_delay(500, 1000)
                        btn.click()
                        next_clicked = True
                        print(f"    ✓ Clicked Next button")
                        break
                except Exception as e:
                    continue
            
            if not next_clicked:
                print(f"    ⚠ Could not find Next button, trying keyboard...")
                page.keyboard.press("Tab")
                human_delay(300, 500)
                page.keyboard.press("Tab")
                human_delay(300, 500)
                page.keyboard.press("Enter")
                print(f"    ✓ Pressed Enter")
            
            # Wait for transition to tariff page
            print(f"    Waiting for tariff page to load...")
            human_delay(4000, 6000)
        else:
            print(f"    ⚠ Not on expected energy usage page")
            print(f"    Page contains: {page_text[:200]}...")
            page.screenshot(path=f"screenshots/ovo_{region.replace(' ', '_')}_unexpected_page.png")
        
        # Take screenshot before tariff page
        page.screenshot(path=f"screenshots/ovo_{region.replace(' ', '_')}_before_tariffs.png")
        
        # ============================================
        # STEP 6: Tariff selection page
        # ============================================
        print(f"\n  [STEP 6] Tariff selection page...")
        
        # Wait for tariffs to load - try multiple indicators
        tariff_page_found = False
        tariff_indicators = [
            'text="Select a tariff"',
            'text="Choose a tariff"',
            'text="1 Year Fixed"',
            'text="2 Year Fixed"',
            'text="Simpler Energy"',
            'text=/Year Fixed/i',
            ':has-text("View details")',
        ]
        
        for indicator in tariff_indicators:
            try:
                page.wait_for_selector(indicator, timeout=8000)
                print(f"    ✓ Tariff page loaded (found: {indicator})")
                tariff_page_found = True
                break
            except:
                continue
        
        if not tariff_page_found:
            # Check what page we're actually on
            page_text = page.inner_text('body')
            print(f"    ⚠ Tariff page not detected")
            print(f"    Page preview: {page_text[:300]}...")
            page.screenshot(path=f"screenshots/ovo_{region.replace(' ', '_')}_tariff_missing.png")
            raise Exception("Could not find tariff selection page")
        
        human_delay(1500, 2500)
        
        # Take screenshot of tariffs
        page.screenshot(path=f"screenshots/ovo_{region.replace(' ', '_')}_tariffs.png")
        
        # Find "View details" links for each tariff
        view_details_selectors = [
            'a:has-text("View details")',
            'button:has-text("View details")',
            '[class*="_inline_"]:has-text("View details")',
            'text="View details"',
        ]
        
        view_links = []
        for selector in view_details_selectors:
            try:
                links = page.locator(selector).all()
                if links and len(links) > 0:
                    view_links = links
                    print(f"    Found {len(links)} 'View details' links")
                    break
            except:
                continue
        
        if not view_links:
            print(f"    ⚠ No View details links found, trying to extract from page directly...")
            page.screenshot(path=f"screenshots/ovo_{region.replace(' ', '_')}_no_view_details.png")
            # Try to extract rates from the main page instead
            rates = extract_rates_from_page(page)
            if rates:
                result['tariffs'].append(rates)
        else:
            print(f"    Found {len(view_links)} tariffs")
        
        # ============================================
        # STEP 7: Click each "View details" and extract rates
        # ============================================
        print(f"\n  [STEP 7] Extracting tariff details...")
        
        if view_links:
            # Only extract the FIRST tariff (cheapest one on left)
            link = view_links[0]
            try:
                print(f"\n    Extracting first tariff:")
                
                # Try clicking View details
                human_delay(800, 1200)
                try:
                    link.scroll_into_view_if_needed(timeout=3000)
                    human_delay(300, 500)
                    link.click(timeout=5000)
                    print(f"      ✓ Clicked View details")
                except Exception as click_err:
                    print(f"      Click failed: {click_err}")
                    print(f"      Trying Tab navigation...")
                    # Use Tab to navigate to link and Enter to click
                    page.keyboard.press("Tab")
                    human_delay(200, 400)
                    page.keyboard.press("Enter")
                
                human_delay(2000, 3000)
                
                # Scroll inside modal to see gas rates
                try:
                    modal = page.locator('[role="dialog"]').first
                    if modal.is_visible(timeout=2000):
                        # Scroll down inside the modal
                        modal.evaluate('(el) => el.scrollTop = el.scrollHeight')
                        human_delay(500, 1000)
                except:
                    pass
                
                # Extract rates from modal
                rates = extract_rates_from_modal(page)
                
                if rates:
                    result['tariffs'].append(rates)
                    print(f"      ✓ Extracted: {rates.get('tariff_name', 'Unknown')}")
                    for k, v in rates.items():
                        if k != 'tariff_name':
                            print(f"        {k}: {v}")
                
                # Close modal (press Escape - most reliable)
                page.keyboard.press("Escape")
                human_delay(800, 1200)
                
            except Exception as e:
                print(f"      ✗ Error: {e}")
                # Try to close any open modal
                try:
                    page.keyboard.press("Escape")
                except:
                    pass
        
        result['url'] = page.url
        
    except Exception as e:
        result['error'] = str(e)
        print(f"\n    ✗ ERROR: {e}")
        try:
            page.screenshot(path=f"screenshots/ovo_{region.replace(' ', '_')}_error.png")
        except:
            pass
    
    finally:
        if context:
            context.close()
    
    return result, tried_addresses


def scrape_with_retry(browser, postcode: str, region: str, max_attempts: int = 3) -> dict:
    """Scrape with retry logic."""
    tried = set()
    
    for attempt in range(1, max_attempts + 1):
        print(f"\n  🔄 Attempt {attempt}/{max_attempts}")
        
        result, tried = scrape_ovo_tariffs(browser, postcode, region, attempt, tried)
        
        if result.get('tariffs'):
            return result
        
        if attempt < max_attempts:
            wait = 30 * (2 ** (attempt - 1)) + random.randint(0, 30)
            print(f"\n  ⏳ Waiting {wait}s before retry...")
            time.sleep(wait)
    
    return result


# ============================================
# MAIN RUNNER
# ============================================

def run_scraper(headless: bool = False, test_postcode: str = None,
                wait_secs: int = 25, max_retries: int = 3):
    """Main scraper with enhanced anti-detection."""
    
    results = []
    
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
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-accelerated-2d-canvas',
                '--no-first-run',
                '--disable-gpu',
            ]
        )
        print("  🌐 Browser launched with stealth mode")
        
        # Process in batches
        items = list(postcodes.items())
        batches = [items[i:i+3] for i in range(0, len(items), 3)]
        
        for batch_idx, batch in enumerate(batches):
            print(f"\n{'#'*60}")
            print(f"  BATCH {batch_idx + 1}/{len(batches)} - {len(batch)} regions")
            print('#'*60)
            
            for i, (region, postcode) in enumerate(batch):
                print(f"\n{'='*60}")
                print(f"  SCRAPING: {region} ({postcode})")
                print('='*60)
                
                result = scrape_with_retry(browser, postcode, region, max_retries)
                results.append(result)
                
                # Save partial results
                if result.get('tariffs'):
                    with open("ovo_tariffs_partial.json", "w") as f:
                        json.dump(results, f, indent=2)
                    print(f"  ✓ Success! (Saved)")
                else:
                    print(f"  ✗ Failed after {max_retries} attempts")
                
                # Wait between regions
                if i < len(batch) - 1:
                    actual_wait = wait_secs + random.randint(-5, 10)
                    print(f"\n  ⏳ Waiting {actual_wait}s before next region...")
                    time.sleep(actual_wait)
            
            # Longer wait between batches
            if batch_idx < len(batches) - 1:
                batch_wait = 90 + random.randint(0, 30)
                print(f"\n  🔄 Batch complete! Waiting {batch_wait}s...")
                time.sleep(batch_wait)
        
        browser.close()
    
    return results


def save_results(results: list):
    """Save to JSON and CSV."""
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # JSON
    json_file = f"ovo_tariffs_{timestamp}.json"
    with open(json_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved: {json_file}")
    
    # CSV
    csv_file = f"ovo_tariffs_{timestamp}.csv"
    rows = []
    
    for r in results:
        base = {
            "supplier": "ovo",
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
                    "contract_months": t.get("contract_months"),
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
        "tariff_name", "contract_months", "exit_fee",
        "elec_unit_rate_p", "elec_standing_p",
        "gas_unit_rate_p", "gas_standing_p", "error"
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
    print(f"{'Region':<20} {'Tariff':<20} {'Exit Fee':<15} {'Elec Unit':<12} {'Elec SC':<10} {'Gas Unit':<12} {'Gas SC':<10}")
    print("-"*130)
    
    success_count = 0
    for r in results:
        if r.get("tariffs"):
            success_count += 1
            for t in r["tariffs"]:
                print(f"{r['region']:<20} {t.get('tariff_name', 'N/A')[:19]:<20} {t.get('exit_fee', 'N/A'):<15} {t.get('elec_unit_rate_p', 'N/A'):<12} {t.get('elec_standing_p', 'N/A'):<10} {t.get('gas_unit_rate_p', 'N/A'):<12} {t.get('gas_standing_p', 'N/A'):<10}")
        else:
            print(f"{r['region']:<20} {'ERROR':<20} {'':<15} {r.get('error', 'Unknown')[:50]}")
    
    print(f"\nSuccess rate: {success_count}/{len(results)} ({100*success_count/len(results):.1f}%)")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="OVO Energy Tariff Scraper v1")
    parser.add_argument("--headless", action="store_true", help="Run headless")
    parser.add_argument("--test", type=str, help="Test single postcode")
    parser.add_argument("--wait", type=int, default=25, help="Seconds between regions (default: 25)")
    parser.add_argument("--retries", type=int, default=3, help="Max retries per region (default: 3)")
    args = parser.parse_args()
    
    os.makedirs("screenshots", exist_ok=True)
    
    print("="*60)
    print("OVO ENERGY TARIFF SCRAPER v1")
    print("="*60)
    print("🕵️ Anti-detection: Rotating fingerprints, human simulation")
    print("📋 Extracts: Tariff name, exit fee, unit rates, standing charges")
    print(f"⏱️ Wait: ~{args.wait}s between regions, ~90s between batches")
    print(f"🔄 Max retries: {args.retries}")
    print()
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
