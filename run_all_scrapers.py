#!/usr/bin/env python3
"""
MASTER TARIFF SCRAPER
Runs all supplier scrapers and combines results into one file.

Usage:
    python run_all_scrapers.py                  # Run all scrapers in PARALLEL
    python run_all_scrapers.py --sequential    # Run one at a time
    python run_all_scrapers.py --only eon bg   # Run specific scrapers
    python run_all_scrapers.py --combine-only  # Just combine existing JSON files
"""

import json
import csv
import os
import subprocess
import sys
import glob
import threading
import time
import re
from datetime import datetime

# ============================================
# CONFIGURATION
# ============================================

SCRAPERS = {
    "eon": {
        "script": "eon_next_scraper_v5.py",
        "output_pattern": "eon_tariffs_*.json",
        "supplier_name": "eon_next",
        "is_api": False,  # Web scraper - needs retry logic
    },
    "bg": {
        "script": "bg_scraper_v10.py",
        "output_pattern": "bg_tariffs_*.json",
        "supplier_name": "british_gas",
        "is_api": False,  # Web scraper - needs retry logic
    },
    "ovo": {
        "script": "ovo_scraper_v1.py",
        "output_pattern": "ovo_tariffs_*.json",
        "supplier_name": "ovo",
        "is_api": False,  # Web scraper - needs retry logic
    },
    "octopus": {
        "script": "octopus_api_v1.py",
        "output_pattern": "octopus_tariffs_*.json",
        "supplier_name": "octopus",
        "is_api": True,  # API-based - no retry needed
    },
    "sp": {
        "script": "scottish_power_scraper_v2.py",
        "output_pattern": "sp_tariffs_*.json",
        "supplier_name": "scottish_power",
        "is_api": False,  # Web scraper - needs retry logic
    },
    "edf": {
        "script": "edf_scraper_v5_fixed.py",
        "output_pattern": "edf_tariffs_*.json",
        "supplier_name": "edf",
        "is_api": False,  # Web scraper - needs retry logic
    },
    "fuse": {
        "script": "fuse_energy_scraper_v2_fixed.py",
        "output_pattern": "fuse_tariffs_*.json",
        "supplier_name": "fuse",
        "is_api": False,  # Web scraper - needs retry logic
    },
}

# Unified output fields
OUTPUT_FIELDS = [
    "supplier",
    "region", 
    "postcode",
    "scraped_at",
    "tariff_name",
    "elec_unit_rate_p",
    "elec_day_rate_p",
    "elec_night_rate_p",
    "elec_standing_p",
    "gas_unit_rate_p",
    "gas_standing_p",
    "exit_fee_gbp",
    "contract_months",
    "error"
]


# ============================================
# FUNCTIONS
# ============================================

def get_latest_file(pattern):
    """Get the most recently modified file matching pattern."""
    files = glob.glob(pattern)
    if not files:
        return None
    return max(files, key=os.path.getmtime)


def run_scraper(name, config):
    """Run a single scraper script."""
    script = config["script"]
    
    if not os.path.exists(script):
        print(f"  ⚠ Script not found: {script}")
        return False
    
    print(f"\n{'='*60}")
    print(f"  Running {name.upper()} scraper: {script}")
    print('='*60)
    
    try:
        # Run the scraper
        cmd = [sys.executable, script]
        
        # Add headless flag for browser-based scrapers (not APIs)
        if not config.get("is_api", False):
            cmd.append("--headless")
        
        result = subprocess.run(
            cmd,
            capture_output=False,  # Show output in real-time
            text=True
        )
        return result.returncode == 0
    except Exception as e:
        print(f"  ✗ Error running {script}: {e}")
        return False


