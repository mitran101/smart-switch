#!/usr/bin/env python3
"""
Octopus Energy Tariff API v1
- Uses official Octopus API (no scraping needed!)
- No authentication required for tariff data
- FULLY DYNAMIC - no monthly updates needed!
- Automatically fetches all current tariffs across all regions
- Outputs in same format as BG/E.ON scrapers
"""

import json
import csv
import requests
import time
from datetime import datetime

# ============================================
# CONFIGURATION
# ============================================

BASE_URL = "https://api.octopus.energy/v1"

# Map GSP regions (A-P) to DNO region names
# Octopus uses single letter codes, we map to your standard DNO names
GSP_TO_DNO = {
    "_A": ("Eastern", "IP4 5ET"),
    "_B": ("East Midlands", "DE23 6JJ"),
    "_C": ("London", "N5 2SD"),
    "_D": ("North Wales & Merseyside", "L3 2BN"),
    "_E": ("West Midlands", "SY2 6HL"),
    "_F": ("North East", "NE2 1UY"),
    "_G": ("North West", "PR4 2NB"),
    "_H": ("Southern", "BH6 4AS"),
    "_J": ("South East", "BN2 7HQ"),
    "_K": ("South Wales", "CF14 2DY"),
    "_L": ("South West", "PL9 7BS"),
    "_M": ("Yorkshire", "YO31 1DT"),
    "_N": ("South Scotland", "G20 6NQ"),
    "_P": ("North Scotland", "AB24 3EN"),
}

# Note: Products are fetched DYNAMICALLY from the API
# No need to manually update product codes - the API always returns current tariffs
# Octopus adds/removes products automatically, script will pick them up


# ============================================
# API FUNCTIONS
# ============================================

def get_all_products(brand="OCTOPUS_ENERGY", is_business=False):
    """Fetch all available products from Octopus API."""
    products = []
    url = f"{BASE_URL}/products/"
    params = {
        "brand": brand,
        "is_business": str(is_business).lower(),
        "is_variable": None,
        "is_prepay": "false",
        "page_size": 100
    }
    
    while url:
        print(f"    Fetching: {url}")
        try:
            resp = requests.get(url, params=params if "page" not in url else None, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            
            for p in data.get("results", []):
                # Only include residential, non-prepay products
                if not p.get("is_business") and not p.get("is_prepay"):
                    products.append(p)
            
            url = data.get("next")
            params = None  # Only use params on first request
            time.sleep(0.5)  # Be nice to the API
            
        except Exception as e:
            print(f"    Error fetching products: {e}")
            break
    
    return products


def get_product_details(product_code):
    """Fetch detailed tariff info for a product."""
    url = f"{BASE_URL}/products/{product_code}/"
    
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"    Error fetching {product_code}: {e}")
        return None


def extract_tariff_rates(product_data, gsp_code):
    """Extract electricity and gas rates for a specific GSP region."""
    rates = {}
    
    # Get electricity rates (single register = standard meter)
    elec_tariffs = product_data.get("single_register_electricity_tariffs", {})
    if gsp_code in elec_tariffs:
        elec = elec_tariffs[gsp_code].get("direct_debit_monthly", {})
        if elec:
            rates["elec_unit_rate_p"] = elec.get("standard_unit_rate_inc_vat")
            rates["elec_standing_p"] = elec.get("standing_charge_inc_vat")
            
            # Get exit fees (API returns pence, convert to pounds)
            exit_fee_pence = elec.get("exit_fees_inc_vat", 0)
            exit_type = elec.get("exit_fees_type", "NONE")
            if exit_fee_pence and exit_type != "NONE":
                exit_fee_pounds = exit_fee_pence / 100  # Convert pence to pounds
                rates["exit_fee"] = f"£{exit_fee_pounds:.0f} per fuel"
            else:
                rates["exit_fee"] = "£0"
    
    # Get gas rates
    gas_tariffs = product_data.get("single_register_gas_tariffs", {})
    if gsp_code in gas_tariffs:
        gas = gas_tariffs[gsp_code].get("direct_debit_monthly", {})
        if gas:
            rates["gas_unit_rate_p"] = gas.get("standard_unit_rate_inc_vat")
            rates["gas_standing_p"] = gas.get("standing_charge_inc_vat")
    
    return rates


