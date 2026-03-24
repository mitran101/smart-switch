#!/usr/bin/env python3
"""
E.ON Next Tariff Scraper v6.1 - PLAYWRIGHT EDITION
- Full form flow: postcode → address → fuel type → EV → usage → see prices → expand → extract
- Commercial address filtering (skips kiosks, churches, farms, offices etc.)
- Electricity-only skip (tries next address if no gas meter)
- Scotland start indices tuned to skip student/HMO addresses
- Tariff name: matches "Next " prefix (covers all current E.ON Next tariffs)
- Rate extraction: simple findall for p/kWh and p/day (robust)
"""

import json
import csv
import re
import random
import time
import os
import sys
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
    "AB24 3EN": 10,
    "G20 6NQ": 12,
    "BN2 7HQ": 16,
}

COMMERCIAL_KEYWORDS = [
    'kiosk', 'bt kiosk', ' pcp ', 'church', 'school', 'college', 'university',
    'hotel', 'pub ', ' inn ', 'farm ', 'barn ', 'lodge ', 'office', 'surgery',
    'pharmacy', 'clinic', 'hospital', 'garage ', 'workshop', 'warehouse',
    'limited', ' ltd', ' plc', 'centre', 'center', 'chapel', 'hall ',
    'club ', 'shop ', 'store ', 'restaurant', 'cafe ', 'bar ', 'unit ',
]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
]

