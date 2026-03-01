#!/usr/bin/env python3
"""
Fuse Energy Tariff Scraper v2
Simple flow:
1. Enter postcode → address dropdown appears
2. Select address from dropdown
3. If "meter unsupported" → try another address
4. Click on tariff card
5. Click "Select tariff" for electricity/gas to see rates
6. Extract rates
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

FUSE_URL = "https://www.fuseenergy.com/app/boarding/premises"

# Some postcodes need higher start index (flats, commercial at top)
POSTCODE_START_INDEX = {
    "BN2 7HQ": 8,
    "AB24 3EN": 5,
    "G20 6NQ": 5,
    "L3 2BN": 5,
    "N5 2SD": 8,
    "NE2 1UY": 30,  # TONS of apartments at start
}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
]

STEALTH_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'plugins', {
    get: () => [
        { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
        { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
        { name: 'Native Client', filename: 'internal-nacl-plugin' }
    ]
});
Object.defineProperty(navigator, 'languages', { get: () => ['en-GB', 'en-US', 'en'] });
window.chrome = { runtime: {}, loadTimes: function() {}, csi: function() {} };
"""

# ============================================
# HELPERS
# ============================================

def human_delay(min_ms=500, max_ms=1500):
    delay = random.betavariate(2, 5) * (max_ms - min_ms) + min_ms
    time.sleep(delay / 1000)

def typing_delay():
    return random.randint(50, 120)

def is_meter_unsupported(page) -> bool:
    """Check if meter unsupported error is shown."""
    try:
        text = page.inner_text('body').lower()
        unsupported_phrases = [
            'unsupported meter',
            'meter unsupported',
            'meter type unsupported',
            'not supported',
            'cannot supply',
            'unable to supply',
            'prepayment',
            'economy 7',
            'economy 10',
            'meter not supported',
            'this meter type',
        ]
        return any(phrase in text for phrase in unsupported_phrases)
    except:
        return False


def is_residential_address(address_text: str) -> bool:
    """STRICT filter - only accept format like '28, Falconar Street' or '28a, Main Road'."""
    import re
    
    address_text = address_text.strip()
    address_lower = address_text.lower()
    
    # Immediate rejections - if contains ANY of these words, reject
    bad_words = ['apartment', 'flat', 'floor', 'surgery', 'dental', 'doctor', 
                 'clinic', 'export', 'business', 'office', 'shop', 'unit', 
                 'suite', 'room', 'studio', 'maisonette', 'landlord', 'supply',
                 'hotel', 'hostel', 'hall', 'house of', 'court', 'block',
                 'tower', 'centre', 'center']
    
    for word in bad_words:
        if word in address_lower:
            return False
    
    # MUST match: starts with number(s), optional letter, comma, space
    # Examples: "28, Street" or "28a, Street" or "123, Road"
    # Rejects: "Apartment 2, 1 Street" (starts with word)
    pattern = r'^\d+[a-z]?,\s+[A-Z]'
    
    if re.match(pattern, address_text):
        return True
    
    return False

