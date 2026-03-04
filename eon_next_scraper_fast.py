#!/usr/bin/env python3
"""
E.ON Next Standard Tariff Scraper v1.1 - SPEED OPTIMIZED (NON-EV)
- ~70% faster than v1.0 while maintaining bot detection avoidance
- For standard tariffs (NOT EV tariffs)
- Reduced delays, faster typing, shorter waits between regions
"""

import json
import csv
import re
import random
import time
import os
import sys
from datetime import datetime

print("Starting imports...")

try:
    print("  Importing undetected_chromedriver...", end=" ")
    import undetected_chromedriver as uc
    print("OK")
except Exception as e:
    print(f"FAILED: {e}")
    sys.exit(1)

try:
    print("  Importing selenium components...", end=" ")
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.common.action_chains import ActionChains
    from selenium.webdriver.support.ui import WebDriverWait, Select
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException, NoSuchElementException
    print("OK")
except Exception as e:
    print(f"FAILED: {e}")
    sys.exit(1)

print("All imports successful!\n")

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

EON_QUOTE_URL = "https://www.eonnext.com/dashboard/journey/get-a-quote"

POSTCODE_START_INDEX = {
    "AB24 3EN": 10,
    "G20 6NQ": 12,
    "BN2 7HQ": 16,
}


# ============================================
# SPEED-OPTIMIZED HUMAN BEHAVIOR SIMULATION
# ============================================

def human_delay(min_sec=0.1, max_sec=0.3):
    """FAST but still varied delay."""
    delay = random.betavariate(2, 5) * (max_sec - min_sec) + min_sec
    time.sleep(delay)


def long_delay():
    """Reduced page load wait."""
    time.sleep(random.uniform(1.0, 1.8))


def human_type(element, text):
    """FAST typing - batch characters with occasional micro-pauses."""
    i = 0
    while i < len(text):
        burst = random.randint(2, 4)
        element.send_keys(text[i:i+burst])
        i += burst
        if i < len(text):
            time.sleep(random.uniform(0.02, 0.06))


def human_click(driver, element):
    try:
        driver.execute_script("arguments[0].scrollIntoView({behavior: 'auto', block: 'center'});", element)
        time.sleep(random.uniform(0.05, 0.15))
        actions = ActionChains(driver)
        actions.move_to_element(element).pause(random.uniform(0.02, 0.08)).click().perform()
    except Exception:
        try:
            driver.execute_script("arguments[0].click();", element)
        except:
            element.click()


def random_scroll(driver):
    scroll_amount = random.randint(100, 300)
    driver.execute_script(f"window.scrollBy(0, {scroll_amount});")
    time.sleep(random.uniform(0.1, 0.2))


def scroll_to_bottom(driver):
    """Quick scroll to load content."""
    last_height = driver.execute_script("return document.body.scrollHeight")
    current = 0
    while current < last_height:
        current += random.randint(500, 800)
        driver.execute_script(f"window.scrollTo(0, {current});")
        time.sleep(random.uniform(0.08, 0.15))
    time.sleep(random.uniform(0.15, 0.25))
    driver.execute_script("window.scrollTo(0, 0);")
    time.sleep(random.uniform(0.08, 0.15))


# ============================================
# BROWSER SETUP
# ============================================

def create_driver(headless=False):
    options = uc.ChromeOptions()
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--lang=en-GB")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-setuid-sandbox")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-software-rasterizer")
    options.add_argument("--disable-accelerated-2d-canvas")
    options.add_argument("--no-zygote")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")

    if headless:
        options.add_argument("--headless=new")

    driver = uc.Chrome(options=options, use_subprocess=False, version_main=145)
    driver.set_page_load_timeout(60)
    driver.implicitly_wait(3)
    
    return driver


# ============================================
# HELPER FUNCTIONS
# ============================================

def close_popup(driver):
    """Close any popup by clicking X."""
    try:
        close_selectors = [
            "button[aria-label*='close' i]",
            "button[aria-label*='Close' i]",
            "[class*='close']",
            "[class*='Close']",
            "button svg",
            ".modal button",
            "[role='dialog'] button",
        ]
        
        for selector in close_selectors:
            try:
                buttons = driver.find_elements(By.CSS_SELECTOR, selector)
                for btn in buttons:
                    if btn.is_displayed():
                        btn.click()
                        print(f"    ✓ Closed popup")
                        time.sleep(0.3)
                        return True
            except:
                continue
        
        try:
            overlay = driver.find_element(By.CSS_SELECTOR, "[class*='overlay'], [class*='backdrop']")
            if overlay.is_displayed():
                driver.execute_script("arguments[0].click();", overlay)
                print(f"    ✓ Closed popup (overlay)")
                time.sleep(0.3)
                return True
        except:
            pass
            
    except Exception as e:
        pass
    
    return False