STEALTH_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'languages', { get: () => ['en-GB', 'en-US', 'en'] });
window.chrome = { runtime: {}, loadTimes: function() {}, csi: function() {}, app: {} };
"""

# ============================================
# HELPERS
# ============================================

def hd(min_ms=300, max_ms=800):
    time.sleep(random.uniform(min_ms / 1000, max_ms / 1000))

def is_commercial(text):
    tl = text.lower()
    return any(kw in tl for kw in COMMERCIAL_KEYWORDS)

def get_body_text(page):
    try:
        return page.inner_text('body').lower()
    except:
        return ''

def close_any_popup(page):
    for sel in [
        "button[aria-label*='close' i]",
        "button:has-text('No thanks')",
        "button:has-text('Close')",
        "button:has-text('Continue')",
        "[class*='close']:visible",
    ]:
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=800):
                btn.click()
                hd(400, 700)
                return True
        except:
            continue
    return False

def click_text(page, *texts):
    for text in texts:
        try:
            el = page.get_by_text(text, exact=True).first
            if el.is_visible(timeout=1500):
                el.click()
                hd(300, 600)
                return True
        except:
            continue
    return False

def click_text_partial(page, *texts):
    for text in texts:
        try:
            el = page.get_by_text(text, exact=False).first
            if el.is_visible(timeout=1500):
                el.click()
                hd(300, 600)
                return True
        except:
            continue
    return False

# ============================================
# MAIN SCRAPE FUNCTION
# ============================================

def scrape_eon(browser, postcode, region, attempt=1, tried_addresses=None):
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

    context = None
    try:
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=random.choice(USER_AGENTS),
            locale="en-GB",
            timezone_id="Europe/London",
        )
        context.add_init_script(STEALTH_SCRIPT)
        page = context.new_page()

        # STEP 1: Load page
        print(f"\n  [1] Loading page...")
        page.goto(EON_QUOTE_URL, timeout=45000, wait_until="domcontentloaded")
        hd(1500, 2500)

        try:
            btn = page.locator('#onetrust-accept-btn-handler').first
            if btn.is_visible(timeout=3000):
                btn.click()
                print(f"    ✓ Accepted cookies")
                hd(500, 900)
        except:
            pass

        # STEP 2: Enter postcode
        print(f"\n  [2] Entering postcode: {postcode}")
        for sel in ['input[name*="postcode" i]', 'input[placeholder*="postcode" i]', 'input[type="text"]']:
            try:
                inp = page.locator(sel).first
                if inp.is_visible(timeout=2000):
                    inp.click()
                    hd(100, 200)
                    inp.fill(postcode)
                    print(f"    ✓ Entered postcode")
                    break
            except:
                continue
        hd(2000, 3000)

        # STEP 3: Select address
        print(f"\n  [3] Selecting address...")
        try:
            dropdown = page.locator('select').first
            dropdown.wait_for(state="visible", timeout=12000)
        except:
            raise Exception("Address dropdown did not appear")

        hd(500, 900)
        options = dropdown.locator('option').all()
        start_idx = POSTCODE_START_INDEX.get(postcode, 1)
        skip_texts = ['select', 'choose', 'please select']

        # Build valid address list
        valid = []
        for i, opt in enumerate(options):
            if i < start_idx:
                continue
            if i in tried_addresses:
                continue
            try:
                txt = opt.text_content().strip()
                if not txt or any(txt.lower().startswith(s) for s in skip_texts):
                    continue
                if is_commercial(txt):
                    continue
                valid.append((i, txt))
            except:
                continue

        print(f"    Found {len(valid)} valid addresses")
        if not valid:
            raise Exception("No valid residential addresses found")

        success = False
        for addr_idx, addr_text in valid[:20]:
            print(f"\n    Trying #{addr_idx}: {addr_text[:55]}...")
            tried_addresses.add(addr_idx)

            dropdown.select_option(index=addr_idx)
            hd(1500, 2500)

            body = get_body_text(page)

            # Skip electricity-only
            if 'only have electricity at this property' in body or 'only have electricity' in body:
                print(f"    ⚠ Electricity-only - skipping...")
                # Re-enter postcode to reset
                for sel in ['input[name*="postcode" i]', 'input[placeholder*="postcode" i]']:
                    try:
                        inp = page.locator(sel).first
                        if inp.is_visible(timeout=2000):
                            inp.fill('')
                            inp.fill(postcode)
                            hd(1500, 2000)
                            try:
                                dropdown = page.locator('select').first
                                dropdown.wait_for(state="visible", timeout=8000)
                                options = dropdown.locator('option').all()
                            except:
                                pass
                            break
                    except:
                        continue
                continue

            # Already supply popup
            if 'already supply this property' in body or 'lets get you to the right place' in body:
                print(f"    ⚠ Already EON customer - closing...")
                close_any_popup(page)
                hd(500, 800)
                try:
                    dropdown = page.locator('select').first
                    options = dropdown.locator('option').all()
                except:
                    pass
                continue

            # Business meter
            if 'business meter' in body or 'commercial meter' in body:
                print(f"    ⚠ Business meter - skipping...")
                close_any_popup(page)
                hd(300, 600)
                continue

            # Something's gone wrong
            if "something's gone wrong" in body or "something went wrong" in body:
                print(f"    ⚠ E.ON error page - retrying postcode...")
                page.goto(EON_QUOTE_URL, timeout=30000, wait_until="domcontentloaded")
                hd(1500, 2500)
                for sel in ['input[name*="postcode" i]', 'input[placeholder*="postcode" i]']:
                    try:
                        inp = page.locator(sel).first
                        if inp.is_visible(timeout=2000):
                            inp.fill(postcode)
                            hd(1500, 2000)
                            try:
                                dropdown = page.locator('select').first
                                dropdown.wait_for(state="visible", timeout=8000)
                                options = dropdown.locator('option').all()
                            except:
                                pass
                            break
                    except:
                        continue
                continue

            print(f"    ✓ Address selected")
            success = True
            break

        if not success:
            raise Exception("Could not find suitable address")

        # STEP 4: Select options
        print(f"\n  [4] Selecting options...")
        click_text(page, 'No')  # EV = No (exact to avoid false positives)
        hd(200, 400)
        fuel_clicked = click_text_partial(page, 'Electricity and gas', 'Electricity & gas')
        if not fuel_clicked:
            print(f"    ⚠ Could not click fuel type button")
        hd(300, 500)
        size_clicked = click_text_partial(page, '1-2 bedroom', '1 or 2 bedroom', 'Small', 'Low')
        if not size_clicked:
            # Try selecting from a dropdown
            for sel in ['select[name*="bedroom" i]', 'select[name*="usage" i]', 'select[name*="size" i]', 'select[name*="house" i]']:
                try:
                    dd = page.locator(sel).first
                    if dd.is_visible(timeout=1500):
                        opts = dd.locator('option').all()
                        for opt in opts:
                            txt = opt.text_content().strip().lower()
                            if any(k in txt for k in ['1', '2', 'small', 'low', 'medium']):
                                dd.select_option(label=opt.text_content().strip())
                                print(f"    ✓ Selected usage from dropdown: {opt.text_content().strip()}")
                                size_clicked = True
                                break
                        if size_clicked:
                            break
                except:
                    continue
            if not size_clicked:
                print(f"    ⚠ Could not select household size/usage - check screenshot")
        hd(300, 500)
        print(f"    ✓ Options selected")

        # STEP 5: Check eligible popup
        body = get_body_text(page)
        if 'great news' in body and 'eligible' in body:
            print(f"    ⚠ Eligible popup - dismissing...")
            click_text(page, 'See prices', 'See tariff prices', 'Continue', 'Close', 'Got it')
            hd(400, 700)

        # STEP 6: Click see prices
        print(f"\n  [5] Clicking see tariff prices...")
        clicked = click_text(page, 'See tariff prices', 'Get quote', 'Continue')
        if not clicked:
            try:
                page.locator('button[type="submit"]').first.click()
            except:
                pass
        hd(2500, 4000)

        # Check for missing-out popup on results
        body = get_body_text(page)
        if "what you'll be missing" in body or "what you will be missing" in body:
            close_any_popup(page)
            hd(500, 800)

        # STEP 7: Expand tariff details
        print(f"\n  [6] Expanding tariff details...")
        expanded = click_text(page, 'More info', 'View details', 'See details', 'Show details', 'Tariff details')
        if expanded:
            print(f"    ✓ Expanded")
        else:
            print(f"    ⚠ No expand button found")
        hd(500, 800)

        page.screenshot(path=f"screenshots/eon_{region.replace(' ', '_')}_expanded.png")

        # STEP 8: Extract rates
        print(f"\n  [7] Extracting rates...")
        # Scroll to load all content
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        hd(300, 500)
        page.evaluate("window.scrollTo(0, 0)")
        hd(200, 400)

        page_text = page.inner_text('body')

        rates = {}
        lines = [l.strip() for l in page_text.splitlines() if l.strip()]

        # Tariff name: first line starting with "Next "
        for line in lines:
            if line.lower().startswith('next ') and len(line) <= 60:
                rates['tariff_name'] = line
                break

        # Exit fee
        m = re.search(r'£(\d+)\s*(?:per fuel\s*)?exit fee|exit fee[:\s]*£(\d+)', page_text, re.I)
        if m:
            rates['exit_fee_gbp'] = int(m.group(1) or m.group(2))

        # Unit rates and standing charges
        unit_rates = re.findall(r'(\d+\.\d+)\s*p\s*(?:per\s*)?kWh', page_text, re.I)
        standing = re.findall(r'(\d+\.\d+)\s*p\s*(?:per\s*)?day', page_text, re.I)

        if len(unit_rates) >= 1:
            rates['elec_unit_rate_p'] = float(unit_rates[0])
        if len(unit_rates) >= 2:
            rates['gas_unit_rate_p'] = float(unit_rates[1])
        if len(standing) >= 1:
            rates['elec_standing_p'] = float(standing[0])
        if len(standing) >= 2:
            rates['gas_standing_p'] = float(standing[1])

        page.screenshot(path=f"screenshots/eon_{region.replace(' ', '_')}_final.png")

        if rates:
            result['tariffs'].append(rates)
            print(f"    ✓ EXTRACTED:")
            for k, v in rates.items():
                print(f"      {k}: {v}")
        else:
            result['error'] = "Could not extract rates"
            print(f"    ✗ No rates found")

        result['url'] = page.url

    except PlaywrightTimeout as e:
        result['error'] = f"Timeout: {str(e)[:100]}"
        print(f"    ✗ TIMEOUT: {e}")
    except Exception as e:
        result['error'] = str(e)[:200]
        print(f"    ✗ ERROR: {e}")
        try:
            page.screenshot(path=f"screenshots/eon_{region.replace(' ', '_')}_error.png")
        except:
            pass
    finally:
        if context:
            context.close()

    result['tried_addresses'] = list(tried_addresses)
    return result, tried_addresses


def scrape_with_retry(browser, postcode, region, max_attempts=3):
    tried = set()
    for attempt in range(1, max_attempts + 1):
        print(f"\n  Attempt {attempt}/{max_attempts}")
        if tried:
            print(f"     Already tried: {sorted(tried)}")
        result, tried = scrape_eon(browser, postcode, region, attempt, tried)
        if result.get('tariffs'):
            return result
        if attempt < max_attempts:
            wait = 15 + random.randint(0, 15)
            print(f"\n  Waiting {wait}s...")
            time.sleep(wait)
    return result


def run_scraper(headless=False, test_postcode=None, regions=None, wait_secs=15, max_retries=3):
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
        for rname, pc in DNO_POSTCODES.items():
            for r in region_list:
                if r.lower() in rname.lower():
                    postcodes[rname] = pc
                    break
        if not postcodes:
            print(f"No matching regions for: {regions}")
            return []
        print(f"  Scraping {len(postcodes)} regions: {', '.join(postcodes.keys())}")
    else:
        postcodes = DNO_POSTCODES

    items = list(postcodes.items())
    batches = [items[i:i+3] for i in range(0, len(items), 3)]
    os.makedirs("screenshots", exist_ok=True)

    with sync_playwright() as p:
        for batch_idx, batch in enumerate(batches):
            if early_abort:
                break

            print(f"\n{'#'*60}")
            print(f"  BATCH {batch_idx + 1}/{len(batches)} - {len(batch)} regions")
            print('#'*60)

            browser = p.chromium.launch(
                headless=headless,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--no-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-setuid-sandbox',
                ]
            )

            try:
                for i, (region, postcode) in enumerate(batch):
                    print(f"\n{'='*60}")
                    print(f"  {region} ({postcode})")
                    print('='*60)

                    result = scrape_with_retry(browser, postcode, region, max_retries)
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
                        print(f"\n  EARLY ABORT: first {consecutive_failures} regions failed")
                        early_abort = True
                        break

                    if i < len(batch) - 1:
                        wait = wait_secs + random.randint(-3, 8)
                        print(f"\n  Waiting {wait}s...")
                        time.sleep(wait)
            finally:
                browser.close()

            if early_abort:
                break

            if batch_idx < len(batches) - 1:
                batch_wait = 45 + random.randint(0, 20)
                print(f"\n  Batch done. Waiting {batch_wait}s...")
                time.sleep(batch_wait)

    # RETRY PASS: if the scraper worked for most regions, retry stragglers
    if not early_abort:
        failed = [(r['region'], r['postcode']) for r in results if not r.get('tariffs')]
        success_count = len(results) - len(failed)
        if failed and success_count >= 5 and len(failed) <= 5:
            print(f"\n{'#'*60}")
            print(f"  RETRY PASS: {success_count}/{len(results)} succeeded, retrying {len(failed)} failed region(s)")
            print('#'*60)
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=headless,
                    args=[
                        '--disable-blink-features=AutomationControlled',
                        '--no-sandbox',
                        '--disable-dev-shm-usage',
                        '--disable-setuid-sandbox',
                    ]
                )
                try:
                    for region, postcode in failed:
                        print(f"\n{'='*60}")
                        print(f"  RETRY: {region} ({postcode})")
                        print('='*60)
                        result = scrape_with_retry(browser, postcode, region, max_retries)
                        for i, r in enumerate(results):
                            if r['region'] == region:
                                results[i] = result
                                break
                        if i < len(failed) - 1:
                            time.sleep(wait_secs + random.randint(0, 10))
                finally:
                    browser.close()

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
                row = base.copy(); row.update(t); rows.append(row)
        else:
            base["error"] = r.get("error", "Unknown"); rows.append(base)

    fields = ["supplier", "region", "postcode", "scraped_at", "attempt", "tariff_name",
              "elec_unit_rate_p", "elec_standing_p", "gas_unit_rate_p", "gas_standing_p",
              "exit_fee_gbp", "error"]
    with open(f"eon_tariffs_{timestamp}.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        writer.writeheader(); writer.writerows(rows)

    print(f"\n{'='*60}")
    success = sum(1 for r in results if r.get('tariffs'))
    print(f"Success: {success}/{len(results)} ({100*success/len(results) if results else 0:.0f}%)")
    for r in results:
        tariffs = r.get('tariffs', [])
        t = tariffs[0] if tariffs else {}
        icon = "✓" if r.get('tariffs') else "✗"
        print(f"  {icon} {r['region']}: {t.get('elec_unit_rate_p','?')}p elec, {t.get('gas_unit_rate_p','?')}p gas")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="E.ON Next Scraper v6.1 - Playwright")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--test", type=str, help="Test single postcode")
    parser.add_argument("--regions", type=str, help="Comma-separated regions")
    parser.add_argument("--wait", type=int, default=15)
    parser.add_argument("--retries", type=int, default=3)
    args = parser.parse_args()

    os.makedirs("screenshots", exist_ok=True)
    print("="*60)
    print("E.ON NEXT SCRAPER v6.1 - PLAYWRIGHT")
    print("="*60)

    results = run_scraper(args.headless, args.test, args.regions, args.wait, args.retries)
    save_results(results)

    try:
        input("\nPress Enter to exit...")
    except (EOFError, KeyboardInterrupt):
        pass


if __name__ == "__main__":
    main()