def extract_rates(page) -> dict:
    """Extract electricity and gas rates from page."""
    rates = {}
    
    try:
        text = page.inner_text('body')
        
        # Save for debug (with UTF-8 encoding)
        try:
            with open('debug_fuse_page.txt', 'w', encoding='utf-8') as f:
                f.write(text)
        except:
            pass  # Don't fail if we can't save debug file
        
        # Find tariff name
        tariff_patterns = [
            r'(Variable\s*Tariff)',
            r'(Fixed\s*Tariff(?:\s*\d+)?)',
            r'(EV\s*Tariff)',
            r'(Multi[\-\s]?rate)',
            r'(Smart\s*EV)',
        ]
        for p in tariff_patterns:
            m = re.search(p, text, re.I)
            if m:
                rates['tariff_name'] = m.group(1).strip()
                break
        
        # Exit fee
        exit_match = re.search(r'[Ee]xit\s*fee[:\s]*£?(\d+)', text)
        if exit_match:
            rates['exit_fee'] = f"£{exit_match.group(1)}"
        elif 'no exit fee' in text.lower():
            rates['exit_fee'] = '£0'
        
        # ELECTRICITY SECTION
        elec_section = re.search(r'Electricity(.*?)(?:Gas|$)', text, re.I | re.S)
        if elec_section:
            elec_text = elec_section.group(1)
            
            # Unit rate
            unit_match = re.search(r'(\d+\.?\d*)\s*p\s*(?:per\s*)?kWh', elec_text, re.I)
            if not unit_match:
                unit_match = re.search(r'[Uu]nit\s*rate[:\s]*(\d+\.?\d*)', elec_text)
            if unit_match:
                val = float(unit_match.group(1))
                if 10 < val < 60:
                    rates['elec_unit_rate_p'] = val
            
            # Standing charge
            sc_match = re.search(r'(\d+\.?\d*)\s*p\s*(?:per\s*)?day', elec_text, re.I)
            if not sc_match:
                sc_match = re.search(r'[Ss]tanding\s*charge[:\s]*(\d+\.?\d*)', elec_text)
            if sc_match:
                val = float(sc_match.group(1))
                if 20 < val < 80:
                    rates['elec_standing_p'] = val
        
        # GAS SECTION
        gas_section = re.search(r'Gas(.*?)(?:Electricity|$)', text, re.I | re.S)
        if gas_section:
            gas_text = gas_section.group(1)
            
            # Unit rate
            unit_match = re.search(r'(\d+\.?\d*)\s*p\s*(?:per\s*)?kWh', gas_text, re.I)
            if not unit_match:
                unit_match = re.search(r'[Uu]nit\s*rate[:\s]*(\d+\.?\d*)', gas_text)
            if unit_match:
                val = float(unit_match.group(1))
                if 3 < val < 20:
                    rates['gas_unit_rate_p'] = val
            
            # Standing charge
            sc_match = re.search(r'(\d+\.?\d*)\s*p\s*(?:per\s*)?day', gas_text, re.I)
            if not sc_match:
                sc_match = re.search(r'[Ss]tanding\s*charge[:\s]*(\d+\.?\d*)', gas_text)
            if sc_match:
                val = float(sc_match.group(1))
                if 20 < val < 60:
                    rates['gas_standing_p'] = val
        
    except Exception as e:
        print(f"      Extract error: {e}")
    
    return rates


# ============================================
# MAIN SCRAPER
# ============================================