def check_already_supply_popup(driver):
    try:
        page_text = driver.page_source.lower()
        if 'already supply this property' in page_text or 'lets get you to the right place' in page_text:
            return True
    except:
        pass
    return False


def check_business_meter_popup(driver):
    try:
        page_text = driver.page_source.lower()
        if 'business meter' in page_text or 'business account' in page_text or 'commercial meter' in page_text or 'business customer' in page_text:
            return True
    except:
        pass
    return False


def check_chrome_app_popup(driver):
    try:
        try:
            alert = driver.switch_to.alert
            alert.dismiss()
            print(f"    ✓ Dismissed Chrome alert")
            return True
        except:
            pass
        
        page_text = driver.page_source.lower()
        if 'open app' in page_text or 'wants to open' in page_text or 'external protocol' in page_text:
            return True
    except:
        pass
    return False


def check_missing_out_popup(driver):
    try:
        page_text = driver.page_source.lower()
        if "what you'll be missing" in page_text or "what you will be missing" in page_text or "here's what you" in page_text:
            return True
    except:
        pass
    return False


def check_eligible_popup(driver):
    try:
        page_text = driver.page_source.lower()
        if "great news" in page_text and "eligible" in page_text:
            return True
        if "you're eligible" in page_text or "you are eligible" in page_text:
            return True
    except:
        pass
    return False


def handle_eligible_popup(driver):
    try:
        print(f"    ⚠ 'Great news you're eligible' popup detected")
        
        button_texts = ["See prices", "See tariff prices", "Continue", "Close", "Got it", "OK", "Okay"]
        for text in button_texts:
            try:
                btn = driver.find_element(By.XPATH, f"//button[contains(text(), '{text}')]")
                if btn.is_displayed():
                    btn.click()
                    print(f"    ✓ Clicked '{text}'")
                    time.sleep(0.5)
                    return True
            except:
                pass
            
            try:
                btn = driver.find_element(By.XPATH, f"//*[contains(text(), '{text}')]")
                if btn.is_displayed():
                    btn.click()
                    print(f"    ✓ Clicked '{text}'")
                    time.sleep(0.5)
                    return True
            except:
                continue
        
        if close_popup(driver):
            return True
        
        return False
    except Exception as e:
        print(f"    ✗ Failed to handle eligible popup: {e}")
        return False


def handle_missing_out_popup(driver, postcode):
    try:
        print(f"    ⚠ 'What you'll be missing' popup detected")
        
        if close_popup(driver):
            time.sleep(0.5)
            return True
        
        dismiss_texts = ["No thanks", "No, thanks", "Continue", "Skip", "Close", "Not now"]
        for text in dismiss_texts:
            try:
                btn = driver.find_element(By.XPATH, f"//*[contains(text(), '{text}')]")
                if btn.is_displayed():
                    btn.click()
                    print(f"    ✓ Clicked '{text}'")
                    time.sleep(0.5)
                    return True
            except:
                continue
        
        print(f"    → Refreshing page...")
        driver.refresh()
        time.sleep(1.5)
        
        try:
            pc_input = WebDriverWait(driver, 8).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'input[name*="postcode" i], input[placeholder*="postcode" i]'))
            )
            pc_input.clear()
            human_type(pc_input, postcode)
            print(f"    ✓ Re-entered postcode")
            time.sleep(1)
        except:
            pass
        
        return True
    except Exception as e:
        print(f"    ✗ Failed to handle popup: {e}")
        return False


def check_postcode_empty(driver, expected_postcode):
    try:
        for selector in ['input[name*="postcode" i]', 'input[placeholder*="postcode" i]']:
            try:
                pc_input = driver.find_element(By.CSS_SELECTOR, selector)
                if pc_input.is_displayed():
                    current = pc_input.get_attribute('value') or ''
                    if current.strip() == '' or current.strip().upper() != expected_postcode.upper():
                        return True, pc_input
            except:
                continue
    except:
        pass
    return False, None