def validate_rates(rates, tariff_name):
    """Sanity check rates and warn if they look suspicious."""
    warnings = []
    
    # Check electricity unit rate (typical range: 5-50p, Agile can be -10 to 100p)
    elec_unit = rates.get("elec_unit_rate_p")
    if elec_unit is not None:
        if elec_unit > 100:
            warnings.append(f"Elec unit rate {elec_unit}p seems high")
        elif elec_unit < -20:
            warnings.append(f"Elec unit rate {elec_unit}p seems very negative")
    
    # Check gas unit rate (typical range: 4-15p)
    gas_unit = rates.get("gas_unit_rate_p")
    if gas_unit is not None:
        if gas_unit > 30:
            warnings.append(f"Gas unit rate {gas_unit}p seems high")
        elif gas_unit < 0:
            warnings.append(f"Gas unit rate {gas_unit}p is negative (unusual)")
    
    # Check standing charges (typical range: 20-60p/day)
    elec_sc = rates.get("elec_standing_p")
    if elec_sc is not None:
        if elec_sc > 100:
            warnings.append(f"Elec standing charge {elec_sc}p/day seems high")
        elif elec_sc < 10:
            warnings.append(f"Elec standing charge {elec_sc}p/day seems low")
    
    gas_sc = rates.get("gas_standing_p")
    if gas_sc is not None:
        if gas_sc > 100:
            warnings.append(f"Gas standing charge {gas_sc}p/day seems high")
        elif gas_sc < 10:
            warnings.append(f"Gas standing charge {gas_sc}p/day seems low")
    
    if warnings:
        print(f"    ⚠ {tariff_name}: {'; '.join(warnings)}")
    
    return len(warnings) == 0


