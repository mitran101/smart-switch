#!/usr/bin/env python3
"""
British Gas Tariff Scraper v10 - STEALTH EDITION
- Rotating user agents
- Randomized browser fingerprints
- Human-like behavior simulation
- Exponential backoff with fresh browser instances
- Network error recovery with full restart
- Per-postcode address start index (for problem areas)
- Relaxed validation (payment method not required)
- Now extracts tariff name and exit fee
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

BG_QUOTE_URL = "https://www.britishgas.co.uk/energy/gas-and-electricity.html"

# Special postcodes that need different starting address indices
# (e.g., coastal areas where first addresses are often electricity-only flats)
POSTCODE_START_INDEX = {
    "BN2 7HQ": 16,   # Brighton - start at 36 Marine Drive area
    "AB24 3EN": 5,   # North Scotland - start from 4th address
    "G20 6NQ": 5,    # South Scotland - start from 4th address
}

# Pool of realistic user agents (Chrome/Edge on Windows, updated versions)
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
]

# Viewport variations (common desktop resolutions)
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
// Comprehensive stealth injection

// 1. Override webdriver
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

// 2. Override plugins (make it look like a real browser)
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

// 3. Override languages
Object.defineProperty(navigator, 'languages', { get: () => ['en-GB', 'en-US', 'en'] });

// 4. Override platform
Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });

// 5. Override hardware concurrency (randomize a bit)
Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });

// 6. Override device memory
Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });

// 7. Fix permissions API
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) => (
    parameters.name === 'notifications' ?
        Promise.resolve({ state: Notification.permission }) :
        originalQuery(parameters)
);

// 8. Override chrome property
window.chrome = {
    runtime: {},
    loadTimes: function() {},
    csi: function() {},
    app: {}
};

// 9. Override connection (make it look like real network)
Object.defineProperty(navigator, 'connection', {
    get: () => ({
        effectiveType: '4g',
        rtt: 50,
        downlink: 10,
        saveData: false
    })
});

// 10. Canvas fingerprint noise (subtle variation)
const originalGetContext = HTMLCanvasElement.prototype.getContext;
HTMLCanvasElement.prototype.getContext = function(type, attributes) {
    const context = originalGetContext.call(this, type, attributes);
    if (type === '2d') {
        const originalFillText = context.fillText;
        context.fillText = function(...args) {
            // Add tiny invisible noise
            args[1] += Math.random() * 0.001;
            return originalFillText.apply(this, args);
        };
    }
    return context;
};

// 11. WebGL vendor/renderer (common Intel GPU)
const getParameter = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function(parameter) {
    if (parameter === 37445) return 'Intel Inc.';
    if (parameter === 37446) return 'Intel Iris OpenGL Engine';
    return getParameter.call(this, parameter);
};

// 12. Fix iframe contentWindow
try {
    Object.defineProperty(HTMLIFrameElement.prototype, 'contentWindow', {
        get: function() {
            return window;
        }
    });
} catch(e) {}

console.log('Stealth mode activated');
"""


# ============================================
# HUMAN BEHAVIOR SIMULATION
# ============================================

def human_delay(min_ms=500, max_ms=2000):
    """Random delay following a more human-like distribution."""
    # Use beta distribution for more realistic timing (most actions are quick, some take longer)
    delay = random.betavariate(2, 5) * (max_ms - min_ms) + min_ms
    time.sleep(delay / 1000)


def human_typing_delay():
    """Return a realistic typing delay in ms."""
    # Most keystrokes are 50-150ms, occasionally slower for 'thinking'
    if random.random() < 0.1:
        return random.randint(200, 400)  # Occasional pause
    return random.randint(50, 150)


def simulate_mouse_movement(page, target_x, target_y):
    """Simulate natural mouse movement to a target."""
    # Get current position (assume center if unknown)
    steps = random.randint(5, 15)
    
    current_x = random.randint(400, 600)
    current_y = random.randint(300, 400)
    
    for i in range(steps):
        # Add some curve/wobble to the movement
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
# RATE EXTRACTION
# ============================================