def load_scraper_results(config):
    """Load results from a scraper's output file."""
    pattern = config["output_pattern"]
    supplier = config["supplier_name"]
    
    latest_file = get_latest_file(pattern)
    if not latest_file:
        print(f"  ⚠ No output file found for pattern: {pattern}")
        return []
    
    print(f"  Loading: {latest_file}")
    
    try:
        with open(latest_file, "r") as f:
            data = json.load(f)
        
        # Normalize the data
        normalized = []
        for r in data:
            # Ensure supplier field exists
            if "supplier" not in r:
                r["supplier"] = supplier
            
            if r.get("tariffs"):
                for t in r["tariffs"]:
                    row = {
                        "supplier": r.get("supplier", supplier),
                        "region": r.get("region", ""),
                        "postcode": r.get("postcode", ""),
                        "scraped_at": r.get("scraped_at", ""),
                        "tariff_name": t.get("tariff_name", ""),
                        "elec_unit_rate_p": t.get("elec_unit_rate_p"),
                        "elec_day_rate_p": t.get("elec_day_rate_p"),
                        "elec_night_rate_p": t.get("elec_night_rate_p"),
                        "elec_standing_p": t.get("elec_standing_p"),
                        "gas_unit_rate_p": t.get("gas_unit_rate_p"),
                        "gas_standing_p": t.get("gas_standing_p"),
                        "exit_fee_gbp": t.get("exit_fee_gbp") or t.get("exit_fee"),
                        "contract_months": t.get("contract_months"),
                        "error": None
                    }
                    normalized.append(row)
            else:
                # Failed scrape
                normalized.append({
                    "supplier": r.get("supplier", supplier),
                    "region": r.get("region", ""),
                    "postcode": r.get("postcode", ""),
                    "scraped_at": r.get("scraped_at", ""),
                    "tariff_name": None,
                    "elec_unit_rate_p": None,
                    "elec_day_rate_p": None,
                    "elec_night_rate_p": None,
                    "elec_standing_p": None,
                    "gas_unit_rate_p": None,
                    "gas_standing_p": None,
                    "exit_fee_gbp": None,
                    "contract_months": None,
                    "error": r.get("error", "Unknown")
                })
        
        return normalized
    
    except Exception as e:
        print(f"  ✗ Error loading {latest_file}: {e}")
        return []


def combine_results(scrapers_to_run):
    """Combine results from all scrapers."""
    all_results = []
    
    print(f"\n{'#'*60}")
    print("  COMBINING RESULTS")
    print('#'*60)
    
    for name, config in SCRAPERS.items():
        if scrapers_to_run and name not in scrapers_to_run:
            continue
        
        results = load_scraper_results(config)
        print(f"  {name}: {len(results)} records")
        all_results.extend(results)
    
    return all_results


def check_incomplete_data(r):
    """Check if a result has incomplete data. Returns reason string or None if OK."""
    # Check for error
    if r.get("error"):
        return f"error: {r.get('error')}"
    
    # Check for missing tariff name
    if not r.get("tariff_name"):
        return "missing tariff name"
    
    # Check for missing crucial rates (need at least elec OR gas unit rate)
    has_elec = r.get("elec_unit_rate_p") is not None
    has_gas = r.get("gas_unit_rate_p") is not None
    
    if not has_elec and not has_gas:
        return "missing unit rates"
    
    # Check for missing standing charges
    has_elec_standing = r.get("elec_standing_p") is not None
    has_gas_standing = r.get("gas_standing_p") is not None
    
    if not has_elec_standing and not has_gas_standing:
        return "missing standing charges"
    
    return None  # Data is complete