def get_current_unit_rates(product_code, tariff_code, fuel="electricity"):
    """Fetch current unit rates for variable/agile tariffs."""
    if fuel == "electricity":
        url = f"{BASE_URL}/products/{product_code}/electricity-tariffs/{tariff_code}/standard-unit-rates/"
    else:
        url = f"{BASE_URL}/products/{product_code}/gas-tariffs/{tariff_code}/standard-unit-rates/"
    
    try:
        resp = requests.get(url, params={"page_size": 1}, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        
        if data.get("results"):
            return data["results"][0].get("value_inc_vat")
    except:
        pass
    
    return None


def get_standing_charges(product_code, tariff_code, fuel="electricity"):
    """Fetch current standing charge."""
    if fuel == "electricity":
        url = f"{BASE_URL}/products/{product_code}/electricity-tariffs/{tariff_code}/standing-charges/"
    else:
        url = f"{BASE_URL}/products/{product_code}/gas-tariffs/{tariff_code}/standing-charges/"
    
    try:
        resp = requests.get(url, params={"page_size": 1}, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        
        if data.get("results"):
            return data["results"][0].get("value_inc_vat")
    except:
        pass
    
    return None


# ============================================
# MAIN SCRAPING LOGIC
# ============================================

def fetch_all_tariffs():
    """Fetch all tariffs for all regions."""
    results = []
    
    print("\n[STEP 1] Fetching available products...")
    products = get_all_products()
    print(f"  Found {len(products)} residential products")
    
    # Filter to most relevant current products
    # Focus on main tariff types people would compare
    relevant_keywords = ["flex", "var", "fix", "loyal", "go", "agile", "intel", "cosy", "tracker", "flux", "snug"]
    
    active_products = []
    for p in products:
        code = p.get("code", "").lower()
        name = p.get("display_name", "").lower()
        direction = p.get("direction", "IMPORT")
        
        # Skip export tariffs (we want import/consumption tariffs)
        if direction == "EXPORT":
            continue
        
        # Check if it's a current, relevant product
        if any(kw in code or kw in name for kw in relevant_keywords):
            if p.get("available_to") is None:  # Still available
                active_products.append(p)
    
    print(f"  Filtered to {len(active_products)} active import tariffs")
    
    print("\n[STEP 2] Fetching tariff details for each product...")
    
    for i, product in enumerate(active_products):
        product_code = product["code"]
        display_name = product.get("display_name", product_code)
        
        print(f"\n  [{i+1}/{len(active_products)}] {display_name} ({product_code})")
        
        # Get full product details
        details = get_product_details(product_code)
        if not details:
            continue
        
        # Extract rates for each region
        first_region = True
        for gsp_code, (region_name, postcode) in GSP_TO_DNO.items():
            rates = extract_tariff_rates(details, gsp_code)
            
            # Validate rates look sensible (only for first region to avoid spam)
            if rates and first_region:
                validate_rates(rates, display_name)
                first_region = False
            
            if rates.get("elec_unit_rate_p") or rates.get("gas_unit_rate_p"):
                # Flag if this is an electricity-only tariff
                elec_only = (rates.get("elec_unit_rate_p") is not None and 
                            rates.get("gas_unit_rate_p") is None)
                
                result = {
                    "region": region_name,
                    "postcode": postcode,
                    "scraped_at": datetime.now().isoformat(),
                    "tariffs": [{
                        "tariff_name": display_name,
                        "product_code": product_code,
                        "elec_unit_rate_p": rates.get("elec_unit_rate_p"),
                        "elec_standing_p": rates.get("elec_standing_p"),
                        "gas_unit_rate_p": rates.get("gas_unit_rate_p"),
                        "gas_standing_p": rates.get("gas_standing_p"),
                        "exit_fee": rates.get("exit_fee", "£0"),
                        "is_variable": product.get("is_variable", False),
                        "is_green": product.get("is_green", False),
                        "is_tracker": product.get("is_tracker", False),
                        "elec_only": elec_only,
                    }]
                }
                results.append(result)
        
        time.sleep(0.3)  # Rate limiting
    
    return results


def save_results(results):
    """Save results in same format as other scrapers."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # JSON output
    json_file = f"octopus_tariffs_{timestamp}.json"
    with open(json_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved: {json_file}")
    
    # CSV output
    csv_file = f"octopus_tariffs_{timestamp}.csv"
    rows = []
    
    for r in results:
        base = {
            "supplier": "octopus",
            "region": r["region"],
            "postcode": r["postcode"],
            "scraped_at": r["scraped_at"],
        }
        
        if r.get("tariffs"):
            for t in r["tariffs"]:
                row = base.copy()
                row.update({
                    "tariff_name": t.get("tariff_name", ""),
                    "product_code": t.get("product_code", ""),
                    "elec_unit_rate_p": t.get("elec_unit_rate_p"),
                    "elec_standing_p": t.get("elec_standing_p"),
                    "gas_unit_rate_p": t.get("gas_unit_rate_p"),
                    "gas_standing_p": t.get("gas_standing_p"),
                    "exit_fee": t.get("exit_fee", ""),
                    "is_variable": t.get("is_variable", False),
                    "is_green": t.get("is_green", False),
                    "elec_only": t.get("elec_only", False),
                })
                rows.append(row)
    
    fieldnames = [
        "supplier", "region", "postcode", "scraped_at", "tariff_name", "product_code",
        "elec_unit_rate_p", "elec_standing_p", "gas_unit_rate_p", "gas_standing_p",
        "exit_fee", "is_variable", "is_green", "elec_only"
    ]
    
    with open(csv_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)
    print(f"Saved: {csv_file}")
    
    # Summary
    print("\n" + "=" * 130)
    print("RESULTS SUMMARY")
    print("=" * 130)
    
    # Group by tariff name
    tariffs_by_name = {}
    for r in results:
        if r.get("tariffs"):
            t = r["tariffs"][0]
            name = t.get("tariff_name", "Unknown")
            if name not in tariffs_by_name:
                tariffs_by_name[name] = []
            tariffs_by_name[name].append((r["region"], t))
    
    print(f"\n{'Tariff':<35} {'Regions':<10} {'Elec Unit':<12} {'Elec SC':<10} {'Gas Unit':<12} {'Gas SC':<10} {'Exit Fee':<15}")
    print("-" * 130)
    
    for name, region_data in tariffs_by_name.items():
        # Show first region's data as example
        region, t = region_data[0]
        print(f"{name[:34]:<35} {len(region_data):<10} {t.get('elec_unit_rate_p', 'N/A'):<12} {t.get('elec_standing_p', 'N/A'):<10} {t.get('gas_unit_rate_p', 'N/A'):<12} {t.get('gas_standing_p', 'N/A'):<10} {t.get('exit_fee', 'N/A'):<15}")
    
    print(f"\nTotal records: {len(results)}")
    print(f"Unique tariffs: {len(tariffs_by_name)}")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Octopus Energy API Tariff Fetcher v1")
    parser.add_argument("--test", action="store_true", help="Test mode - fetch one product only")
    args = parser.parse_args()
    
    print("=" * 60)
    print("OCTOPUS ENERGY TARIFF API v1")
    print("=" * 60)
    print("✓ Uses official public API (no scraping)")
    print("✓ No authentication required")
    print("✓ FULLY DYNAMIC - no monthly updates needed!")
    print("✓ Auto-fetches all current residential tariffs")
    print("✓ All 14 DNO regions")
    print()
    
    results = fetch_all_tariffs()
    
    if results:
        save_results(results)
    else:
        print("\n⚠ No results found!")
    
    print("\nDone!")


if __name__ == "__main__":
    main()
