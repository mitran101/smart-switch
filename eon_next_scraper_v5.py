#!/usr/bin/env python3
"""
E.ON Next Tariff Scraper v5.2 - UNDETECTED CHROME
- Only picks residential addresses (starting with number)
- Handles "already supply" popup
- Handles "business meter" popup
- Handles prepayment meter - goes back
- Handles Chrome "open app" popup - refreshes
- Handles page refresh on invalid address
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
    "AB24 3EN": 5,
    "G20 6NQ": 5,
    "BN2 7HQ": 16,
}


# ============================================
# HUMAN BEHAVIOR SIMULATION
# ============================================

def human_delay(min_sec=0.5, max_sec=2.0):
    delay = random.betavariate(2, 5) * (max_sec - min_sec) + min_sec
    time.sleep(delay)


def long_delay():
    time.sleep(random.uniform(3, 6))


def human_type(element, text):
    for char in text:
        element.send_keys(char)
        if random.random() < 0.1:
            time.sleep(random.uniform(0.2, 0.5))
        else:
            time.sleep(random.uniform(0.05, 0.15))


def human_click(driver, element):
    try:
        driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", element)
        time.sleep(random.uniform(0.3, 0.7))
        actions = ActionChains(driver)
        actions.move_to_element(element).pause(random.uniform(0.1, 0.3)).click().perform()
    except Exception:
        try:
            driver.execute_script("arguments[0].click();", element)
        except:
            element.click()


def random_scroll(driver):
    scroll_amount = random.randint(100, 300)
    driver.execute_script(f"window.scrollBy(0, {scroll_amount});")
    time.sleep(random.uniform(0.3, 0.8))


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
    
    if headless:
        options.add_argument("--headless=new")
    
    driver = uc.Chrome(options=options, use_subprocess=True)
    driver.set_page_load_timeout(60)
    driver.implicitly_wait(5)
    
    return driver


# ============================================
# HELPER FUNCTIONS
# ============================================

def close_popup(driver):
    """Close any popup (like 'already supply' modal) by clicking X."""
    try:
        # Look for close buttons (X)
        close_selectors = [
            "button[aria-label*='close' i]",
            "button[aria-label*='Close' i]",
            "[class*='close']",
            "[class*='Close']",
            "button svg",  # Often X is an SVG inside button
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
                        time.sleep(0.5)
                        return True
            except:
                continue
        
        # Also try clicking outside the modal
        try:
            overlay = driver.find_element(By.CSS_SELECTOR, "[class*='overlay'], [class*='backdrop']")
            if overlay.is_displayed():
                driver.execute_script("arguments[0].click();", overlay)
                print(f"    ✓ Closed popup (overlay)")
                time.sleep(0.5)
                return True
        except:
            pass
            
    except Exception as e:
        pass
    
    return False


def check_already_supply_popup(driver):
    """Check if 'we already supply this property' popup appeared."""
    try:
        page_text = driver.page_source.lower()
        if 'already supply this property' in page_text or 'lets get you to the right place' in page_text:
            return True
    except:
        pass
    return False


def check_business_meter_popup(driver):
    """Check if 'business meter' popup appeared."""
    try:
        page_text = driver.page_source.lower()
        if 'business meter' in page_text or 'business account' in page_text or 'commercial meter' in page_text or 'business customer' in page_text:
            return True
    except:
        pass
    return False


def check_chrome_app_popup(driver):
    """Check if Chrome 'open app' popup appeared and handle it."""
    try:
        # Check for Chrome alert
        try:
            alert = driver.switch_to.alert
            alert.dismiss()
            print(f"    ✓ Dismissed Chrome alert")
            return True
        except:
            pass
        
        # Check page for app-related text
        page_text = driver.page_source.lower()
        if 'open app' in page_text or 'wants to open' in page_text or 'external protocol' in page_text:
            return True
    except:
        pass
    return False


def check_postcode_empty(driver, expected_postcode):
    """Check if postcode field is empty or different (page reset)."""
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


def get_valid_addresses(options, start_idx, tried_addresses):
    """Get list of valid residential addresses (starting with number, not flats)."""
    valid = []
    skip_words = ['flat', 'apartment', 'floor', 'unit', 'suite', 'apt', 'room', 'basement']
    
    for i in range(start_idx, len(options)):
        if i in tried_addresses:
            continue
        try:
            text = options[i].text.strip()
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


def enter_postcode(driver, postcode):
    """Enter postcode and wait for dropdown."""
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
    human_delay(0.3, 0.6)
    postcode_input.clear()
    human_delay(0.2, 0.4)
    human_type(postcode_input, postcode)
    human_delay(2, 4)
    
    return postcode_input


def select_options_after_address(driver):
    """Select fuel type, EV no, usage level."""
    # Fuel type
    try:
        elec_gas = driver.find_element(By.XPATH, "//*[contains(text(), 'Electricity and gas')]")
        if elec_gas.is_displayed():
            human_click(driver, elec_gas)
            human_delay(0.8, 1.5)
    except:
        pass
    
    # EV - No
    try:
        no_buttons = driver.find_elements(By.XPATH, "//*[text()='No']")
        if no_buttons:
            human_click(driver, no_buttons[-1])
            human_delay(0.5, 1)
    except:
        pass
    
    # Usage level
    try:
        usage = driver.find_element(By.XPATH, "//*[contains(text(), '1-2 bedrooms')]")
        if usage.is_displayed():
            human_click(driver, usage)
            human_delay(0.8, 1.5)
    except:
        pass


def click_see_prices(driver):
    """Click the see prices / get quote button."""
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
# RATE EXTRACTION
# ============================================

def extract_rates(driver) -> dict:
    rates = {}
    
    try:
        page_text = driver.find_element(By.TAG_NAME, "body").text
        
        # Debug: save page text
        with open("debug_page_text.txt", "w", encoding="utf-8") as f:
            f.write(page_text)
        print(f"    📄 Saved page text to debug_page_text.txt")
        
        # Tariff name
        for pattern in [r'(Next Fixed \d+m v\d+)', r'(Next Flex[^\n]*)', r'(Next Online v\d+)']:
            match = re.search(pattern, page_text, re.I)
            if match:
                rates['tariff_name'] = match.group(1).strip()
                break
        
        # Exit fee
        match = re.search(r'£(\d+)\s*(?:per fuel\s*)?exit fee|exit fee[:\s]*£(\d+)', page_text, re.I)
        if match:
            rates['exit_fee_gbp'] = int(match.group(1) or match.group(2))
        
        # Electricity rates
        patterns = [
            (r'electricity.*?day.*?(\d+\.?\d*)\s*p', 'elec_day_rate_p'),
            (r'day\s*rate.*?(\d+\.?\d*)\s*p', 'elec_day_rate_p'),
            (r'electricity.*?night.*?(\d+\.?\d*)\s*p', 'elec_night_rate_p'),
            (r'night\s*rate.*?(\d+\.?\d*)\s*p', 'elec_night_rate_p'),
            (r'electricity.*?unit\s*rate.*?(\d+\.?\d*)\s*p', 'elec_unit_rate_p'),
            (r'electricity.*?(\d+\.?\d*)\s*p\s*(?:per\s*)?kWh', 'elec_unit_rate_p'),
            (r'electricity.*?standing.*?(\d+\.?\d*)\s*p', 'elec_standing_p'),
            (r'gas.*?unit\s*rate.*?(\d+\.?\d*)\s*p', 'gas_unit_rate_p'),
            (r'gas.*?(\d+\.?\d*)\s*p\s*(?:per\s*)?kWh', 'gas_unit_rate_p'),
            (r'gas.*?standing.*?(\d+\.?\d*)\s*p', 'gas_standing_p'),
        ]
        
        for pattern, key in patterns:
            if key not in rates:
                match = re.search(pattern, page_text, re.I | re.S)
                if match:
                    rates[key] = float(match.group(1))
        
        # Fallback: find any prices
        if not rates:
            all_prices = re.findall(r'(\d+\.\d+)\s*p', page_text)
            if all_prices:
                print(f"    Found prices on page: {all_prices[:10]}")
        
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
        time.sleep(random.uniform(1, 3))
        
        driver.get(EON_QUOTE_URL)
        long_delay()
        print(f"    ✓ Page loaded")
        random_scroll(driver)
        
        # Handle cookies
        try:
            cookie_btn = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler"))
            )
            human_click(driver, cookie_btn)
            print(f"    ✓ Accepted cookies")
            human_delay(1, 2)
        except:
            pass
        
        # STEP 2: Enter postcode
        print(f"\n  [STEP 2] Entering postcode: {postcode}")
        enter_postcode(driver, postcode)
        print(f"    ✓ Typed postcode")
        
        # STEP 3: Select address
        print(f"\n  [STEP 3] Selecting address...")
        
        try:
            address_dropdown = WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.TAG_NAME, "select"))
            )
            print(f"    ✓ Dropdown found")
        except:
            raise Exception("Address dropdown did not appear")
        
        human_delay(0.5, 1)
        select = Select(address_dropdown)
        options = select.options
        
        start_idx = POSTCODE_START_INDEX.get(postcode, 1)
        valid_addresses = get_valid_addresses(options, start_idx, tried_addresses)
        
        if not valid_addresses:
            raise Exception("No valid residential addresses found")
        
        print(f"    Found {len(valid_addresses)} valid addresses")
        
        # Try addresses until one works
        success = False
        max_address_tries = min(10, len(valid_addresses))
        
        for addr_idx, addr_text in valid_addresses[:max_address_tries]:
            print(f"\n    Trying #{addr_idx}: {addr_text[:50]}...")
            tried_addresses.add(addr_idx)
            
            human_delay(0.5, 1)
            select.select_by_index(addr_idx)
            human_delay(1.5, 2.5)
            
            # Check for Chrome app popup - refresh and restart
            if check_chrome_app_popup(driver):
                print(f"    ⚠ Chrome app popup - refreshing...")
                driver.refresh()
                human_delay(2, 3)
                # Re-enter postcode and restart
                enter_postcode(driver, postcode)
                human_delay(2, 3)
                try:
                    address_dropdown = WebDriverWait(driver, 10).until(
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
                human_delay(1, 2)
                
                # Need to re-get dropdown
                try:
                    address_dropdown = driver.find_element(By.TAG_NAME, "select")
                    select = Select(address_dropdown)
                except:
                    # If dropdown gone, re-enter postcode
                    print(f"    Re-entering postcode...")
                    enter_postcode(driver, postcode)
                    human_delay(2, 3)
                    address_dropdown = WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.TAG_NAME, "select"))
                    )
                    select = Select(address_dropdown)
                continue
            
            # Check for business meter popup
            if check_business_meter_popup(driver):
                print(f"    ⚠ Business meter - closing popup...")
                close_popup(driver)
                human_delay(1, 2)
                
                # Re-get dropdown or re-enter postcode
                try:
                    address_dropdown = driver.find_element(By.TAG_NAME, "select")
                    select = Select(address_dropdown)
                except:
                    print(f"    Re-entering postcode...")
                    enter_postcode(driver, postcode)
                    human_delay(2, 3)
                    address_dropdown = WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.TAG_NAME, "select"))
                    )
                    select = Select(address_dropdown)
                continue
            
            # Check for prepayment meter
            try:
                page_text = driver.page_source.lower()
                if 'prepayment' in page_text or 'prepay' in page_text or 'pay as you go' in page_text:
                    print(f"    ⚠ Prepayment meter - going back...")
                    driver.back()
                    human_delay(1.5, 2.5)
                    # Re-enter postcode
                    enter_postcode(driver, postcode)
                    human_delay(2, 3)
                    address_dropdown = WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.TAG_NAME, "select"))
                    )
                    select = Select(address_dropdown)
                    continue
            except:
                pass
            
            # STEP 4-6: Select options
            print(f"    Selecting options...")
            select_options_after_address(driver)
            
            # STEP 7: Click see prices
            print(f"    Clicking see prices...")
            random_scroll(driver)
            human_delay(1, 2)
            click_see_prices(driver)
            
            print(f"    Waiting for results...")
            long_delay()
            
            # Check if page reset (postcode empty)
            is_empty, pc_input = check_postcode_empty(driver, postcode)
            if is_empty:
                print(f"    ⚠ Page reset - address invalid, trying next...")
                if pc_input:
                    # Re-enter postcode
                    human_click(driver, pc_input)
                    pc_input.clear()
                    human_type(pc_input, postcode)
                    human_delay(2, 3)
                    
                    # Re-get dropdown
                    try:
                        address_dropdown = WebDriverWait(driver, 10).until(
                            EC.presence_of_element_located((By.TAG_NAME, "select"))
                        )
                        select = Select(address_dropdown)
                    except:
                        pass
                continue
            
            # Check for "already supply" popup again
            if check_already_supply_popup(driver):
                print(f"    ⚠ Already EON customer popup - trying next...")
                close_popup(driver)
                human_delay(1, 2)
                
                # Re-enter postcode
                is_empty, pc_input = check_postcode_empty(driver, postcode)
                if is_empty and pc_input:
                    human_click(driver, pc_input)
                    pc_input.clear()
                    human_type(pc_input, postcode)
                    human_delay(2, 3)
                    
                    try:
                        address_dropdown = WebDriverWait(driver, 10).until(
                            EC.presence_of_element_located((By.TAG_NAME, "select"))
                        )
                        select = Select(address_dropdown)
                    except:
                        pass
                continue
            
            # If we got here, address worked!
            success = True
            print(f"    ✓ Address #{addr_idx} worked!")
            break
        
        if not success:
            raise Exception("No valid address found after multiple tries")
        
        # STEP 8: Expand details
        print(f"\n  [STEP 8] Expanding details...")
        human_delay(1, 2)
        
        for text in ["More info", "View details", "See details"]:
            try:
                btn = driver.find_element(By.XPATH, f"//*[contains(text(), '{text}')]")
                if btn.is_displayed():
                    human_click(driver, btn)
                    print(f"    ✓ Expanded")
                    break
            except:
                continue
        
        human_delay(2, 3)
        driver.save_screenshot(f"screenshots/eon_{region.replace(' ', '_')}_final.png")
        
        # STEP 9: Extract rates
        print(f"\n  [STEP 9] Extracting rates...")
        
        rates = extract_rates(driver)
        
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
            wait = 30 * (2 ** (attempt - 1)) + random.randint(0, 30)
            print(f"\n  ⏳ Waiting {wait}s...")
            time.sleep(wait)
    
    return result


def run_scraper(headless=False, test_postcode=None, wait_secs=30, max_retries=3):
    results = []
    
    if test_postcode:
        postcodes = {k: v for k, v in DNO_POSTCODES.items() if v == test_postcode}
        if not postcodes:
            postcodes = {"Test": test_postcode}
    else:
        postcodes = DNO_POSTCODES
    
    items = list(postcodes.items())
    batches = [items[i:i+3] for i in range(0, len(items), 3)]
    
    for batch_idx, batch in enumerate(batches):
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
                else:
                    print(f"  ✗ Failed")
                
                if i < len(batch) - 1:
                    wait = wait_secs + random.randint(-10, 20)
                    print(f"\n  ⏳ Waiting {wait}s...")
                    time.sleep(wait)
        
        finally:
            if driver:
                driver.quit()
                print("  Browser closed")
        
        if batch_idx < len(batches) - 1:
            batch_wait = 120 + random.randint(0, 60)
            print(f"\n  🔄 Batch done. Waiting {batch_wait}s...")
            time.sleep(batch_wait)
    
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
    
    fields = ["supplier", "region", "postcode", "scraped_at", "attempt", "tariff_name",
              "elec_day_rate_p", "elec_night_rate_p", "elec_unit_rate_p", "elec_standing_p",
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
    
    parser = argparse.ArgumentParser(description="E.ON Next Scraper v5.1")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--test", type=str, help="Test single postcode")
    parser.add_argument("--wait", type=int, default=30)
    parser.add_argument("--retries", type=int, default=3)
    args = parser.parse_args()
    
    os.makedirs("screenshots", exist_ok=True)
    
    print("="*60)
    print("E.ON NEXT SCRAPER v5.2 - UNDETECTED CHROME")
    print("="*60)
    print("✓ Only picks residential addresses (starting with number)")
    print("✓ Handles 'already supply' popup")
    print("✓ Handles 'business meter' popup")
    print("✓ Handles prepayment meter")
    print("✓ Handles Chrome 'open app' popup")
    print("✓ Handles page reset on invalid address")
    print()
    
    results = run_scraper(args.headless, args.test, args.wait, args.retries)
    save_results(results)
    
    input("\nPress Enter to exit...")


if __name__ == "__main__":
    main()
