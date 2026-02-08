#!/usr/bin/env python3
"""
E.ON Next Tariff Scraper v6 - PLAYWRIGHT EDITION
Migrated from Selenium/undetected-chrome to Playwright for better compatibility
- Handles residential address selection
- Handles "already supply" popup
- Handles "business meter" popup
- Handles prepayment meter detection
- Handles Chrome "open app" popup
- Handles page refresh on invalid address
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

EON_QUOTE_URL = "https://www.eonnext.com/dashboard/journey/get-a-quote"

POSTCODE_START_INDEX = {
    "AB24 3EN": 5,
    "G20 6NQ": 5,
    "BN2 7HQ": 16,
}

# Pool of realistic user agents
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
window.chrome = { runtime: {}, loadTimes: function() {}, csi: function() {}, app: {} };
"""

# ============================================
# HELPER FUNCTIONS
# ============================================

def human_delay(min_ms=500, max_ms=2000):
    delay = random.betavariate(2, 5) * (max_ms - min_ms) + min_ms
    time.sleep(delay / 1000)

def typing_delay():
    return random.randint(50, 120)

def is_residential_address(text: str) -> bool:
    """Check if address is residential (starts with number, no flats)."""
    if not text or not text[0].isdigit():
        return False

    skip_words = ['flat', 'apartment', 'floor', 'unit', 'suite', 'apt', 'room', 'basement']
    return not any(w in text.lower() for w in skip_words)

def check_popup_issues(page) -> dict:
    """Check for various popup/blocker issues."""
    try:
        text = page.inner_text('body').lower()

        return {
            'already_supply': 'already supply this property' in text or 'lets get you to the right place' in text,
            'business_meter': 'business meter' in text or 'business account' in text or 'commercial meter' in text,
            'prepayment': 'prepayment' in text or 'pre-payment' in text or 'pay as you go' in text,
            'missing_out': "what you'll be missing" in text or "what you will be missing" in text,
        }
    except:
        return {'already_supply': False, 'business_meter': False, 'prepayment': False, 'missing_out': False}

def close_popup(page):
    """Try to close any popup."""
    close_selectors = [
        "button[aria-label*='close' i]",
        "button[aria-label*='Close' i]",
        "[class*='close']",
        "button:has-text('No thanks')",
        "button:has-text('Continue')",
        "button:has-text('Close')",
    ]

    for selector in close_selectors:
        try:
            btn = page.locator(selector).first
            if btn.is_visible(timeout=1000):
                btn.click()
                print(f"    ✓ Closed popup")
                human_delay(500, 1000)
                return True
        except:
            continue

    return False

# ============================================
# MAIN SCRAPER
# ============================================

