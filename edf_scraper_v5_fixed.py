#!/usr/bin/env python3
"""
EDF Energy Tariff Scraper v5
Fixed: Always re-enter postcode on every retry
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

POSTCODE_START_INDEX = {
    "BN2 7HQ": 16,
    "AB24 3EN": 8,
    "G20 6NQ": 8,
    "L3 2BN": 8,
    "NE2 1UY": 8,
    "N5 2SD": 5,
}

EMAIL = "switch.pilots@gmail.com"
URL = "https://www.edfenergy.com/quote/choose-tariff"

def remove_onetrust_overlay(page):
    """Forcibly remove OneTrust cookie overlay that blocks clicks."""
    try:
        page.evaluate("""
            () => {
                const darkFilter = document.querySelector('.onetrust-pc-dark-filter');
                if (darkFilter) darkFilter.remove();
                const oneTrust = document.querySelector('#onetrust-consent-sdk');
                if (oneTrust) oneTrust.remove();
                const allOverlays = document.querySelectorAll('[class*="onetrust"]');
                allOverlays.forEach(el => el.remove());
            }
        """)
    except:
        pass

# Any of these = bad address, try next
ADDRESS_PROBLEMS = [
    'already an edf customer',
    'already supply',
    'existing customer',
    'prepayment meter',
    'prepay meter',
    'business meter',
    'business account',
    'smart meter',
    'economy 7',
    'economy 10',
    "can't give you a quote",
    'unable to quote',
    "we've run into an issue",
    "run into an issue",
    "try that again",
    "please try selecting your address again",
    "are you an edf customer",
    "please let us know",
    "please confirm",
    "is this correct",
    "call us to get a quote",
    "please call our",
    "call our energy specialists",
    "business prices",
    "business postcode",
    "business address",
    "my business postcode",
    "step 1 of 7",
]


def human_delay(min_ms=500, max_ms=1500):
    time.sleep(random.randint(min_ms, max_ms) / 1000)


def check_for_problems(page) -> str:
    """Check if page shows any problems."""
    try:
        text = page.inner_text('body').lower()
        for problem in ADDRESS_PROBLEMS:
            if problem in text:
                return problem
    except:
        pass
    return None


def has_dual_fuel(page) -> bool:
    """Check if 'Electricity and Gas' option is visible."""
    try:
        dual = page.locator('text="Electricity and Gas"').first
        return dual.is_visible(timeout=2000)
    except:
        return False


def extract_rates(text: str) -> dict:
    """Extract tariff rates from page text."""
    rates = {}
    
    # Tariff name
    m = re.search(r'(Simply Fixed\s*\w+\d+v?\d*)', text, re.I)
    if m:
        rates['tariff_name'] = m.group(1).strip()
    else:
        for pattern in [r'(Standard Variable)', r'(Price Tracker)']:
            m = re.search(pattern, text, re.I)
            if m:
                rates['tariff_name'] = m.group(1).strip()
                break
    
    # Exit fee
    m = re.search(r'Exit fee\s*£?(\d+(?:\.\d+)?)', text, re.I)
    if m:
        rates['exit_fee'] = f"£{m.group(1)}"
    elif 'no exit fee' in text.lower():
        rates['exit_fee'] = "£0"
    
    # Gas section
    gas_match = re.search(r'Gas supply(.*?)(?:Electricity supply|How we worked|All rates|$)', text, re.I | re.S)
    if gas_match:
        gas_text = gas_match.group(1)
        m = re.search(r'Unit rate\s*(\d+\.?\d*)\s*p', gas_text, re.I)
        if m:
            rates['gas_unit_rate_p'] = float(m.group(1))
        m = re.search(r'Standing charge\s*(\d+\.?\d*)\s*p', gas_text, re.I)
        if m:
            rates['gas_standing_p'] = float(m.group(1))
    
    # Electricity section
    elec_match = re.search(r'Electricity supply(.*?)(?:Gas supply|How we worked|All rates|$)', text, re.I | re.S)
    if elec_match:
        elec_text = elec_match.group(1)
        m = re.search(r'Unit rate\s*(\d+\.?\d*)\s*p', elec_text, re.I)
        if m:
            rates['elec_unit_rate_p'] = float(m.group(1))
        m = re.search(r'Standing charge\s*(\d+\.?\d*)\s*p', elec_text, re.I)
        if m:
            rates['elec_standing_p'] = float(m.group(1))
    
    if rates.get('elec_unit_rate_p') or rates.get('gas_unit_rate_p'):
        return rates
    return {}


def reset_and_search(page, postcode: str) -> bool:
    """Reset to fresh state: load page, cookies, enter postcode, search."""
    try:
        print(f"    → Resetting page and re-entering postcode...")
        page.goto(URL, wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)
        
        # Aggressive OneTrust/cookie handling
        cookie_selectors = [
            'button#onetrust-accept-btn-handler',
            'button.onetrust-close-btn-handler',
            'button:has-text("Accept All Cookies")',
            'button:has-text("Accept all")',
        ]
        
        for selector in cookie_selectors:
            try:
                btn = page.locator(selector).first
                if btn.is_visible(timeout=2000):
                    btn.click(timeout=5000)
                    time.sleep(1)
                    break
            except:
                pass
        
        # Forcibly remove overlay
        try:
            page.evaluate("""
                () => {
                    const darkFilter = document.querySelector('.onetrust-pc-dark-filter');
                    if (darkFilter) darkFilter.remove();
                    const oneTrust = document.querySelector('#onetrust-consent-sdk');
                    if (oneTrust) oneTrust.remove();
                }
            """)
        except:
            pass
        
        time.sleep(1)
        
        # Enter postcode
        postcode_input = page.locator('input[type="text"]').first
        postcode_input.wait_for(state="visible", timeout=5000)
        postcode_input.fill(postcode)
        time.sleep(0.5)
        
        # Click search
        page.click('button:has-text("Search")')
        time.sleep(4)
        
        return True
    except Exception as e:
        print(f"    ✗ Reset failed: {e}")
        return False


def scrape_edf(browser, postcode: str, region: str) -> dict:
    """Scrape EDF tariffs for a single postcode."""
    
    result = {
        "supplier": "edf",
        "region": region,
        "postcode": postcode,
        "scraped_at": datetime.now().isoformat(),
        "tariffs": [],
    }
    
    context = browser.new_context(
        viewport={"width": 1920, "height": 1080},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36",
    )
    page = context.new_page()
    
    start_idx = POSTCODE_START_INDEX.get(postcode, 1)
    current_idx = start_idx
    max_attempts = 15
    
    try:
        # INITIAL LOAD
        print(f"\n  [STEP 1] Loading EDF website...")
        page.goto(URL, wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)
        print(f"    ✓ Page loaded")
        
        # COOKIES - AGGRESSIVE ONETRUST HANDLING
        print(f"\n  [STEP 2] Handling cookies and OneTrust overlay...")
        time.sleep(2)  # Let OneTrust load
        
        # Method 1: Try to click accept buttons
        cookie_selectors = [
            'button#onetrust-accept-btn-handler',
            'button.onetrust-close-btn-handler',
            'button:has-text("Accept All Cookies")',
            'button:has-text("Accept all")',
            'button:has-text("Accept")',
            '#onetrust-accept-btn-handler',
        ]
        
        clicked = False
        for selector in cookie_selectors:
            try:
                btn = page.locator(selector).first
                if btn.is_visible(timeout=2000):
                    btn.click(timeout=5000)
                    print(f"    ✓ Clicked cookie button: {selector}")
                    clicked = True
                    time.sleep(1)
                    break
            except:
                pass
        
        # Method 2: Forcibly remove OneTrust overlay using JavaScript
        try:
            page.evaluate("""
                () => {
                    // Remove dark filter overlay
                    const darkFilter = document.querySelector('.onetrust-pc-dark-filter');
                    if (darkFilter) darkFilter.remove();
                    
                    // Remove entire OneTrust SDK
                    const oneTrust = document.querySelector('#onetrust-consent-sdk');
                    if (oneTrust) oneTrust.remove();
                    
                    // Remove any other overlays
                    const overlays = document.querySelectorAll('[class*="onetrust"]');
                    overlays.forEach(el => el.remove());
                }
            """)
            print(f"    ✓ Removed OneTrust overlay via JavaScript")
        except:
            pass
        
        if not clicked:
            print(f"    No cookie banner found (or already dismissed)")
        
        time.sleep(1)  # Let page settle after cookie handling
        
        # POSTCODE
        print(f"\n  [STEP 3] Entering postcode: {postcode}")
        postcode_input = page.locator('input[type="text"]').first
        postcode_input.wait_for(state="visible", timeout=10000)
        postcode_input.fill(postcode)
        print(f"    ✓ Entered postcode")
        time.sleep(0.5)
        
        # CRITICAL: Remove OneTrust overlay one more time before clicking Search
        remove_onetrust_overlay(page)
        
        page.click('button:has-text("Search")')
        print(f"    ✓ Clicked Search")
        time.sleep(4)
        
        page.screenshot(path=f"screenshots/edf_{region.replace(' ', '_')}_after_search.png")
        
        # ADDRESS SELECTION LOOP
        found_good_address = False
        
        while not found_good_address and current_idx < start_idx + max_attempts:
            print(f"\n  [STEP 4] Trying address #{current_idx}...")
            
            # Open dropdown
            page.keyboard.press("Escape")
            time.sleep(0.3)
            
            dropdown_opened = False
            for selector in ['text="Select address"', '[class*="select"]']:
                try:
                    dropdown = page.locator(selector).first
                    if dropdown.is_visible(timeout=2000):
                        dropdown.click()
                        dropdown_opened = True
                        time.sleep(1.5)
                        break
                except:
                    continue
            
            if not dropdown_opened:
                # Try by position
                try:
                    label = page.locator('text="Select your address"').first
                    if label.is_visible(timeout=2000):
                        box = label.bounding_box()
                        if box:
                            page.mouse.click(box['x'] + 100, box['y'] + 60)
                            dropdown_opened = True
                            time.sleep(1.5)
                except:
                    pass
            
            if not dropdown_opened:
                print(f"    ✗ Could not open dropdown")
                current_idx += 1
                reset_and_search(page, postcode)
                continue
            
            print(f"    ✓ Opened dropdown")
            
            # Navigate to address
            page.keyboard.press("Home")
            time.sleep(0.3)
            for _ in range(current_idx):
                page.keyboard.press("ArrowDown")
                time.sleep(0.2)
            page.keyboard.press("Enter")
            time.sleep(2)
            
            print(f"    ✓ Selected address #{current_idx}")
            page.screenshot(path=f"screenshots/edf_{region.replace(' ', '_')}_addr_{current_idx}.png")
            
            # CHECK FOR PROBLEMS BEFORE CONTINUE
            page_text = page.inner_text('body').lower()
            
            # Business page?
            if 'step 1 of 7' in page_text or 'business prices' in page_text:
                print(f"    ⚠ Business address - skipping")
                current_idx += 1
                reset_and_search(page, postcode)
                continue
            
            # Any other problem?
            problem = check_for_problems(page)
            if problem:
                print(f"    ⚠ Problem: {problem}")
                current_idx += 1
                reset_and_search(page, postcode)
                continue
            
            # CLICK CONTINUE
            print(f"\n  [STEP 5] Clicking Continue...")
            try:
                remove_onetrust_overlay(page)  # Remove overlay before click
                page.click('button:has-text("Continue")', timeout=5000)
                print(f"    ✓ Clicked Continue")
            except:
                print(f"    ✗ No Continue button")
                current_idx += 1
                reset_and_search(page, postcode)
                continue
            
            time.sleep(3)
            page.screenshot(path=f"screenshots/edf_{region.replace(' ', '_')}_after_continue.png")
            
            # CHECK WHERE WE LANDED
            page_text = page.inner_text('body').lower()
            
            # Business page after continue?
            if 'step 1 of 7' in page_text or 'business prices' in page_text:
                print(f"    ⚠ Landed on business page")
                current_idx += 1
                reset_and_search(page, postcode)
                continue
            
            # Problem after continue?
            problem = check_for_problems(page)
            if problem:
                print(f"    ⚠ Problem after continue: {problem}")
                current_idx += 1
                reset_and_search(page, postcode)
                continue
            
            # STEP 6: TRY TO SELECT ELECTRICITY AND GAS - IF NOT THERE, TRY NEXT ADDRESS
            print(f"\n  [STEP 6] Selecting Electricity and Gas...")
            try:
                remove_onetrust_overlay(page)  # Remove overlay
                page.click('text="Electricity and Gas"', timeout=5000)
                print(f"    ✓ Selected Electricity and Gas")
                time.sleep(1)
            except:
                print(f"    ⚠ No 'Electricity and Gas' option - trying next address")
                current_idx += 1
                reset_and_search(page, postcode)
                continue
            
            # Select Medium usage
            try:
                remove_onetrust_overlay(page)  # Remove overlay
                page.click('text="Medium"', timeout=3000)
                print(f"    ✓ Selected Medium usage")
                time.sleep(1)
            except:
                pass
            
            page.keyboard.press("PageDown")
            time.sleep(0.5)
            
            try:
                remove_onetrust_overlay(page)  # Remove overlay
                page.click('button:has-text("Continue")', timeout=5000)
                print(f"    ✓ Clicked Continue")
                time.sleep(3)
            except:
                pass
            
            # EMAIL PAGE
            page_text = page.inner_text('body').lower()
            if 'email' in page_text or 'step 3' in page_text:
                print(f"\n  [STEP 7] Entering email...")
                inputs = page.locator('input').all()
                for inp in inputs:
                    try:
                        if inp.is_visible(timeout=1000):
                            inp_type = inp.get_attribute('type') or 'text'
                            if inp_type in ['text', 'email']:
                                inp.fill(EMAIL)
                                print(f"    ✓ Entered email")
                                break
                    except:
                        continue
                time.sleep(1)
            
            # GET QUOTE
            print(f"\n  [STEP 8] Getting quote...")
            try:
                remove_onetrust_overlay(page)  # Remove overlay
                page.click('button:has-text("Get my quote")', timeout=5000)
                print(f"    ✓ Clicked Get my quote")
            except:
                try:
                    remove_onetrust_overlay(page)  # Remove overlay
                    page.click('button[type="submit"]', timeout=3000)
                    print(f"    ✓ Clicked submit")
                except:
                    pass
            
            time.sleep(5)
            page.screenshot(path=f"screenshots/edf_{region.replace(' ', '_')}_results.png")
            
            # CHECK IF WE GOT RESULTS
            page_text = page.inner_text('body').lower()
            if 'choose the best tariff' in page_text or 'simply fixed' in page_text:
                found_good_address = True
                print(f"    ✓ Got tariff results!")
            else:
                # Check for problems
                problem = check_for_problems(page)
                if problem:
                    print(f"    ⚠ Problem on results: {problem}")
                    current_idx += 1
                    reset_and_search(page, postcode)
                    continue
                
                # Unknown state - might still be okay
                if 'step 4' in page_text or 'tariff' in page_text:
                    found_good_address = True
                else:
                    print(f"    ⚠ Unexpected page state")
                    current_idx += 1
                    reset_and_search(page, postcode)
                    continue
        
        if not found_good_address:
            raise Exception(f"No valid address found after {max_attempts} attempts")
        
        # EXTRACT RATES
        print(f"\n  [STEP 9] Opening tariff details...")
        try:
            page.click('text="See full tariff details"', timeout=5000)
            print(f"    ✓ Opened tariff details")
            time.sleep(2)
        except:
            print(f"    Extracting from main page")
        
        # Scroll to see all rates
        for _ in range(5):
            page.keyboard.press("PageDown")
            time.sleep(0.3)
        
        page.screenshot(path=f"screenshots/edf_{region.replace(' ', '_')}_details.png", full_page=True)
        
        print(f"\n  [STEP 10] Extracting rates...")
        page_text = page.inner_text('body')
        
        with open(f"debug_edf_{region.replace(' ', '_')}.txt", "w", encoding="utf-8") as f:
            f.write(page_text)
        
        rates = extract_rates(page_text)
        if rates:
            result['tariffs'].append(rates)
            print(f"\n    ✓ EXTRACTED:")
            print(f"      Tariff: {rates.get('tariff_name', 'N/A')}")
            print(f"      Exit: {rates.get('exit_fee', 'N/A')}")
            print(f"      Elec: {rates.get('elec_unit_rate_p', 'N/A')}p/kWh, {rates.get('elec_standing_p', 'N/A')}p/day")
            print(f"      Gas: {rates.get('gas_unit_rate_p', 'N/A')}p/kWh, {rates.get('gas_standing_p', 'N/A')}p/day")
        else:
            result['error'] = "Could not extract rates"
            print(f"    ✗ No rates found")
        
        result['address_attempts'] = current_idx - start_idx + 1
        
    except Exception as e:
        result['error'] = str(e)
        print(f"\n  ✗ ERROR: {e}")
        try:
            page.screenshot(path=f"screenshots/edf_{region.replace(' ', '_')}_error.png")
        except:
            pass
    
    finally:
        context.close()
    
    return result


def run_all_regions(browser, postcodes: dict, wait_between: int = 20) -> list:
    results = []
    
    for i, (region, postcode) in enumerate(postcodes.items()):
        print(f"\n{'='*60}")
        print(f"SCRAPING: {region} ({postcode}) [{i+1}/{len(postcodes)}]")
        print('='*60)
        
        result = scrape_edf(browser, postcode, region)
        results.append(result)
        
        with open("edf_tariffs_partial.json", "w") as f:
            json.dump(results, f, indent=2)
        
        if i < len(postcodes) - 1:
            wait = wait_between + random.randint(-5, 10)
            print(f"\n  ⏳ Waiting {wait}s...")
            time.sleep(wait)
    
    return results


def save_results(results: list):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    json_file = f"edf_tariffs_{ts}.json"
    with open(json_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved: {json_file}")
    
    csv_file = f"edf_tariffs_{ts}.csv"
    with open(csv_file, "w", newline="", encoding="utf-8") as f:
        fields = ["supplier", "region", "postcode", "scraped_at", "tariff_name", "exit_fee",
                  "elec_unit_rate_p", "elec_standing_p", "gas_unit_rate_p", "gas_standing_p", 
                  "address_attempts", "error"]
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        
        for r in results:
            row = {
                "supplier": r.get("supplier"),
                "region": r.get("region"),
                "postcode": r.get("postcode"),
                "scraped_at": r.get("scraped_at"),
                "address_attempts": r.get("address_attempts"),
                "error": r.get("error"),
            }
            if r.get("tariffs"):
                row.update(r["tariffs"][0])
            writer.writerow(row)
    
    print(f"Saved: {csv_file}")
    
    print(f"\n{'='*80}")
    print("RESULTS SUMMARY")
    print('='*80)
    print(f"{'Region':<25} {'Tariff':<22} {'Elec':<10} {'Gas':<10} {'Exit':<8}")
    print('-'*80)
    
    success = 0
    for r in results:
        if r.get("tariffs"):
            success += 1
            t = r["tariffs"][0]
            print(f"{r['region']:<25} {t.get('tariff_name', 'N/A')[:21]:<22} {str(t.get('elec_unit_rate_p', 'N/A'))+'p':<10} {str(t.get('gas_unit_rate_p', 'N/A'))+'p':<10} {t.get('exit_fee', 'N/A'):<8}")
        else:
            print(f"{r['region']:<25} {'ERROR':<22} {r.get('error', 'Unknown')[:30]}")
    
    print('-'*80)
    print(f"Success: {success}/{len(results)}")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="EDF Scraper v5")
    parser.add_argument("--test", help="Test single postcode")
    parser.add_argument("--headless", action="store_true", help="Run headless")
    parser.add_argument("--wait", type=int, default=20, help="Wait between regions")
    args = parser.parse_args()
    
    os.makedirs("screenshots", exist_ok=True)
    
    print("="*60)
    print("EDF ENERGY TARIFF SCRAPER v5")
    print("="*60)
    
    if args.test:
        postcodes = {k: v for k, v in DNO_POSTCODES.items() if v == args.test}
        if not postcodes:
            postcodes = {"Test": args.test}
    else:
        postcodes = DNO_POSTCODES
    
    print(f"Regions: {len(postcodes)}")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless, slow_mo=50)
        results = run_all_regions(browser, postcodes, args.wait)
        browser.close()
    
    save_results(results)
    print("\n✓ Done!")


if __name__ == "__main__":
    main()