COMMERCIAL_KEYWORDS = [
    'kiosk', 'bt kiosk', ' pcp ', 'church', 'school', 'college', 'university',
    'hotel', 'pub ', ' inn ', 'farm ', 'barn ', 'lodge ', 'office', 'surgery',
    'pharmacy', 'clinic', 'hospital', 'garage ', 'workshop', 'warehouse',
    'limited', ' ltd', ' plc', 'centre', 'center', 'chapel', 'hall ',
    'club ', 'shop ', 'store ', 'restaurant', 'cafe ', 'bar ', 'unit ',
]

def get_valid_addresses(options, start_idx, tried_addresses):
    valid = []
    skip_texts = ['select', 'choose', 'please select']

    for i in range(start_idx, len(options)):
        if i in tried_addresses:
            continue
        try:
            text = options[i].text.strip()
            if not text or any(text.lower().startswith(s) for s in skip_texts):
                continue
            tl = text.lower()
            if any(kw in tl for kw in COMMERCIAL_KEYWORDS):
                continue
            valid.append((i, text))
        except:
            continue

    return valid


def enter_postcode(driver, postcode):
    postcode_input = None
    for selector in ['input[name*="postcode" i]', 'input[placeholder*="postcode" i]', 'input[id*="postcode" i]']:
        try:
            postcode_input = driver.find_element(By.CSS_SELECTOR, selector)
            if postcode_input.is_displayed():
                break
        except:
            continue
    
    if not postcode_input:
        raise Exception("Could not find postcode input")
    
    human_click(driver, postcode_input)
    human_delay(0.1, 0.2)
    postcode_input.clear()
    human_delay(0.1, 0.2)
    human_type(postcode_input, postcode)
    time.sleep(random.uniform(1.5, 2.5))  # Wait for address lookup
    
    return postcode_input


def select_no_ev(driver):
    """Select NO for EV question (standard tariffs)."""
    try:
        # Click NO for EV
        no_buttons = driver.find_elements(By.XPATH, "//*[text()='No']")
        for btn in no_buttons:
            try:
                if btn.is_displayed():
                    human_click(driver, btn)
                    print(f"    ✓ Clicked 'No' for EV")
                    human_delay(0.2, 0.4)
                    return True
            except:
                continue
    except Exception as e:
        print(f"    ⚠ Could not click No for EV: {e}")
    return False


def select_options_after_address(driver):
    """Select fuel type, NO for EV, usage level."""
    
    # EV - No (standard tariffs)
    select_no_ev(driver)
    
    # Fuel type - Electricity and gas
    try:
        elec_gas = driver.find_element(By.XPATH, "//*[contains(text(), 'Electricity and gas')]")
        if elec_gas.is_displayed():
            human_click(driver, elec_gas)
            human_delay(0.3, 0.6)
    except:
        pass
    
    # Usage level
    try:
        usage = driver.find_element(By.XPATH, "//*[contains(text(), '1-2 bedrooms')]")
        if usage.is_displayed():
            human_click(driver, usage)
            human_delay(0.3, 0.6)
    except:
        pass


def click_see_prices(driver):
    for text in ["See tariff prices", "Get quote", "Continue"]:
        try:
            btn = driver.find_element(By.XPATH, f"//button[contains(text(), '{text}')]")
            if btn.is_displayed():
                human_click(driver, btn)
                return True
        except:
            continue
    return False


# ============================================
# RATE EXTRACTION - STANDARD (NON-EV) TARIFFS
# ============================================

def extract_rates(driver) -> dict:
    """Extract rates from the results page for standard (non-EV) tariffs."""
    rates = {}
    
    try:
        # Scroll down to load all content and capture all prices
        print(f"    📜 Scrolling to load all prices...")
        scroll_to_bottom(driver)
        human_delay(0.3, 0.5)
        
        page_text = driver.find_element(By.TAG_NAME, "body").text
        
        with open("debug_page_text.txt", "w", encoding="utf-8") as f:
            f.write(page_text)
        print(f"    📄 Saved page text to debug_page_text.txt")
        
        # Tariff name - find line starting with "Next " (all E.ON Next tariffs do)
        lines = [l.strip() for l in page_text.splitlines() if l.strip()]
        for line in lines:
            if line.lower().startswith('next ') and len(line) <= 60:
                rates['tariff_name'] = line
                break

        # Exit fee
        match = re.search(r'£(\d+)\s*(?:per fuel\s*)?exit fee|exit fee[:\s]*£(\d+)', page_text, re.I)
        if match:
            rates['exit_fee_gbp'] = int(match.group(1) or match.group(2))

        # Find all p/kWh and p/day values in order — first pair is elec, second is gas
        unit_rates = re.findall(r'(\d+\.\d+)\s*p\s*(?:per\s*)?kWh', page_text, re.I)
        standing_charges = re.findall(r'(\d+\.\d+)\s*p\s*(?:per\s*)?day', page_text, re.I)

        if len(unit_rates) >= 1:
            rates['elec_unit_rate_p'] = float(unit_rates[0])
        if len(unit_rates) >= 2:
            rates['gas_unit_rate_p'] = float(unit_rates[1])
        if len(standing_charges) >= 1:
            rates['elec_standing_p'] = float(standing_charges[0])
        if len(standing_charges) >= 2:
            rates['gas_standing_p'] = float(standing_charges[1])
        
    except Exception as e:
        print(f"    ✗ Extraction error: {e}")
    
    return rates