def scrape_eon(browser, postcode: str, region: str, attempt: int = 1) -> dict:
    """Scrape E.ON Next tariffs for a single postcode."""

    result = {
        "supplier": "eon_next",
        "region": region,
        "postcode": postcode,
        "scraped_at": datetime.now().isoformat(),
        "tariffs": [],
        "attempt": attempt,
    }

    context = None
    tried_addresses = set()

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

        # STEP 1: Load page
        print(f"\n  [1] Loading E.ON Next...")
        page.goto(EON_QUOTE_URL, timeout=45000, wait_until="domcontentloaded")
        human_delay(2000, 4000)

        # Handle cookies
        try:
            cookie_btn = page.locator('#onetrust-accept-btn-handler').first
            if cookie_btn.is_visible(timeout=3000):
                cookie_btn.click()
                print(f"    ✓ Accepted cookies")
                human_delay(1000, 2000)
        except:
            pass

        page.screenshot(path=f"screenshots/eon_{region.replace(' ', '_')}_01_loaded.png")

        # STEP 2: Enter postcode
        print(f"\n  [2] Entering postcode: {postcode}")

        postcode_selectors = [
            'input[name*="postcode" i]',
            'input[placeholder*="postcode" i]',
            'input[type="text"]'
        ]

        postcode_input = None
        for selector in postcode_selectors:
            try:
                postcode_input = page.locator(selector).first
                if postcode_input.is_visible(timeout=2000):
                    break
            except:
                continue

        if not postcode_input:
            raise Exception("Could not find postcode input")

        postcode_input.click()
        human_delay(300, 500)
        postcode_input.fill('')

        for char in postcode:
            postcode_input.type(char, delay=typing_delay())

        print(f"    ✓ Entered postcode")
        human_delay(2000, 3000)

        page.screenshot(path=f"screenshots/eon_{region.replace(' ', '_')}_02_postcode.png")

        # STEP 3: Select address
        print(f"\n  [3] Selecting address...")

        try:
            address_dropdown = page.locator('select').first
            address_dropdown.wait_for(state="visible", timeout=15000)
            print(f"    ✓ Address dropdown found")
        except:
            page.screenshot(path=f"screenshots/eon_{region.replace(' ', '_')}_no_dropdown.png")
            raise Exception("Address dropdown did not appear")

        human_delay(1000, 2000)

        # Get options
        options = address_dropdown.locator('option').all()
        print(f"    Found {len(options)} addresses")

        start_idx = POSTCODE_START_INDEX.get(postcode, 1)
        max_tries = 10
        address_selected = False

        for i in range(start_idx, min(len(options), start_idx + 20)):
            if i in tried_addresses:
                continue

            try:
                addr_text = options[i].text_content().strip()

                if not is_residential_address(addr_text):
                    print(f"    [{i}] Skip non-residential: {addr_text[:40]}")
                    continue

                print(f"    [{i}] Trying: {addr_text[:50]}...")
                tried_addresses.add(i)

                address_dropdown.select_option(index=i)
                human_delay(2000, 3000)

                page.screenshot(path=f"screenshots/eon_{region.replace(' ', '_')}_after_addr_{i}.png")

                # Check for issues
                issues = check_popup_issues(page)

                if issues['already_supply']:
                    print(f"    ⚠ Already EON customer popup - closing...")
                    close_popup(page)
                    human_delay(1000, 2000)
                    continue

                if issues['business_meter']:
                    print(f"    ⚠ Business meter detected - trying next address")
                    continue

                if issues['prepayment']:
                    print(f"    ⚠ Prepayment meter - trying next address")
                    continue

                if issues['missing_out']:
                    print(f"    ⚠ 'What you'll be missing' popup - closing...")
                    close_popup(page)
                    human_delay(1000, 2000)

                # Check if we have tariff options visible
                try:
                    # Look for tariff cards or buttons
                    tariff_check = page.locator('text=/tariff/i, button:has-text("View"), button:has-text("Select")').first
                    if tariff_check.is_visible(timeout=5000):
                        print(f"    ✓ Address accepted - tariffs loading")
                        address_selected = True
                        break
                except:
                    print(f"    ✗ No tariffs visible for this address")
                    continue

            except Exception as e:
                print(f"    ✗ Error with address {i}: {str(e)[:50]}")
                continue

        if not address_selected:
            raise Exception(f"No valid address found after trying {len(tried_addresses)} addresses")

        # Wait for tariffs to load
        human_delay(3000, 5000)
        page.screenshot(path=f"screenshots/eon_{region.replace(' ', '_')}_tariffs.png")

        # STEP 4: Extract tariff data
        print(f"\n  [4] Extracting tariff data...")

        page_text = page.inner_text('body')

        # Find tariff name
        tariff_name = None
        tariff_patterns = [
            r'(Next Flex)',
            r'(Next Drive)',
            r'(Variable\s*Tariff)',
            r'(Fixed\s*Tariff)',
        ]
        for pattern in tariff_patterns:
            match = re.search(pattern, page_text, re.I)
            if match:
                tariff_name = match.group(1)
                break

        # Extract rates - look for prices in pence
        elec_unit = None
        elec_standing = None
        gas_unit = None
        gas_standing = None

        # Electricity unit rate (look for p/kWh)
        elec_match = re.search(r'electricity.*?(\d+\.?\d*)\s*p\s*/?\s*kWh', page_text, re.I | re.S)
        if elec_match:
            elec_unit = float(elec_match.group(1))

        # Electricity standing charge
        elec_sc_match = re.search(r'electricity.*?standing.*?(\d+\.?\d*)\s*p\s*/?\s*day', page_text, re.I | re.S)
        if elec_sc_match:
            elec_standing = float(elec_sc_match.group(1))

        # Gas unit rate
        gas_match = re.search(r'gas.*?(\d+\.?\d*)\s*p\s*/?\s*kWh', page_text, re.I | re.S)
        if gas_match:
            gas_unit = float(gas_match.group(1))

        # Gas standing charge
        gas_sc_match = re.search(r'gas.*?standing.*?(\d+\.?\d*)\s*p\s*/?\s*day', page_text, re.I | re.S)
        if gas_sc_match:
            gas_standing = float(gas_sc_match.group(1))

        # Exit fee
        exit_fee = "£0"
        exit_match = re.search(r'exit\s*fee.*?£(\d+)', page_text, re.I)
        if exit_match:
            exit_fee = f"£{exit_match.group(1)}"

        if tariff_name and (elec_unit or gas_unit):
            tariff = {
                'tariff_name': tariff_name,
                'elec_unit_rate_p': elec_unit,
                'elec_standing_p': elec_standing,
                'gas_unit_rate_p': gas_unit,
                'gas_standing_p': gas_standing,
                'exit_fee': exit_fee,
            }
            result['tariffs'].append(tariff)

            print(f"    ✓ Found: {tariff_name}")
            print(f"      Elec: {elec_unit}p/kWh, {elec_standing}p/day")
            print(f"      Gas: {gas_unit}p/kWh, {gas_standing}p/day")
            print(f"      Exit fee: {exit_fee}")
        else:
            result['error'] = "Could not extract tariff rates"
            print(f"    ✗ No tariff data found")

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
                page.screenshot(path=f"screenshots/eon_{region.replace(' ', '_')}_final.png")
            except:
                pass
            context.close()

    return result