def extract_tariff_rates(page_text: str) -> dict:
    """Extract rates by looking for section headers."""
    rates = {}
    
    gas_match = re.search(
        r'Gas tariff costs.*?Unit rate\s*(\d+\.?\d*)\s*p\s*per\s*kWh.*?Standing charge\s*(\d+\.?\d*)\s*p\s*per\s*day',
        page_text, re.I | re.S
    )
    if gas_match:
        rates['gas_unit_rate_p'] = float(gas_match.group(1))
        rates['gas_standing_p'] = float(gas_match.group(2))
    
    elec_match = re.search(
        r'Electricity tariff costs.*?Unit rate\s*(\d+\.?\d*)\s*p\s*per\s*kWh.*?Standing charge\s*(\d+\.?\d*)\s*p\s*per\s*day',
        page_text, re.I | re.S
    )
    if elec_match:
        rates['elec_unit_rate_p'] = float(elec_match.group(1))
        rates['elec_standing_p'] = float(elec_match.group(2))
    
    # Extract tariff name (e.g., "Fixed Tariff Dec26 v3")
    tariff_patterns = [
        r'(Fixed Tariff\s+[A-Za-z]+\d+\s*v?\d*)',  # "Fixed Tariff Dec26 v3"
        r'(Fixed Tariff\s+[A-Za-z]+\s+\d{4}\s*v?\d*)',  # "Fixed Tariff December 2026 v3"
        r'((?:Fixed|Variable|Flex|Standard)\s+Tariff[^\n£]*?)(?=\s*(?:Estimated|Fixed energy|£))',
    ]
    
    for pattern in tariff_patterns:
        tariff_match = re.search(pattern, page_text, re.I)
        if tariff_match:
            tariff_name = tariff_match.group(1).strip()
            tariff_name = re.sub(r'\s+', ' ', tariff_name).strip()
            if len(tariff_name) > 5:
                rates['tariff_name'] = tariff_name
                break
    
    # Extract exit fee (e.g., "Exit fee: £50 per fuel")
    exit_fee_patterns = [
        r'Exit\s*fee[:\s]*£(\d+(?:\.\d+)?)\s*(per\s*fuel)?',  # "Exit fee: £50 per fuel"
        r'Exit\s*fee[:\s]+(\d+(?:\.\d+)?)\s*(per\s*fuel)?',   # "Exit fee: 50 per fuel"
    ]
    
    for pattern in exit_fee_patterns:
        exit_match = re.search(pattern, page_text, re.I)
        if exit_match:
            amount = exit_match.group(1)
            per_fuel = exit_match.group(2)
            if per_fuel:
                rates['exit_fee'] = f"£{amount} per fuel"
            else:
                rates['exit_fee'] = f"£{amount}"
            break
    
    # Check for "no exit fee" scenarios
    if 'exit_fee' not in rates:
        if re.search(r'no\s*exit\s*fee', page_text, re.I):
            rates['exit_fee'] = "£0"
    
    return rates


# ============================================
# NETWORK ERROR DETECTION
# ============================================

def detect_blocking(page) -> tuple[bool, str]:
    """Detect if we've been blocked or hit a network error."""
    try:
        page_text = page.inner_text('body').lower()
        
        # Check for various blocking signals
        if 'network error' in page_text:
            return True, "network_error"
        if 'access denied' in page_text:
            return True, "access_denied"
        if 'too many requests' in page_text:
            return True, "rate_limited"
        if 'captcha' in page_text or 'verify you are human' in page_text:
            return True, "captcha"
        if 'error' in page_text and 'undefined' in page_text:
            return True, "api_error"
        if 'something went wrong' in page_text:
            return True, "generic_error"
            
        return False, ""
    except:
        return False, ""


# ============================================
# MAIN SCRAPING LOGIC
# ============================================