# ============================================
# MAIN SCRAPING LOGIC
# ============================================

def scrape_eon(driver, postcode: str, region: str, attempt: int = 1,
               tried_addresses: set = None) -> tuple:
    
    if tried_addresses is None:
        tried_addresses = set()
    
    result = {
        "supplier": "eon_next",
        "region": region,
        "postcode": postcode,
        "scraped_at": datetime.now().isoformat(),
        "tariffs": [],
        "attempt": attempt,
    }
    
    try:
        # STEP 1: Load page
        print(f"\n  [STEP 1] Loading page...")
        time.sleep(random.uniform(0.5, 1.0))
        
        driver.get(EON_QUOTE_URL)
        long_delay()
        print(f"    ✓ Page loaded")
        random_scroll(driver)
        
        # Handle cookies
        try:
            cookie_btn = WebDriverWait(driver, 4).until(
                EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler"))
            )
            human_click(driver, cookie_btn)
            print(f"    ✓ Accepted cookies")
            human_delay(0.2, 0.4)
        except:
            pass
        
        # STEP 2: Enter postcode
        print(f"\n  [STEP 2] Entering postcode: {postcode}")
        enter_postcode(driver, postcode)
        print(f"    ✓ Typed postcode")
        
        # STEP 3: Select address
        print(f"\n  [STEP 3] Selecting address...")
        
        try:
            address_dropdown = WebDriverWait(driver, 12).until(
                EC.presence_of_element_located((By.TAG_NAME, "select"))
            )
            print(f"    ✓ Dropdown found")
        except:
            raise Exception("Address dropdown did not appear")
        
        human_delay(0.2, 0.4)
        select = Select(address_dropdown)
        options = select.options
        
        start_idx = POSTCODE_START_INDEX.get(postcode, 1)
        valid_addresses = get_valid_addresses(options, start_idx, tried_addresses)
        
        if not valid_addresses:
            raise Exception("No valid residential addresses found")
        
        print(f"    Found {len(valid_addresses)} valid addresses")
        
        success = False
        max_address_tries = min(20, len(valid_addresses))
        
        for addr_idx, addr_text in valid_addresses[:max_address_tries]:
            print(f"\n    Trying #{addr_idx}: {addr_text[:50]}...")
            tried_addresses.add(addr_idx)
            
            human_delay(0.2, 0.4)
            select.select_by_index(addr_idx)
            human_delay(0.3, 0.6)
            
            # Check for Chrome app popup
            if check_chrome_app_popup(driver):
                print(f"    ⚠ Chrome app popup - refreshing...")
                driver.refresh()
                human_delay(0.5, 0.8)
                enter_postcode(driver, postcode)
                human_delay(0.5, 0.8)
                try:
                    address_dropdown = WebDriverWait(driver, 8).until(
                        EC.presence_of_element_located((By.TAG_NAME, "select"))
                    )
                    select = Select(address_dropdown)
                except:
                    pass
                continue
            
            # Check for "already supply" popup
            if check_already_supply_popup(driver):
                print(f"    ⚠ Already EON customer - closing popup...")
                close_popup(driver)
                human_delay(0.2, 0.4)
                
                try:
                    address_dropdown = driver.find_element(By.TAG_NAME, "select")
                    select = Select(address_dropdown)
                except:
                    print(f"    Re-entering postcode...")
                    enter_postcode(driver, postcode)
                    human_delay(0.5, 0.8)
                    address_dropdown = WebDriverWait(driver, 8).until(
                        EC.presence_of_element_located((By.TAG_NAME, "select"))
                    )
                    select = Select(address_dropdown)
                continue
            
            # Check for electricity-only property (no gas meter)
            try:
                body_text = driver.find_element(By.TAG_NAME, "body").text.lower()
                if "only have electricity at this property" in body_text or "only have electricity" in body_text:
                    print(f"    ⚠ Electricity-only property - skipping to next address...")
                    enter_postcode(driver, postcode)
                    human_delay(0.5, 0.8)
                    try:
                        address_dropdown = WebDriverWait(driver, 8).until(
                            EC.presence_of_element_located((By.TAG_NAME, "select"))
                        )
                        select = Select(address_dropdown)
                    except:
                        pass
                    continue
            except:
                pass

            # Check for business meter popup
            if check_business_meter_popup(driver):
                print(f"    ⚠ Business meter - closing popup...")
                close_popup(driver)
                human_delay(0.2, 0.4)
                
                try:
                    address_dropdown = driver.find_element(By.TAG_NAME, "select")
                    select = Select(address_dropdown)
                except:
                    print(f"    Re-entering postcode...")
                    enter_postcode(driver, postcode)
                    human_delay(0.5, 0.8)
                    address_dropdown = WebDriverWait(driver, 8).until(
                        EC.presence_of_element_located((By.TAG_NAME, "select"))
                    )
                    select = Select(address_dropdown)
                continue
            
            # Check for "Something's gone wrong" error page
            try:
                body = driver.find_element(By.TAG_NAME, "body").text.lower()
                if "something's gone wrong" in body or "something went wrong" in body:
                    print(f"    ⚠ E.ON error page - reloading...")
                    driver.get(driver.current_url.split('?')[0])
                    human_delay(1.5, 2.5)
                    enter_postcode(driver, postcode)
                    human_delay(0.8, 1.2)
                    try:
                        address_dropdown = WebDriverWait(driver, 10).until(
                            EC.presence_of_element_located((By.TAG_NAME, "select"))
                        )
                        select = Select(address_dropdown)
                    except:
                        pass
                    continue
            except:
                pass

            # Check for page reset
            is_empty, pc_input = check_postcode_empty(driver, postcode)
            if is_empty:
                print(f"    ⚠ Page reset - re-entering postcode...")
                if pc_input:
                    pc_input.clear()
                    human_type(pc_input, postcode)
                else:
                    enter_postcode(driver, postcode)
                human_delay(0.5, 0.8)
                try:
                    address_dropdown = WebDriverWait(driver, 8).until(
                        EC.presence_of_element_located((By.TAG_NAME, "select"))
                    )
                    select = Select(address_dropdown)
                except:
                    pass
                continue
            
            # Check for 'what you'll be missing' popup
            if check_missing_out_popup(driver):
                print(f"    ⚠ 'Missing out' popup...")
                handle_missing_out_popup(driver, postcode)
                human_delay(0.3, 0.6)
                continue
            
            success = True
            break
        
        if not success:
            raise Exception("Could not find suitable address")
        
        print(f"    ✓ Address selected")
        
        # STEP 4: Select options (NO for EV)
        print(f"\n  [STEP 4] Selecting options (NO EV)...")
        select_options_after_address(driver)
        print(f"    ✓ Options selected")
        
        # STEP 5: Handle eligible popup
        if check_eligible_popup(driver):
            print(f"\n  [STEP 5] Handling eligible popup...")
            handle_eligible_popup(driver)
            human_delay(0.2, 0.4)
        
        # STEP 6: Check for prepayment meter
        print(f"\n  [STEP 6] Checking for prepayment...")
        page_text = driver.page_source.lower()
        if 'prepayment' in page_text or 'prepay' in page_text:
            print(f"    ⚠ Prepayment meter detected - going back...")
            driver.back()
            long_delay()
            raise Exception("Prepayment meter - need different address")
        
        # STEP 7: Click see prices
        print(f"\n  [STEP 7] Clicking see prices...")
        if not click_see_prices(driver):
            for selector in ['button[type="submit"]', 'button.primary', 'button.cta']:
                try:
                    btn = driver.find_element(By.CSS_SELECTOR, selector)
                    if btn.is_displayed():
                        human_click(driver, btn)
                        break
                except:
                    continue
        
        print(f"    ✓ Clicked")
        
        # Wait for results page to load
        time.sleep(random.uniform(2.5, 4.0))
        
        # Check for popups on results page
        if check_missing_out_popup(driver):
            print(f"    ⚠ 'Missing out' popup on results...")
            handle_missing_out_popup(driver, postcode)
            human_delay(0.3, 0.6)
        
        if check_eligible_popup(driver):
            handle_eligible_popup(driver)
            human_delay(0.2, 0.4)
        
        # STEP 8: Expand details (MUST DO FOR NON-EV)
        print(f"\n  [STEP 8] Expanding details...")
        human_delay(0.3, 0.6)
        
        # Check again for popup
        if check_missing_out_popup(driver):
            handle_missing_out_popup(driver, postcode)
            human_delay(0.5, 0.8)
        
        # Click "More info" / "View details" to expand tariff details
        expanded = False
        for text in ["More info", "View details", "See details", "Show details", "View prices"]:
            try:
                btn = driver.find_element(By.XPATH, f"//*[contains(text(), '{text}')]")
                if btn.is_displayed():
                    human_click(driver, btn)
                    print(f"    ✓ Clicked '{text}'")
                    expanded = True
                    break
            except:
                continue
        
        if not expanded:
            print(f"    ⚠ No expand button found")
        
        human_delay(0.5, 0.8)
        driver.save_screenshot(f"screenshots/eon_{region.replace(' ', '_')}_expanded.png")
        
        # STEP 9: Extract rates
        print(f"\n  [STEP 9] Extracting rates...")
        
        # Final check for popup blocking rates
        if check_missing_out_popup(driver):
            print(f"    ⚠ Popup blocking rates page!")
            handle_missing_out_popup(driver, postcode)
            human_delay(0.5, 0.8)
            driver.save_screenshot(f"screenshots/eon_{region.replace(' ', '_')}_after_popup.png")
        
        if check_eligible_popup(driver):
            handle_eligible_popup(driver)
            human_delay(0.2, 0.4)
        
        rates = extract_rates(driver)
        
        driver.save_screenshot(f"screenshots/eon_{region.replace(' ', '_')}_final.png")
        
        if rates:
            result['tariffs'].append(rates)
            print(f"    ✓ EXTRACTED:")
            for k, v in rates.items():
                print(f"      {k}: {v}")
        else:
            result['error'] = "Could not extract rates"
            print(f"    ✗ No rates found")
        
        result['url'] = driver.current_url
        
    except Exception as e:
        result['error'] = str(e)
        print(f"\n    ✗ ERROR: {e}")
        try:
            driver.save_screenshot(f"screenshots/eon_{region.replace(' ', '_')}_error.png")
        except:
            pass
    
    result['tried_addresses'] = list(tried_addresses)
    
    return result, tried_addresses