def scrape_with_retry(browser, postcode: str, region: str, max_attempts: int = 3) -> dict:
    """Retry with exponential backoff."""
    for attempt in range(1, max_attempts + 1):
        print(f"\n  🔄 Attempt {attempt}/{max_attempts}")

        result = scrape_eon(browser, postcode, region, attempt)

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

def run_scraper(headless: bool = False, test_postcode: str = None, wait_secs: int = 30, max_retries: int = 3):
    """Main runner."""

    results = []
    consecutive_failures = 0

    if test_postcode:
        postcodes = {k: v for k, v in DNO_POSTCODES.items() if v == test_postcode}
        if not postcodes:
            postcodes = {"Test": test_postcode}
    else:
        postcodes = DNO_POSTCODES

    os.makedirs("screenshots", exist_ok=True)

    # Split into batches
    items = list(postcodes.items())
    batches = [
        items[0:3],   # Batch 1
        items[3:6],   # Batch 2
        items[6:9],   # Batch 3
        items[9:12],  # Batch 4
        items[12:14], # Batch 5
    ]

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

        for batch_idx, batch in enumerate(batches):
            print(f"\n{'#'*60}")
            print(f"  BATCH {batch_idx + 1}/{len(batches)} - {len(batch)} regions")
            print('#'*60)

            for i, (region, postcode) in enumerate(batch):
                print(f"\n{'='*50}")
                print(f"  [{i+1}/{len(batch)}] {region} ({postcode})")
                print('='*50)

                result = scrape_with_retry(browser, postcode, region, max_retries)
                results.append(result)

                # Track success/failure
                if result.get('tariffs'):
                    print(f"  ✓ Success!")
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
                if i < len(batch) - 1:
                    wait = wait_secs + random.randint(-10, 20)
                    print(f"\n  ⏳ Waiting {wait}s...")
                    time.sleep(wait)

            # Longer wait between batches
            if batch_idx < len(batches) - 1:
                batch_wait = 120 + random.randint(0, 60)
                print(f"\n  🔄 Batch done. Waiting {batch_wait}s...")
                time.sleep(batch_wait)

        browser.close()

    return results


def save_results(results: list):
    """Save JSON and CSV."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    # JSON
    with open(f"eon_tariffs_{ts}.json", "w") as f:
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

    with open(f"eon_tariffs_{ts}.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "supplier", "region", "postcode", "scraped_at", "attempt",
            "tariff_name", "exit_fee", "elec_unit_rate_p", "elec_standing_p",
            "gas_unit_rate_p", "gas_standing_p", "error"
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
    parser.add_argument("--wait", type=int, default=30, help="Wait between regions")
    parser.add_argument("--retries", type=int, default=3, help="Max retries per region")
    args = parser.parse_args()

    print("="*60)
    print("E.ON NEXT SCRAPER v6 - PLAYWRIGHT EDITION")
    print("="*60)

    results = run_scraper(
        headless=args.headless,
        test_postcode=args.test,
        wait_secs=args.wait,
        max_retries=args.retries
    )
    save_results(results)
    print("\n✓ Done!")


if __name__ == "__main__":
    main()