def scrape_fuse(browser, postcode: str, region: str, attempt: int = 1) -> dict:
    """Scrape Fuse Energy tariffs for a postcode."""
    
    result = {
        "supplier": "fuse_energy",
        "region": region,
        "postcode": postcode,
        "scraped_at": datetime.now().isoformat(),
        "tariffs": [],
        "attempt": attempt,
    }
    
    context = None
    tried_addresses = set()  # Track address TEXT, not just index
    start_idx = POSTCODE_START_INDEX.get(postcode, 1)
    
    try:
        # Setup browser context
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=random.choice(USER_AGENTS),
            locale="en-GB",
            timezone_id="Europe/London",
        )
        context.add_init_script(STEALTH_SCRIPT)
        page = context.new_page()
        
        # ========== STEP 1: Load page ==========
        print(f"    [1] Loading Fuse...")
        page.goto(FUSE_URL, timeout=45000, wait_until="domcontentloaded")
        human_delay(2000, 3000)
        
        # Handle cookies
        try:
            cookie_btn = page.locator('button:has-text("Accept"), button:has-text("Allow")').first
            if cookie_btn.is_visible(timeout=2000):
                cookie_btn.click()
                human_delay(500, 1000)
        except:
            pass
        
        page.screenshot(path=f"screenshots/fuse_{region.replace(' ', '_')}_01_loaded.png")
        
        # ========== STEP 2: Enter postcode ==========
        print(f"    [2] Entering postcode: {postcode}")
        
        # Find postcode input
        postcode_input = page.locator('input[type="text"], input[name*="postcode" i], input[placeholder*="postcode" i]').first
        postcode_input.click()
        human_delay(300, 500)
        postcode_input.fill('')
        
        # Type postcode
        for char in postcode:
            postcode_input.type(char, delay=typing_delay())
        
        human_delay(1500, 2500)  # Wait for dropdown to appear
        
        page.screenshot(path=f"screenshots/fuse_{region.replace(' ', '_')}_02_postcode.png")
        
        # ========== STEP 3: Select address from dropdown ==========
        print(f"    [3] Selecting address...")
        
        max_restart_attempts = 10
        address_selected = False
        
        # Loop: each iteration is a fresh start after a failure
        for restart_num in range(max_restart_attempts):
            print(f"")
            print(f"      ===== RESTART ITERATION #{restart_num + 1}/{max_restart_attempts} =====")
            try:
                # Wait for dropdown to load
                human_delay(2000, 3000)
                
                # Get ALL addresses in the dropdown
                address_items = []
                try:
                    items = page.locator(f'[role="option"]:has-text("{postcode}")').all()
                    if items:
                        address_items = items
                except:
                    pass
                
                if not address_items:
                    try:
                        items = page.locator(f'div:has-text("{postcode}"), li:has-text("{postcode}")').all()
                        address_items = [item for item in items if item.is_visible()]
                    except:
                        pass
                
                if not address_items:
                    print(f"      ⚠ No addresses found yet, waiting longer...")
                    human_delay(2000, 3000)
                    # Try one more time
                    try:
                        items = page.locator(f'[role="option"]:has-text("{postcode}")').all()
                        if items:
                            address_items = items
                        else:
                            items = page.locator(f'div:has-text("{postcode}")').all()
                            address_items = [item for item in items if item.is_visible()]
                    except:
                        pass
                    
                    if not address_items:
                        print(f"      ✗ Still no addresses, will retry on next restart")
                        if restart_num < max_restart_attempts - 1:
                            # Try reloading the page
                            page.goto(FUSE_URL, timeout=30000, wait_until="domcontentloaded")
                            human_delay(2000, 3000)
                            try:
                                postcode_input = page.locator('input[type="text"]').first
                                postcode_input.click()
                                postcode_input.fill('')
                                for char in postcode:
                                    postcode_input.type(char, delay=typing_delay())
                                human_delay(2000, 3000)
                            except:
                                pass
                            continue
                        else:
                            break
                
                print(f"      Restart #{restart_num + 1}/{max_restart_attempts}: Found {len(address_items)} addresses, scanning for untried residential...")
                
                # Find the FIRST untried residential address (scan from start_idx onwards)
                target_item = None
                target_idx = None
                target_text = None
                
                for idx in range(start_idx, len(address_items)):
                    try:
                        item = address_items[idx]
                        addr_text = item.inner_text().strip()
                        
                        # Clean - extract just the address line containing the postcode
                        addr_lines = [line.strip() for line in addr_text.split('\n') if postcode in line]
                        if addr_lines:
                            addr_text = addr_lines[0]
                        
                        # Already tried?
                        if addr_text in tried_addresses:
                            print(f"        [{idx}] Already tried: {addr_text[:50]}")
                            continue
                        
                        # Residential?
                        if not is_residential_address(addr_text):
                            print(f"        [{idx}] Skip non-residential: {addr_text[:50]}")
                            tried_addresses.add(addr_text)
                            continue
                        
                        # Found it!
                        target_item = item
                        target_idx = idx
                        target_text = addr_text
                        print(f"        [{idx}] ✓ Good residential address")
                        break
                        
                    except Exception as e:
                        print(f"        [{idx}] Error reading: {str(e)[:40]}")
                        continue
                
                if not target_item:
                    print(f"      ✗ No more untried residential addresses found")
                    break
                
                # Try this address
                print(f"      Trying [{target_idx}]: {target_text[:60]}")
                tried_addresses.add(target_text)
                
                # Check if this address has "Meter unsupported" warning in the dropdown
                try:
                    meter_warning = target_item.locator('text="Meter unsupported"').count()
                    if meter_warning > 0:
                        print(f"      ⚠ Meter unsupported shown in dropdown, skipping")
                        continue
                except:
                    pass
                
                # Click it
                try:
                    arrow_selectors = ['button', '[role="button"]', 'svg']
                    clicked = False
                    for selector in arrow_selectors:
                        try:
                            arrow = target_item.locator(selector).first
                            if arrow.is_visible(timeout=1000):
                                arrow.click()
                                clicked = True
                                break
                        except:
                            continue
                    
                    if not clicked:
                        target_item.click()
                except Exception as e:
                    print(f"      ✗ Click failed: {str(e)[:50]}")
                    target_item.click()
                
                human_delay(3000, 4000)
                
                # Screenshot to see what page we landed on
                try:
                    page.screenshot(path=f"screenshots/fuse_{region.replace(' ', '_')}_after_address_{restart_num}.png")
                except:
                    pass
                
                # ========== FORCE CLOSE ANY MODALS ==========
                print(f"      Closing any modals...")
                for _ in range(3):
                    try:
                        page.keyboard.press("Escape")
                        human_delay(800, 1200)
                    except:
                        pass
                human_delay(2500, 3500)  # Longer wait for page to settle
                
                # Check if we're still on address dropdown (address click failed)
                try:
                    still_on_dropdown = page.locator('text="Enter your postcode"').is_visible(timeout=2000)
                    if still_on_dropdown:
                        print(f"      ✗ Still on address dropdown, click didn't work")
                        continue
                except:
                    pass
                
                # ========== CRITICAL: Check for unsupported meter FIRST ==========
                if is_meter_unsupported(page):
                    print(f"      ✗ Unsupported meter detected, restarting...")
                    page.goto(FUSE_URL, timeout=30000, wait_until="domcontentloaded")
                    human_delay(2000, 3000)
                    try:
                        postcode_input = page.locator('input[type="text"]').first
                        postcode_input.click()
                        postcode_input.fill('')
                        for char in postcode:
                            postcode_input.type(char, delay=typing_delay())
                        human_delay(1500, 2500)
                    except:
                        pass
                    continue  # Go to next restart_num (restart from beginning)
                
                # ========== Verify we ACTUALLY have both Electricity AND Gas ==========
                print(f"      Verifying both fuels available...")
                
                page_progressed = False
                try:
                    # Must see BOTH Electricity and Gas sections with "Select a tariff"
                    elec_visible = page.locator('text="Electricity"').first.is_visible(timeout=5000)
                    gas_visible = page.locator('text="Gas"').first.is_visible(timeout=2000)
                    select_count = page.locator('text="Select a tariff"').count()
                    
                    print(f"      DEBUG: Elec={elec_visible}, Gas={gas_visible}, SelectButtons={select_count}")
                    
                    # Need both fuels with at least 2 "Select a tariff" buttons
                    if elec_visible and gas_visible and select_count >= 2:
                        print(f"      ✓ Both Electricity and Gas available!")
                        page_progressed = True
                    else:
                        print(f"      ✗ Missing fuel - WILL RESTART")
                        
                except Exception as e:
                    print(f"      ✗ Check failed: {str(e)[:60]}")
                
                if not page_progressed:
                    print(f"      >>> RESTARTING NOW - clearing session and starting fresh <<<")
                    
                    # CLEAR ALL COOKIES AND STORAGE
                    try:
                        print(f"      [DEBUG] Clearing cookies and storage...")
                        context.clear_cookies()
                        page.evaluate("() => { localStorage.clear(); sessionStorage.clear(); }")
                        print(f"      [DEBUG] Cookies cleared")
                    except Exception as e:
                        print(f"      [DEBUG] Clear cookies error: {str(e)[:50]}")
                    
                    # Go to blank first
                    try:
                        print(f"      [DEBUG] Going to blank page...")
                        page.goto("about:blank", timeout=10000, wait_until="domcontentloaded")
                        human_delay(500, 1000)
                        print(f"      [DEBUG] Blank page loaded")
                    except Exception as e:
                        print(f"      [DEBUG] Blank page error: {str(e)[:50]}")
                    
                    # Now go to Fuse
                    try:
                        print(f"      [DEBUG] Going to Fuse URL...")
                        page.goto(FUSE_URL, timeout=30000, wait_until="domcontentloaded")
                        print(f"      [DEBUG] Fuse page loaded")
                        human_delay(2000, 3000)
                    except Exception as e:
                        print(f"      [DEBUG] Fuse page error: {str(e)[:50]}")
                        continue
                    
                    # Re-enter postcode
                    try:
                        print(f"      [DEBUG] Finding postcode input...")
                        postcode_input = page.locator('input[type="text"], input[name*="postcode" i]').first
                        print(f"      [DEBUG] Clicking input...")
                        postcode_input.click()
                        human_delay(300, 500)
                        print(f"      [DEBUG] Clearing input...")
                        postcode_input.fill('')
                        print(f"      [DEBUG] Typing postcode...")
                        for char in postcode:
                            postcode_input.type(char, delay=typing_delay())
                        human_delay(1500, 2500)
                        print(f"      ✓ Re-entered postcode, cycling to next address")
                    except Exception as e:
                        print(f"      [DEBUG] Postcode entry error: {str(e)[:100]}")
                        continue
                    
                    continue  # Go to next restart_num (restart from beginning)
                
                # Success!
                address_selected = True
                print(f"      ✓ Address confirmed working")
                break
                
            except Exception as e:
                print(f"      ✗ Restart #{restart_num + 1} error: {str(e)[:100]}")
                print(f"      Will try restart #{restart_num + 2} if available...")
                continue
        
        if not address_selected:
            raise Exception(f"Could not find valid address after {max_restart_attempts} restarts")
        
        # ========== STEP 4: Click "Electricity - Select a tariff" ==========
        print(f"    [4] Opening Electricity tariffs...")
        
        try:
            # Click on the Electricity section
            elec_button = page.locator('text="Electricity" >> .. >> text="Select a tariff"').first
            if not elec_button.is_visible(timeout=3000):
                elec_button = page.locator('text="Electricity"').first
            
            elec_button.click()
            human_delay(2000, 3000)
            print(f"      ✓ Opened electricity tariffs")
        except Exception as e:
            print(f"      ⚠ Could not click electricity: {e}")
        
        page.screenshot(path=f"screenshots/fuse_{region.replace(' ', '_')}_04_electricity.png")
        
        # ========== STEP 5: Extract electricity rates ==========
        print(f"    [5] Extracting electricity rates...")
        
        elec_rates = {}
        try:
            text = page.inner_text('body')
            
            # Find all tariffs - look for patterns like "Dec Single Rate Fixed (13m) v3"
            tariff_blocks = re.split(r'(?=Dec |Single Rate |Off-Peak |Variable|Fixed|Smart EV)', text)
            
            for block in tariff_blocks:
                if 'Standing charge' not in block:
                    continue
                
                # Extract tariff name
                name_match = re.search(r'^([^\n]+)', block)
                tariff_name = name_match.group(1).strip() if name_match else "Unknown"
                
                # Standing charge
                sc_match = re.search(r'Standing charge.*?£([\d.]+)', block, re.I | re.S)
                standing = float(sc_match.group(1)) * 100 if sc_match else None  # Convert to pence
                
                # Unit rate (single rate)
                unit_match = re.search(r'Unit rate.*?£([\d.]+)', block, re.I | re.S)
                unit_rate = float(unit_match.group(1)) * 100 if unit_match else None  # Convert to pence
                
                # Exit fee
                exit_match = re.search(r'[Ee]arly exit fee.*?£([\d.]+)', block, re.S)
                if not exit_match:
                    exit_match = re.search(r'[Ee]xit fee.*?£([\d.]+)', block, re.S)
                exit_fee = f"£{exit_match.group(1)}" if exit_match else "£0"
                
                if standing and unit_rate:
                    if not elec_rates:  # Take first valid tariff
                        elec_rates = {
                            'tariff_name': tariff_name,
                            'elec_standing_p': round(standing, 2),
                            'elec_unit_rate_p': round(unit_rate, 2),
                            'exit_fee': exit_fee
                        }
                        print(f"      ✓ Found: {tariff_name}")
                        print(f"        {unit_rate:.2f}p/kWh, {standing:.2f}p/day, exit: {exit_fee}")
                        break
        except Exception as e:
            print(f"      ✗ Extract error: {e}")
        
        # ========== STEP 6: Close modal and open Gas ==========
        print(f"    [6] Closing modal and opening Gas...")
        
        # Close modal - just use Escape
        print(f"      Pressing Escape...")
        page.keyboard.press("Escape")
        human_delay(2500, 3500)  # Longer wait for modal to close
        
        # Now click Gas - try multiple approaches
        gas_clicked = False
        
        # Method 1: Click the entire Gas section container
        try:
            print(f"      Method 1: Clicking Gas container...")
            gas_section = page.locator('text="Gas"').first
            parent = gas_section.locator('xpath=ancestor::*[contains(@class, "cursor") or @role="button"][1]').first
            parent.click()
            gas_clicked = True
            print(f"      ✓ Clicked Gas container")
        except Exception as e:
            print(f"      Method 1 failed: {str(e)[:50]}")
        
        # Method 2: Just click the Gas text itself
        if not gas_clicked:
            try:
                print(f"      Method 2: Clicking Gas text...")
                page.locator('text="Gas"').first.click()
                gas_clicked = True
                print(f"      ✓ Clicked Gas text")
            except Exception as e:
                print(f"      Method 2 failed: {str(e)[:50]}")
        
        # Method 3: Find "Select a tariff" under Gas
        if not gas_clicked:
            try:
                print(f"      Method 3: Clicking 'Select a tariff' under Gas...")
                # Find all "Select a tariff" elements
                selects = page.locator('text="Select a tariff"').all()
                # Click the second one (Gas is usually second)
                if len(selects) >= 2:
                    selects[1].click()
                    gas_clicked = True
                    print(f"      ✓ Clicked second 'Select a tariff'")
            except Exception as e:
                print(f"      Method 3 failed: {str(e)[:50]}")
        
        if not gas_clicked:
            print(f"      ✗ Could not open Gas")
        
        human_delay(2500, 3500)
        
        page.screenshot(path=f"screenshots/fuse_{region.replace(' ', '_')}_05_gas.png")
        
        # ========== STEP 7: Extract gas rates ==========
        print(f"    [7] Extracting gas rates...")
        
        gas_rates = {}
        try:
            text = page.inner_text('body')
            
            # Save for debugging
            try:
                with open('debug_gas_page.txt', 'w', encoding='utf-8') as f:
                    f.write(text)
            except:
                pass
            
            # Look for Gas section specifically
            if 'Gas' in text and 'Standing charge' in text:
                tariff_blocks = re.split(r'(?=Dec |Single Rate |Variable|Fixed)', text)
                
                for block in tariff_blocks:
                    if 'Standing charge' not in block:
                        continue
                    
                    name_match = re.search(r'^([^\n]+)', block)
                    tariff_name = name_match.group(1).strip() if name_match else "Unknown"
                    
                    sc_match = re.search(r'Standing charge.*?£([\d.]+)', block, re.I | re.S)
                    standing = float(sc_match.group(1)) * 100 if sc_match else None
                    
                    unit_match = re.search(r'Unit rate.*?£([\d.]+)', block, re.I | re.S)
                    unit_rate = float(unit_match.group(1)) * 100 if unit_match else None
                    
                    # Exit fee
                    exit_match = re.search(r'[Ee]arly exit fee.*?£([\d.]+)', block, re.S)
                    if not exit_match:
                        exit_match = re.search(r'[Ee]xit fee.*?£([\d.]+)', block, re.S)
                    exit_fee = f"£{exit_match.group(1)}" if exit_match else "£0"
                    
                    if standing and unit_rate and 3 < unit_rate < 20:  # Gas rates sanity check
                        if not gas_rates:
                            gas_rates = {
                                'gas_standing_p': round(standing, 2),
                                'gas_unit_rate_p': round(unit_rate, 2),
                                'gas_exit_fee': exit_fee
                            }
                            print(f"      ✓ Found: {tariff_name}")
                            print(f"        {unit_rate:.2f}p/kWh, {standing:.2f}p/day, exit: {exit_fee}")
                            break
            
            if not gas_rates:
                print(f"      ⚠ No gas rates found (may not have gas supply)")
                
        except Exception as e:
            print(f"      ✗ Extract error: {e}")
        
        page.screenshot(path=f"screenshots/fuse_{region.replace(' ', '_')}_final.png", full_page=True)
        
        # ========== Combine results ==========
        print(f"    [8] Combining results...")
        
        combined_rates = {**elec_rates, **gas_rates}
        
        if combined_rates.get('elec_unit_rate_p') or combined_rates.get('gas_unit_rate_p'):
            result['tariffs'].append(combined_rates)
            print(f"      ✓ Complete!")
            print(f"        Elec: {combined_rates.get('elec_unit_rate_p', '?')}p/kWh, {combined_rates.get('elec_standing_p', '?')}p/day, exit: {combined_rates.get('exit_fee', '?')}")
            print(f"        Gas:  {combined_rates.get('gas_unit_rate_p', '?')}p/kWh, {combined_rates.get('gas_standing_p', '?')}p/day, exit: {combined_rates.get('gas_exit_fee', '?')}")
        else:
            result['error'] = "No rates extracted"
            print(f"      ✗ No rates found")
        
        result['url'] = page.url
        
    except PlaywrightTimeout as e:
        result['error'] = f"Timeout: {str(e)[:100]}"
        print(f"    ✗ TIMEOUT")
    except Exception as e:
        result['error'] = str(e)[:200]
        print(f"    ✗ ERROR: {e}")
    finally:
        if context:
            try:
                page.screenshot(path=f"screenshots/fuse_{region.replace(' ', '_')}_final.png")
            except:
                pass
            context.close()
    
    return result