def scrape_with_retry(driver, postcode: str, region: str, max_attempts: int = 3) -> dict:
    tried = set()
    
    for attempt in range(1, max_attempts + 1):
        print(f"\n  🔄 Attempt {attempt}/{max_attempts}")
        if tried:
            print(f"     Already tried addresses: {sorted(tried)}")
        
        result, tried = scrape_eon(driver, postcode, region, attempt, tried)
        
        if result.get('tariffs'):
            return result
        
        if attempt < max_attempts:
            wait = 8 + random.randint(0, 12)
            print(f"\n  ⏳ Waiting {wait}s...")
            time.sleep(wait)
    
    return result


def run_scraper(headless=False, test_postcode=None, regions=None, wait_secs=10, max_retries=3):
    results = []
    consecutive_failures = 0
    early_abort = False
    
    if test_postcode:
        postcodes = {k: v for k, v in DNO_POSTCODES.items() if v == test_postcode}
        if not postcodes:
            postcodes = {"Test": test_postcode}
    elif regions:
        region_list = [r.strip() for r in regions.split(",")]
        postcodes = {}
        for region_name, postcode in DNO_POSTCODES.items():
            for r in region_list:
                if r.lower() in region_name.lower():
                    postcodes[region_name] = postcode
                    break
        if not postcodes:
            print(f"⚠ No matching regions found for: {regions}")
            print(f"  Available regions: {', '.join(DNO_POSTCODES.keys())}")
            return []
        print(f"  Scraping {len(postcodes)} regions: {', '.join(postcodes.keys())}")
    else:
        postcodes = DNO_POSTCODES
    
    items = list(postcodes.items())
    batches = [items[i:i+3] for i in range(0, len(items), 3)]
    
    for batch_idx, batch in enumerate(batches):
        if early_abort:
            break
            
        print(f"\n{'#'*60}")
        print(f"  BATCH {batch_idx + 1}/{len(batches)} - {len(batch)} regions")
        print('#'*60)
        
        driver = None
        try:
            print("  🌐 Starting Chrome (undetected)...")
            driver = create_driver(headless)
            print("  ✓ Browser ready")
            
            for i, (region, postcode) in enumerate(batch):
                print(f"\n{'='*60}")
                print(f"  {region} ({postcode})")
                print('='*60)
                
                result = scrape_with_retry(driver, postcode, region, max_retries)
                results.append(result)
                
                if result.get('tariffs'):
                    with open("eon_tariffs_partial.json", "w") as f:
                        json.dump(results, f, indent=2)
                    print(f"  ✓ Success!")
                    consecutive_failures = 0
                else:
                    print(f"  ✗ Failed")
                    consecutive_failures += 1
                
                if consecutive_failures >= 3 and len(results) <= 4:
                    print(f"\n  🛑 EARLY ABORT: First {consecutive_failures} regions failed consecutively")
                    print(f"  → Scraper appears broken on this environment")
                    print(f"  → Run manually on local machine")
                    early_abort = True
                    break
                
                if i < len(batch) - 1:
                    wait = wait_secs + random.randint(-3, 8)
                    print(f"\n  ⏳ Waiting {wait}s...")
                    time.sleep(wait)
        
        finally:
            if driver:
                driver.quit()
                print("  Browser closed")
        
        if early_abort:
            break
        
        if batch_idx < len(batches) - 1:
            batch_wait = 30 + random.randint(0, 20)
            print(f"\n  🔄 Batch done. Waiting {batch_wait}s...")
            time.sleep(batch_wait)
    
    if early_abort:
        print(f"\n  ⚠️ Scraper aborted early with {len(results)} partial results")
    
    return results