def create_stealth_context(browser, use_channel=False):
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
        reduced_motion="no-preference",
        has_touch=False,
        is_mobile=False,
        device_scale_factor=1,
        # Add extra HTTP headers
        extra_http_headers={
            "Accept-Language": "en-GB,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
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
    
    # Inject stealth scripts
    context.add_init_script(STEALTH_SCRIPTS)
    
    return context, user_agent, viewport


def scrape_bg_tariffs(browser, postcode: str, region: str, attempt: int = 1) -> dict:
    """Navigate BG quote journey with enhanced stealth."""
    
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
        
        print(f"    🕵️ Stealth: {viewport['width']}x{viewport['height']} | {user_agent[:50]}...")
        
        # ============================================
        # STEP 1: Load BG homepage with human-like behavior
        # ============================================
        print(f"\n  [STEP 1] Loading British Gas website...")
        
        # Random initial delay (human wouldn't click instantly)
        human_delay(1000, 3000)
        
        page.goto(BG_QUOTE_URL, timeout=60000, wait_until="domcontentloaded")
        human_delay(2000, 4000)
        
        # Check for blocking
        blocked, block_type = detect_blocking(page)
        if blocked:
            raise Exception(f"Blocked on page load: {block_type}")
        
        print(f"    ✓ Page loaded")
        
        # Random scroll to look human
        random_scroll(page)
        
        # Handle cookies if they appear
        try:
            cookie_btn = page.locator('#onetrust-accept-btn-handler')
            if cookie_btn.is_visible(timeout=3000):
                human_delay(500, 1500)
                cookie_btn.click()
                print(f"    ✓ Accepted cookies")
                human_delay(800, 1500)
        except:
            pass
        
        # ============================================
        # STEP 2: Enter postcode with human-like typing
        # ============================================
        print(f"\n  [STEP 2] Entering postcode: {postcode}")
        
        postcode_input = page.locator('input[name="postcode"], input[placeholder*="postcode" i]').first
        postcode_input.wait_for(state="visible", timeout=10000)
        
        # Move mouse to input field
        box = postcode_input.bounding_box()
        if box:
            simulate_mouse_movement(page, box['x'] + box['width']/2, box['y'] + box['height']/2)
        
        human_delay(300, 800)
        postcode_input.click()
        human_delay(200, 500)
        
        # Type like a human
        for char in postcode:
            postcode_input.type(char, delay=human_typing_delay())
        
        human_delay(500, 1200)
        print(f"    ✓ Typed postcode")
        
        # Press Enter
        postcode_input.press("Enter")
        print(f"    Waiting for address dropdown...")
        
        # Check for blocking
        human_delay(2000, 4000)
        blocked, block_type = detect_blocking(page)
        if blocked:
            raise Exception(f"Blocked after postcode entry: {block_type}")
        
        # Wait for address dropdown
        page.locator('#address-select').wait_for(state="visible", timeout=20000)
        human_delay(800, 1500)
        print(f"    ✓ Address dropdown appeared")
        
        # ============================================
        # STEP 3 & 4: Select address
        # ============================================
        print(f"\n  [STEP 3] Selecting address from dropdown...")
        
        address_select = page.locator('#address-select')
        options = address_select.locator('option').all()
        
        # Check if this postcode has a special starting index
        start_idx = POSTCODE_START_INDEX.get(postcode, 2)
        if start_idx > 2:
            print(f"    ⚡ Using special start index {start_idx} for {postcode}")
        
        # Skip flats/apartments
        skip_words = ['flat', 'floor', 'apartment', 'apt', 'unit', 'suite', 'room', 'basement', '1st', '2nd', '3rd', '4th', '5th']
        good_indices = []
        for idx in range(start_idx, len(options)):
            try:
                text = options[idx].inner_text().lower()
                if not any(word in text for word in skip_words):
                    good_indices.append(idx)
            except:
                continue
        
        if not good_indices:
            good_indices = list(range(start_idx, min(len(options), start_idx + 10)))
            print(f"    No house addresses found, trying all...")
        else:
            print(f"    Found {len(good_indices)} house addresses")
        
        address_worked = False
        
        for addr_index in good_indices[:6]:
            print(f"\n    Trying address #{addr_index}...")
            
            human_delay(500, 1200)
            address_select.select_option(index=addr_index)
            human_delay(1000, 2000)
            
            # Click "Choose this address"
            print(f"  [STEP 4] Clicking 'Choose this address'...")
            
            button_selectors = [
                'button:has-text("Choose this address")',
                'text="Choose this address"',
                '.cta.submit',
            ]
            
            button_clicked = False
            for selector in button_selectors:
                try:
                    btn = page.locator(selector).first
                    if btn.is_visible(timeout=2000):
                        btn.scroll_into_view_if_needed()
                        human_delay(300, 700)
                        btn.click()
                        button_clicked = True
                        break
                except:
                    continue
            
            if not button_clicked:
                print(f"    ✗ Could not click 'Choose this address'")
                continue
            
            human_delay(2000, 4000)
            
            # Check for blocking
            blocked, block_type = detect_blocking(page)
            if blocked:
                print(f"    ✗ Blocked: {block_type}")
                page.go_back()
                human_delay(2000, 3000)
                address_select = page.locator('#address-select')
                address_select.wait_for(state="visible", timeout=10000)
                continue
            
            # Check for valid page - just need fuel question and usage question
            # (payment method may or may not be visible)
            valid_page = False
            try:
                fuel_question = page.locator('text="What fuel do you need?"')
                usage_question = page.locator('text="How much energy do you use a year?"')
                
                if (fuel_question.is_visible(timeout=2000) and 
                    usage_question.is_visible(timeout=1000)):
                    valid_page = True
                    print(f"    ✓ Address #{addr_index} shows full quote form!")
            except:
                pass
            
            if valid_page:
                address_worked = True
                break
            else:
                print(f"    ✗ Address #{addr_index} doesn't show full form - going back...")
                page.go_back()
                human_delay(1500, 2500)
                address_select = page.locator('#address-select')
                address_select.wait_for(state="visible", timeout=10000)
                continue
        
        if not address_worked:
            raise Exception("Could not find a valid address with Gas & Electricity")
        
        # Make sure Gas & electricity is selected
        try:
            gas_elec = page.locator('text="Gas & electricity"').first
            if gas_elec.is_visible(timeout=2000):
                human_delay(300, 600)
                gas_elec.click()
                print(f"    ✓ Selected 'Gas & electricity'")
                human_delay(300, 600)
        except:
            pass
        
        # ============================================
        # STEP 5: Click "Low" usage option
        # ============================================
        print(f"\n  [STEP 5] Selecting 'Low' usage...")
        random_scroll(page)
        
        low_clicked = False
        try:
            low_label = page.locator('label:has-text("Low")')
            if low_label.is_visible(timeout=3000):
                human_delay(400, 900)
                low_label.click()
                low_clicked = True
                print(f"    ✓ Clicked 'Low'")
        except:
            pass
        
        if not low_clicked:
            try:
                low_text = page.locator('text="Low"').first
                if low_text.is_visible(timeout=3000):
                    human_delay(400, 900)
                    low_text.click()
                    low_clicked = True
                    print(f"    ✓ Clicked 'Low'")
            except:
                pass
        
        human_delay(800, 1500)
        
        # ============================================
        # STEP 6: Click "Continue"
        # ============================================
        print(f"\n  [STEP 6] Looking for 'Continue' button...")
        
        # Scroll down
        page.mouse.wheel(0, random.randint(300, 500))
        human_delay(800, 1500)
        
        continue_selectors = [
            'button:has-text("Continue")',
            'text="Continue"',
            '.cta.submit:has-text("Continue")',
            'button.cta',
        ]
        
        continue_clicked = False
        for selector in continue_selectors:
            try:
                btn = page.locator(selector).first
                if btn.is_visible(timeout=3000):
                    btn.scroll_into_view_if_needed()
                    human_delay(400, 800)
                    btn.click()
                    continue_clicked = True
                    print(f"    ✓ Clicked Continue")
                    break
            except:
                continue
        
        if not continue_clicked:
            page.screenshot(path=f"screenshots/{region.replace(' ', '_')}_debug_continue.png")
            raise Exception("Could not find Continue button")
        
        # Wait for results
        print(f"    Waiting for tariff results...")
        human_delay(3000, 5000)
        
        # Check for blocking
        blocked, block_type = detect_blocking(page)
        if blocked:
            raise Exception(f"Blocked after Continue: {block_type}")
        
        # Handle email popup
        try:
            no_thanks = page.locator('text="No thanks. Take me to my quote"')
            if no_thanks.is_visible(timeout=3000):
                print(f"    Found email popup - clicking 'No thanks'...")
                human_delay(500, 1200)
                no_thanks.click()
                human_delay(2000, 4000)
        except:
            pass
        
        try:
            page.locator('text="See tariff details"').first.wait_for(state="visible", timeout=15000)
            print(f"    ✓ Tariff results appeared")
        except:
            print(f"    ⚠ Tariff details not found yet...")
        
        # ============================================
        # STEP 7: Click "See tariff details"
        # ============================================
        print(f"\n  [STEP 7] Clicking 'See tariff details'...")
        
        try:
            see_details = page.locator('text="See tariff details"').first
            see_details.wait_for(state="visible", timeout=10000)
            see_details.scroll_into_view_if_needed()
            human_delay(400, 900)
            see_details.click()
            print(f"    ✓ Clicked 'See tariff details'")
        except Exception as e:
            print(f"    ✗ Could not click 'See tariff details': {e}")
        
        human_delay(2000, 3500)
        
        try:
            page.locator('text="Gas tariff costs"').first.wait_for(state="visible", timeout=10000)
            print(f"    ✓ Tariff details expanded")
        except:
            print(f"    ⚠ Could not confirm expansion, trying anyway...")
        
        page.screenshot(path=f"screenshots/{region.replace(' ', '_')}_final.png", full_page=True)
        
        # ============================================
        # STEP 8: Extract rates
        # ============================================
        print(f"\n  [STEP 8] Extracting tariff rates...")
        
        page_text = page.inner_text('body')
        rates = extract_tariff_rates(page_text)
        
        if rates.get('gas_unit_rate_p') and rates.get('elec_unit_rate_p'):
            result['tariffs'].append(rates)
            print(f"    ✓ EXTRACTED RATES:")
            print(f"      Gas:  {rates['gas_unit_rate_p']}p/kWh | {rates['gas_standing_p']}p/day")
            print(f"      Elec: {rates['elec_unit_rate_p']}p/kWh | {rates['elec_standing_p']}p/day")
        else:
            result['error'] = "Could not extract rates"
            print(f"    ✗ Could not extract rates")
        
        result['url'] = page.url
        
    except PlaywrightTimeout as e:
        result['error'] = f"Timeout: {str(e)}"
        print(f"\n    ✗ TIMEOUT: {e}")
        if context:
            try:
                page.screenshot(path=f"screenshots/{region.replace(' ', '_')}_error.png")
            except:
                pass
    except Exception as e:
        result['error'] = str(e)
        print(f"\n    ✗ ERROR: {e}")
        if context:
            try:
                page.screenshot(path=f"screenshots/{region.replace(' ', '_')}_error.png")
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
    """Scrape with exponential backoff on failure."""
    
    for attempt in range(1, max_attempts + 1):
        print(f"\n  🔄 Attempt {attempt}/{max_attempts}")
        
        result = scrape_bg_tariffs(browser, postcode, region, attempt)
        
        if result.get('tariffs'):
            return result
        
        if attempt < max_attempts:
            # Exponential backoff: 30s, 60s, 120s...
            wait_time = 30 * (2 ** (attempt - 1))
            print(f"\n  ⏳ Failed. Waiting {wait_time}s before retry (backoff)...")
            time.sleep(wait_time)
    
    return result


# ============================================
# MAIN RUNNER
# ============================================

def run_scraper(headless: bool = False, test_postcode: str = None, 
                wait_secs: int = 20, max_retries: int = 3):
    """Main scraper with enhanced anti-detection."""
    
    results = []
    consecutive_failures = 0  # Track consecutive failures for early abort
    early_abort = False
    
    if test_postcode:
        postcodes = {k: v for k, v in DNO_POSTCODES_ALL.items() if v == test_postcode}
        if not postcodes:
            postcodes = {"Test": test_postcode}
    else:
        postcodes = DNO_POSTCODES_ALL
    
    with sync_playwright() as p:
        # Launch with extra stealth args
        browser = p.chromium.launch(
            headless=headless,
            channel="msedge",
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
        
        # Batch configuration (smaller batches, more delay)
        all_batches = [
            ("Batch 1", {k: postcodes[k] for k in list(postcodes.keys())[:3] if k in postcodes}),
            ("Batch 2", {k: postcodes[k] for k in list(postcodes.keys())[3:6] if k in postcodes}),
            ("Batch 3", {k: postcodes[k] for k in list(postcodes.keys())[6:9] if k in postcodes}),
            ("Batch 4", {k: postcodes[k] for k in list(postcodes.keys())[9:12] if k in postcodes}),
            ("Batch 5", {k: postcodes[k] for k in list(postcodes.keys())[12:] if k in postcodes}),
        ]
        all_batches = [(name, b) for name, b in all_batches if b]
        
        for batch_idx, (batch_name, batch_postcodes) in enumerate(all_batches):
            if early_abort:
                break
                
            print(f"\n{'#'*60}")
            print(f"  {batch_name} - {len(batch_postcodes)} regions")
            print('#'*60)
            
            for i, (region, postcode) in enumerate(batch_postcodes.items()):
                print(f"\n{'='*60}")
                print(f"  SCRAPING: {region} ({postcode})")
                print('='*60)
                
                result = scrape_with_retry(browser, postcode, region, max_retries)
                results.append(result)
                
                # Save partial results
                if result.get('tariffs'):
                    with open("bg_tariffs_partial.json", "w") as f:
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
                
                # Wait between regions (randomized)
                if i < len(batch_postcodes) - 1:
                    actual_wait = wait_secs + random.randint(-5, 10)
                    print(f"\n  ⏳ Waiting {actual_wait}s before next region...")
                    time.sleep(actual_wait)
            
            if early_abort:
                break
            
            # Longer wait between batches
            if batch_idx < len(all_batches) - 1:
                batch_wait = 90 + random.randint(0, 30)
                print(f"\n  🔄 Batch complete! Waiting {batch_wait}s before next batch...")
                time.sleep(batch_wait)
        
        browser.close()
    
    if early_abort:
        print(f"\n  ⚠️ Scraper aborted early with {len(results)} partial results")
    
    return results


def save_results(results: list):
    """Save to JSON and CSV."""
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    json_file = f"bg_tariffs_{timestamp}.json"
    with open(json_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved: {json_file}")
    
    csv_file = f"bg_tariffs_{timestamp}.csv"
    rows = []
    
    for r in results:
        base = {
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
                    "gas_unit_rate_p": t.get("gas_unit_rate_p"),
                    "gas_standing_p": t.get("gas_standing_p"),
                    "elec_unit_rate_p": t.get("elec_unit_rate_p"),
                    "elec_standing_p": t.get("elec_standing_p"),
                })
                rows.append(row)
        else:
            row = base.copy()
            row["error"] = r.get("error", "No tariffs found")
            rows.append(row)
    
    fieldnames = ["region", "postcode", "scraped_at", "attempt", "tariff_name", "exit_fee",
                  "gas_unit_rate_p", "gas_standing_p", 
                  "elec_unit_rate_p", "elec_standing_p", "error"]
    
    with open(csv_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)
    print(f"Saved: {csv_file}")
    
    # Summary
    print("\n" + "="*130)
    print("RESULTS SUMMARY")
    print("="*130)
    print(f"{'Region':<20} {'Tariff':<25} {'Exit Fee':<15} {'Gas Unit':<10} {'Gas Stand':<10} {'Elec Unit':<10} {'Elec Stand':<10}")
    print("-"*130)
    
    success_count = 0
    for r in results:
        if r.get("tariffs"):
            success_count += 1
            t = r["tariffs"][0]
            tariff_name = t.get('tariff_name', 'N/A')[:24]
            exit_fee = t.get('exit_fee', 'N/A')
            print(f"{r['region']:<20} {tariff_name:<25} {exit_fee:<15} {t.get('gas_unit_rate_p','N/A'):<10} {t.get('gas_standing_p','N/A'):<10} {t.get('elec_unit_rate_p','N/A'):<10} {t.get('elec_standing_p','N/A'):<10}")
        else:
            print(f"{r['region']:<20} {'ERROR':<25} {'':<15} {r.get('error', 'Unknown')}")
    
    print(f"\nSuccess rate: {success_count}/{len(results)} ({100*success_count/len(results):.1f}%)")


def main():
    import os
    import argparse
    
    parser = argparse.ArgumentParser(description="British Gas Tariff Scraper v10 - Stealth Edition")
    parser.add_argument("--headless", action="store_true", help="Run headless")
    parser.add_argument("--test", type=str, help="Test single postcode")
    parser.add_argument("--wait", type=int, default=20, help="Base seconds between regions (default: 20)")
    parser.add_argument("--retries", type=int, default=3, help="Max retries per region (default: 3)")
    args = parser.parse_args()
    
    os.makedirs("screenshots", exist_ok=True)
    
    print("="*60)
    print("BRITISH GAS TARIFF SCRAPER v10 - STEALTH EDITION")
    print("="*60)
    print(f"🕵️ Anti-detection: Rotating fingerprints, human simulation")
    print(f"📋 Extracts: Tariff name, exit fee, unit rates, standing charges")
    print(f"⏱️ Wait: ~{args.wait}s between regions, ~90s between batches")
    print(f"🔄 Max retries: {args.retries} (with exponential backoff)")
    print(f"📦 Batches: 3-3-3-3-2 regions")
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