def scrape_with_retry(browser, postcode: str, region: str, max_attempts: int = 3) -> dict:
    """Retry with exponential backoff."""
    for attempt in range(1, max_attempts + 1):
        print(f"\n  🔄 Attempt {attempt}/{max_attempts}")
        
        result = scrape_fuse(browser, postcode, region, attempt)
        
        if result.get('tariffs'):
            return result
        
        if attempt < max_attempts:
            wait = 30 * (2 ** (attempt - 1)) + random.randint(0, 10)
            print(f"  ⏳ Waiting {wait}s...")
            time.sleep(wait)
    
    return result


# ============================================
# RUNNER
# ============================================

def run_scraper(headless: bool = False, test_postcode: str = None):
    """Main runner."""
    
    results = []
    consecutive_failures = 0  # Track consecutive failures for early abort
    early_abort = False
    
    if test_postcode:
        postcodes = {k: v for k, v in DNO_POSTCODES.items() if v == test_postcode}
        if not postcodes:
            postcodes = {"Test": test_postcode}
    else:
        postcodes = DNO_POSTCODES
    
    os.makedirs("screenshots", exist_ok=True)
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            slow_mo=50,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-dev-shm-usage',
            ]
        )
        
        items = list(postcodes.items())
        
        for i, (region, postcode) in enumerate(items):
            print(f"\n{'='*50}")
            print(f"  [{i+1}/{len(items)}] {region} ({postcode})")
            print('='*50)
            
            result = scrape_with_retry(browser, postcode, region)
            results.append(result)
            
            # Track success/failure
            if result.get('tariffs'):
                consecutive_failures = 0  # Reset on success
            else:
                consecutive_failures += 1
            
            # EARLY ABORT: If first 3 regions all fail, scraper is broken
            if consecutive_failures >= 3 and len(results) <= 4:
                print(f"\n  🛑 EARLY ABORT: First {consecutive_failures} regions failed consecutively")
                print(f"  → Scraper appears broken on this environment")
                print(f"  → Run manually on local machine")
                early_abort = True
                break
            
            # Save partial
            with open("fuse_tariffs_partial.json", "w") as f:
                json.dump(results, f, indent=2)
            
            # Wait between regions
            if i < len(items) - 1:
                wait = random.randint(20, 35)
                print(f"\n  ⏳ Next region in {wait}s...")
                time.sleep(wait)
        
        browser.close()
    
    if early_abort:
        print(f"\n  ⚠️ Scraper aborted early with {len(results)} partial results")
    
    return results