def save_results(results):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    with open(f"eon_tariffs_{timestamp}.json", "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved: eon_tariffs_{timestamp}.json")
    
    rows = []
    for r in results:
        base = {"supplier": "eon_next", "region": r["region"], "postcode": r["postcode"],
                "scraped_at": r["scraped_at"], "attempt": r.get("attempt", 1)}
        if r.get("tariffs"):
            for t in r["tariffs"]:
                row = base.copy()
                row.update(t)
                rows.append(row)
        else:
            base["error"] = r.get("error", "Unknown")
            rows.append(base)
    
    # Standard tariff fields (no peak/offpeak/smart charging)
    fields = ["supplier", "region", "postcode", "scraped_at", "attempt", "tariff_name",
              "elec_unit_rate_p", "elec_standing_p",
              "gas_unit_rate_p", "gas_standing_p", "exit_fee_gbp", "error"]
    
    with open(f"eon_tariffs_{timestamp}.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)
    
    print("\n" + "="*70)
    success = sum(1 for r in results if r.get('tariffs'))
    print(f"Success: {success}/{len(results)} ({100*success/len(results) if results else 0:.0f}%)")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="E.ON Next Standard Tariff Scraper v1.1 - SPEED OPTIMIZED (NON-EV)")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--test", type=str, help="Test single postcode")
    parser.add_argument("--regions", type=str, help="Comma-separated list of regions")
    parser.add_argument("--list-regions", action="store_true", help="List all available regions")
    parser.add_argument("--wait", type=int, default=10, help="Seconds between regions (default: 10)")
    parser.add_argument("--retries", type=int, default=3)
    args = parser.parse_args()
    
    if args.list_regions:
        print("Available regions:")
        for region, postcode in DNO_POSTCODES.items():
            print(f"  {region}: {postcode}")
        return
    
    os.makedirs("screenshots", exist_ok=True)
    
    print("="*60)
    print("E.ON NEXT STANDARD TARIFF SCRAPER v1.1 - SPEED OPTIMIZED 🚀")
    print("="*60)
    print("✓ NON-EV version (standard tariffs)")
    print("✓ ~70% faster than v1.0")
    print("✓ Between-region wait: 10s (was 30s)")
    print("✓ Batch wait: 30-50s (was 120-180s)")
    print()
    
    results = run_scraper(args.headless, args.test, args.regions, args.wait, args.retries)
    save_results(results)
    
    input("\nPress Enter to exit...")


if __name__ == "__main__":
    main()