def save_combined_results(results):
    """Save combined results to JSON and CSV."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # JSON for web use
    json_file = f"all_tariffs_{timestamp}.json"
    output_data = {
        "last_updated": datetime.now().isoformat(),
        "total_records": len(results),
        "suppliers": list(set(r["supplier"] for r in results if r.get("supplier"))),
        "tariffs": results
    }
    
    with open(json_file, "w") as f:
        json.dump(output_data, f, indent=2)
    print(f"\n✓ Saved: {json_file}")
    
    # Also save a simple version for website
    simple_file = "all_tariffs_latest.json"
    with open(simple_file, "w") as f:
        json.dump(output_data, f, indent=2)
    print(f"✓ Saved: {simple_file} (for website)")
    
    # =====================================================
    # WEBSITE FORMAT - Transform to tariff-tracker format
    # =====================================================
    website_tariffs = convert_to_website_format(results)
    website_file = "tariff_data_latest.json"
    
    website_output = {
        "lastUpdated": datetime.now().strftime("%d %B %Y"),
        "tariffs": website_tariffs
    }
    
    # Save as JSON file for website
    with open(website_file, "w") as f:
        json.dump(website_output, f, indent=2)
    print(f"✓ Saved: {website_file} (for tariff tracker)")
    
    # CSV for analysis
    csv_file = f"all_tariffs_{timestamp}.csv"
    with open(csv_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_FIELDS, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(results)
    print(f"✓ Saved: {csv_file}")
    
    # Summary
    print(f"\n{'='*60}")
    print("  SUMMARY")
    print('='*60)
    
    # Count by supplier
    supplier_stats = {}
    for r in results:
        s = r.get("supplier", "unknown")
        if s not in supplier_stats:
            supplier_stats[s] = {"total": 0, "success": 0}
        supplier_stats[s]["total"] += 1
        if r.get("tariff_name") and not r.get("error"):
            supplier_stats[s]["success"] += 1
    
    for supplier, stats in supplier_stats.items():
        pct = 100 * stats["success"] / stats["total"] if stats["total"] > 0 else 0
        print(f"  {supplier}: {stats['success']}/{stats['total']} ({pct:.0f}%)")
    
    print(f"\n  TOTAL: {len(results)} records")
    
    return json_file, csv_file


def convert_to_website_format(results):
    """Convert flat scraper results to website tariff-tracker format."""
    
    # Group by supplier and tariff name
    suppliers = {}
    
    for r in results:
        if not r.get("tariff_name"):
            continue  # Skip failed scrapes
        
        supplier = r.get("supplier", "unknown")
        tariff_name = r.get("tariff_name", "")
        region = r.get("region", "")
        
        key = f"{supplier}|{tariff_name}"
        
        if key not in suppliers:
            # Determine supplier display name and logo
            if supplier == "eon_next":
                display_name = "E.ON Next"
                logo = "logo-eon.png"
            elif supplier == "british_gas":
                display_name = "British Gas"
                logo = "logo-bg.png"
            elif supplier == "ovo":
                display_name = "OVO Energy"
                logo = "logo-ovo.png"
            elif supplier == "octopus":
                display_name = "Octopus Energy"
                logo = "logo-octopus.png"
            else:
                display_name = supplier.replace("_", " ").title()
                logo = f"logo-{supplier}.png"
            
            suppliers[key] = {
                "supplier": display_name,
                "logo": logo,
                "name": tariff_name,
                "fuelTypes": ["dual", "electric", "gas"],
                "contractLength": "12 months",  # Default
                "exitFees": "£50 per fuel",  # Default
                "regions": {},
                "pros": [],
                "cons": []
            }
        
        # Add region data
        elec_unit = r.get("elec_unit_rate_p")
        elec_standing = r.get("elec_standing_p")
        gas_unit = r.get("gas_unit_rate_p")
        gas_standing = r.get("gas_standing_p")
        
        # Only add if we have data
        if elec_unit or gas_unit:
            suppliers[key]["regions"][region] = {
                "dd": {  # Direct debit rates only
                    "elecSC": elec_standing or 0,
                    "elecUnit": elec_unit or 0,
                    "gasSC": gas_standing or 0,
                    "gasUnit": gas_unit or 0
                }
            }
        
        # Set exit fees from scraped data - normalize to "£X per fuel"
        exit_fee = r.get("exit_fee_gbp") or r.get("exit_fee")
        supplier_name = r.get("supplier", "")
        
        if exit_fee:
            # If already says "per fuel", keep as is
            if isinstance(exit_fee, str) and "per fuel" in exit_fee.lower():
                suppliers[key]["exitFees"] = exit_fee
            else:
                # Extract number
                fee_num = None
                if isinstance(exit_fee, str):
                    match = re.search(r'[\d.]+', exit_fee)
                    if match:
                        fee_num = float(match.group())
                else:
                    fee_num = float(exit_fee)
                
                if fee_num is not None:
                    # EDF shows total (£100 for dual fuel) - divide by 2
                    if supplier_name == "edf":
                        fee_num = fee_num / 2
                    
                    suppliers[key]["exitFees"] = f"£{int(fee_num)} per fuel"
        
        # Set contract length from scraped data
        contract_months = r.get("contract_months")
        if contract_months:
            suppliers[key]["contractLength"] = f"{contract_months} months"
    
    return list(suppliers.values())


def run_scraper_thread(name, config, results_dict):
    """Run scraper in a thread and store success status."""
    success = run_scraper(name, config)
    results_dict[name] = success


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Master Tariff Scraper")
    parser.add_argument("--only", nargs="+", help="Only run specific scrapers (e.g. --only eon bg)")
    parser.add_argument("--sequential", action="store_true", help="Run scrapers one at a time instead of parallel")
    parser.add_argument("--combine-only", action="store_true", help="Only combine existing results, don't run scrapers")
    parser.add_argument("--wait", type=int, default=300, help="Wait time between scrapers in sequential mode (seconds)")
    parser.add_argument("--no-retry", action="store_true", help="Skip retry logic for failed regions")
    args = parser.parse_args()
    
    print("="*60)
    print("  MASTER TARIFF SCRAPER")
    print("="*60)
    print(f"  Available scrapers: {list(SCRAPERS.keys())}")
    
    scrapers_to_run = args.only if args.only else list(SCRAPERS.keys())
    print(f"  Will process: {scrapers_to_run}")
    
    if args.sequential:
        print(f"  Mode: SEQUENTIAL (one at a time, {args.wait}s between)")
    else:
        print(f"  Mode: PARALLEL (all at same time)")
    print()
    
    if not args.combine_only:
        if args.sequential:
            # Run each scraper one at a time
            for i, name in enumerate(scrapers_to_run):
                if name not in SCRAPERS:
                    print(f"  ⚠ Unknown scraper: {name}")
                    continue
                
                success = run_scraper(name, SCRAPERS[name])
                
                # Wait between scrapers
                if i < len(scrapers_to_run) - 1:
                    print(f"\n  ⏳ Waiting {args.wait}s before next scraper...")
                    time.sleep(args.wait)
        else:
            # Run all scrapers in parallel
            threads = []
            results_dict = {}
            
            print(f"\n  🚀 Starting {len(scrapers_to_run)} scrapers in parallel...")
            print(f"  (Each will open its own browser window)\n")
            
            for name in scrapers_to_run:
                if name not in SCRAPERS:
                    print(f"  ⚠ Unknown scraper: {name}")
                    continue
                
                t = threading.Thread(target=run_scraper_thread, args=(name, SCRAPERS[name], results_dict))
                t.start()
                threads.append((name, t))
                time.sleep(5)  # Small delay between starting each
            
            # Wait for all to complete
            print(f"\n  ⏳ Waiting for all scrapers to complete...")
            for name, t in threads:
                t.join()
                status = "✓" if results_dict.get(name) else "✗"
                print(f"    {status} {name} finished")
    
    # Combine all results
    results = combine_results(scrapers_to_run)
    
    # =====================================================
    # RETRY FAILED OR INCOMPLETE REGIONS (Web scrapers only)
    # =====================================================
    if not args.combine_only and not args.no_retry:
        failed = []
        for r in results:
            supplier = r.get("supplier", "")
            
            # Find if this supplier is API-based (skip retry for API scrapers)
            is_api = False
            for name, config in SCRAPERS.items():
                if config["supplier_name"] == supplier:
                    is_api = config.get("is_api", False)
                    break
            
            if is_api:
                continue  # Skip API-based scrapers - they don't need retries
            
            # Check if data is incomplete
            reason = check_incomplete_data(r)
            if reason:
                failed.append((r, reason))
        
        if failed:
            print(f"\n{'#'*60}")
            print(f"  RETRYING {len(failed)} FAILED/INCOMPLETE REGIONS")
            print(f"  (Skipping API-based scrapers like Octopus)")
            print('#'*60)
            
            for r, reason in failed:
                supplier = r.get("supplier", "")
                region = r.get("region", "")
                postcode = r.get("postcode", "")
                
                print(f"\n  Retrying: {supplier} - {region} ({postcode})")
                print(f"    Reason: {reason}")
                
                # Find the right scraper
                scraper_name = None
                for name, config in SCRAPERS.items():
                    if config["supplier_name"] == supplier:
                        scraper_name = name
                        break
                
                if not scraper_name:
                    print(f"    ⚠ Unknown supplier, skipping")
                    continue
                
                config = SCRAPERS[scraper_name]
                script = config["script"]
                
                if not os.path.exists(script):
                    print(f"    ⚠ Script not found: {script}")
                    continue
                
                # Run single postcode test
                try:
                    print(f"    Running {script} --test \"{postcode}\"")
                    subprocess.run(
                        [sys.executable, script, "--test", postcode],
                        capture_output=False,
                        text=True
                    )
                    print(f"\n    ⏳ Cooling down 60s before next retry...")
                    time.sleep(60)  # Longer cooldown between retries
                except Exception as e:
                    print(f"    ✗ Error: {e}")
            
            # Re-combine results after retries
            print(f"\n  Re-combining results after retries...")
            results = combine_results(scrapers_to_run)
    
    if results:
        save_combined_results(results)
        
        # Final data quality report
        print(f"\n{'='*60}")
        print("  DATA QUALITY REPORT")
        print('='*60)
        
        complete = 0
        incomplete = 0
        for r in results:
            if check_incomplete_data(r):
                incomplete += 1
            else:
                complete += 1
        
        pct = 100 * complete / len(results) if results else 0
        print(f"  Complete records: {complete}/{len(results)} ({pct:.1f}%)")
        print(f"  Incomplete/Failed: {incomplete}")
        
        if incomplete > 0:
            print(f"\n  Incomplete regions by supplier:")
            by_supplier = {}
            for r in results:
                reason = check_incomplete_data(r)
                if reason:
                    s = r.get("supplier", "unknown")
                    if s not in by_supplier:
                        by_supplier[s] = []
                    by_supplier[s].append(f"{r.get('region')} ({reason})")
            
            for s, regions in by_supplier.items():
                print(f"    {s}:")
                for region in regions[:5]:  # Show first 5
                    print(f"      - {region}")
                if len(regions) > 5:
                    print(f"      ... and {len(regions) - 5} more")
    else:
        print("\n  ⚠ No results to combine!")
    
    # input("\nPress Enter to exit...")  # Disabled for automated runs


if __name__ == "__main__":
    main()