def save_results(results: list):
    """Save JSON and CSV."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # JSON
    with open(f"fuse_tariffs_{ts}.json", "w") as f:
        json.dump(results, f, indent=2)
    
    # CSV
    rows = []
    for r in results:
        base = {
            "supplier": r["supplier"],
            "region": r["region"],
            "postcode": r["postcode"],
            "scraped_at": r["scraped_at"],
            "attempt": r.get("attempt", 1),
        }
        if r.get("tariffs"):
            for t in r["tariffs"]:
                row = {**base, **t}
                rows.append(row)
        else:
            rows.append({**base, "error": r.get("error", "Unknown")})
    
    with open(f"fuse_tariffs_{ts}.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "supplier", "region", "postcode", "scraped_at", "attempt",
            "tariff_name", "exit_fee", "elec_unit_rate_p", "elec_standing_p",
            "gas_unit_rate_p", "gas_standing_p", "gas_exit_fee", "error"
        ], extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)
    
    # Summary
    print(f"\n{'='*70}")
    print("SUMMARY")
    print('='*70)
    success = sum(1 for r in results if r.get('tariffs'))
    print(f"Success: {success}/{len(results)}")
    
    for r in results:
        if r.get('tariffs'):
            t = r['tariffs'][0]
            print(f"  ✓ {r['region']}: {t.get('elec_unit_rate_p', '?')}p elec, {t.get('gas_unit_rate_p', '?')}p gas")
        else:
            print(f"  ✗ {r['region']}: {r.get('error', 'Failed')[:40]}")


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--test", type=str, help="Test single postcode")
    args = parser.parse_args()
    
    print("="*50)
    print("FUSE ENERGY SCRAPER v2")
    print("="*50)
    
    results = run_scraper(headless=args.headless, test_postcode=args.test)
    save_results(results)
    print("\n✓ Done!")


if __name__ == "__main__":
    main()
