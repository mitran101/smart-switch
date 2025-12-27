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
        "is_api": False,
    },
    "bg": {
        "script": "bg_scraper_v10.py",
        "output_pattern": "bg_tariffs_*.json",
        "supplier_name": "british_gas",
        "is_api": False,
    },
    "ovo": {
        "script": "ovo_scraper_v1.py",
        "output_pattern": "ovo_tariffs_*.json",
        "supplier_name": "ovo",
        "is_api": False,
    },
    "octopus": {
        "script": "octopus_api_v1.py",
        "output_pattern": "octopus_tariffs_*.json",
        "supplier_name": "octopus",
        "is_api": True,
    },
    "sp": {
        "script": "scottish_power_scraper_v2.py",
        "output_pattern": "sp_tariffs_*.json",
        "supplier_name": "scottish_power",
        "is_api": False,
    },
    "edf": {
        "script": "edf_scraper_v5_fixed.py",
        "output_pattern": "edf_tariffs_*.json",
        "supplier_name": "edf",
        "is_api": False,
    },
    "fuse": {
        "script": "fuse_energy_scraper_v2_fixed.py",
        "output_pattern": "fuse_tariffs_*.json",
        "supplier_name": "fuse_energy",
        "is_api": False,
    },
}

# Retry threshold - only retry if success rate > this percentage
RETRY_THRESHOLD = 0.5  # 50% = 7/14 regions must succeed to bother retrying

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
    """Get the file with MOST data matching pattern (not just newest).
    This prevents single-region retry files from overwriting full scrape data.
    """
    files = glob.glob(pattern)
    if not files:
        return None
    
    # Find file with most records, not just newest
    best_file = None
    best_count = -1
    
    for f in files:
        try:
            with open(f, 'r') as fp:
                data = json.load(fp)
                count = len(data) if isinstance(data, list) else 0
                if count > best_count:
                    best_count = count
                    best_file = f
        except:
            continue
    
    # Fallback to newest if we couldn't read any files
    if best_file is None:
        return max(files, key=os.path.getmtime)
    
    return best_file


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
        cmd = [sys.executable, script]
        
        if not config.get("is_api", False):
            cmd.append("--headless")
        
        result = subprocess.run(
            cmd,
            capture_output=False,
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
        
        normalized = []
        for r in data:
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
    if r.get("error"):
        return f"error: {r.get('error')}"
    
    if not r.get("tariff_name"):
        return "missing tariff_name"
    
    if not r.get("elec_unit_rate_p") and not r.get("elec_day_rate_p"):
        return "missing elec rates"
    
    if not r.get("elec_standing_p"):
        return "missing elec_standing_p"
    
    tariff_name = (r.get("tariff_name") or "").lower()
    is_elec_only = "electric" in tariff_name or "elec only" in tariff_name
    
    if not is_elec_only:
        if not r.get("gas_unit_rate_p"):
            return "missing gas_unit_rate_p"
        if not r.get("gas_standing_p"):
            return "missing gas_standing_p"
    
    return None


def save_combined_results(results):
    """Save combined results to JSON and CSV."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    tracker_data = {"tariffs": results, "updated": datetime.now().isoformat()}
    
    with open("all_tariffs.json", "w") as f:
        json.dump(tracker_data, f, indent=2)
    print(f"\n  ✓ Saved: all_tariffs.json")
    
    with open(f"all_tariffs_{timestamp}.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_FIELDS, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(results)
    print(f"  ✓ Saved: all_tariffs_{timestamp}.csv")
    
    summary = create_summary(results)
    with open("tariff_data_latest.json", "w") as f:
        json.dump(summary, f, indent=2)
    print(f"  ✓ Saved: tariff_data_latest.json")


def create_summary(results):
    """Create a summary JSON for the tariff tracker."""
    suppliers = {}
    
    for r in results:
        if r.get("error") or not r.get("tariff_name"):
            continue
        
        supplier = r.get("supplier", "")
        region = r.get("region", "")
        tariff = r.get("tariff_name", "")
        
        key = f"{supplier}_{tariff}"
        
        if key not in suppliers:
            suppliers[key] = {
                "supplier": supplier,
                "tariffName": tariff,
                "regions": {},
                "exitFees": None,
                "contractLength": None,
            }
        
        suppliers[key]["regions"][region] = {
            "elecUnitRate": r.get("elec_unit_rate_p"),
            "elecDayRate": r.get("elec_day_rate_p"),
            "elecNightRate": r.get("elec_night_rate_p"),
            "elecStanding": r.get("elec_standing_p"),
            "gasUnitRate": r.get("gas_unit_rate_p"),
            "gasStanding": r.get("gas_standing_p"),
        }
        
        exit_fee = r.get("exit_fee_gbp") or r.get("exit_fee")
        supplier_name = r.get("supplier", "")
        
        if exit_fee:
            if isinstance(exit_fee, str) and "per fuel" in exit_fee.lower():
                suppliers[key]["exitFees"] = exit_fee
            else:
                fee_num = None
                if isinstance(exit_fee, str):
                    match = re.search(r'[\d.]+', exit_fee)
                    if match:
                        fee_num = float(match.group())
                else:
                    fee_num = float(exit_fee)
                
                if fee_num is not None:
                    if supplier_name == "edf":
                        fee_num = fee_num / 2
                    
                    suppliers[key]["exitFees"] = f"£{int(fee_num)} per fuel"
        
        contract_months = r.get("contract_months")
        if contract_months:
            suppliers[key]["contractLength"] = f"{contract_months} months"
    
    return list(suppliers.values())


def run_scraper_thread(name, config, results_dict):
    """Run scraper in a thread and store success status."""
    success = run_scraper(name, config)
    results_dict[name] = success


def get_supplier_success_rate(results, supplier_name):
    """Calculate success rate for a supplier."""
    supplier_results = [r for r in results if r.get("supplier") == supplier_name]
    if not supplier_results:
        return 0, 0, 0
    
    total = len(supplier_results)
    successful = sum(1 for r in supplier_results if not check_incomplete_data(r))
    
    return successful, total, successful / total if total > 0 else 0


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Master Tariff Scraper")
    parser.add_argument("--only", nargs="+", help="Only run specific scrapers")
    parser.add_argument("--sequential", action="store_true", help="Run one at a time")
    parser.add_argument("--combine-only", action="store_true", help="Only combine existing results")
    parser.add_argument("--wait", type=int, default=300, help="Wait time between scrapers")
    parser.add_argument("--no-retry", action="store_true", default=True, help="Skip retry logic (default: True)")
    parser.add_argument("--retry", action="store_true", help="Enable retry logic for failed regions")
    args = parser.parse_args()
    
    print("="*60)
    print("  MASTER TARIFF SCRAPER")
    print("="*60)
    print(f"  Available scrapers: {list(SCRAPERS.keys())}")
    
    scrapers_to_run = args.only if args.only else list(SCRAPERS.keys())
    print(f"  Will process: {scrapers_to_run}")
    
    if args.sequential:
        print(f"  Mode: SEQUENTIAL ({args.wait}s between)")
    else:
        print(f"  Mode: PARALLEL")
    print()
    
    if not args.combine_only:
        if args.sequential:
            for i, name in enumerate(scrapers_to_run):
                if name not in SCRAPERS:
                    print(f"  ⚠ Unknown scraper: {name}")
                    continue
                
                run_scraper(name, SCRAPERS[name])
                
                if i < len(scrapers_to_run) - 1:
                    print(f"\n  ⏳ Waiting {args.wait}s...")
                    time.sleep(args.wait)
        else:
            threads = []
            results_dict = {}
            
            print(f"\n  🚀 Starting {len(scrapers_to_run)} scrapers in parallel...\n")
            
            for name in scrapers_to_run:
                if name not in SCRAPERS:
                    print(f"  ⚠ Unknown scraper: {name}")
                    continue
                
                t = threading.Thread(target=run_scraper_thread, args=(name, SCRAPERS[name], results_dict))
                t.start()
                threads.append((name, t))
                time.sleep(5)
            
            print(f"\n  ⏳ Waiting for all scrapers to complete...")
            for name, t in threads:
                t.join()
                status = "✓" if results_dict.get(name) else "✗"
                print(f"    {status} {name} finished")
    
    # Combine all results
    results = combine_results(scrapers_to_run)
    
    # =====================================================
    # SMART RETRY: Only retry scrapers that mostly worked
    # (Disabled by default - use --retry to enable)
    # =====================================================
    if not args.combine_only and args.retry:
        failures_by_supplier = {}
        
        for r in results:
            supplier = r.get("supplier", "")
            
            is_api = False
            scraper_name = None
            for name, config in SCRAPERS.items():
                if config["supplier_name"] == supplier:
                    is_api = config.get("is_api", False)
                    scraper_name = name
                    break
            
            if is_api:
                continue
            
            reason = check_incomplete_data(r)
            if reason:
                if supplier not in failures_by_supplier:
                    failures_by_supplier[supplier] = []
                failures_by_supplier[supplier].append((r, reason, scraper_name))
        
        # Check each supplier's success rate
        suppliers_to_retry = {}
        suppliers_to_skip = []
        
        print(f"\n{'#'*60}")
        print(f"  ANALYZING FAILURE RATES")
        print('#'*60)
        
        for supplier, failures in failures_by_supplier.items():
            successful, total, rate = get_supplier_success_rate(results, supplier)
            failed_count = len(failures)
            
            print(f"\n  {supplier}:")
            print(f"    Success: {successful}/{total} regions ({rate*100:.0f}%)")
            print(f"    Failed:  {failed_count} regions")
            
            if rate >= RETRY_THRESHOLD:
                print(f"    → Will retry {failed_count} failed regions")
                suppliers_to_retry[supplier] = failures
            else:
                print(f"    → SKIPPING retries (below {RETRY_THRESHOLD*100:.0f}% threshold)")
                print(f"    → Run manually and upload JSON")
                suppliers_to_skip.append(supplier)
        
        # Only retry suppliers that mostly worked
        if suppliers_to_retry:
            total_retries = sum(len(f) for f in suppliers_to_retry.values())
            print(f"\n{'#'*60}")
            print(f"  RETRYING {total_retries} REGIONS")
            print(f"  (Skipping {len(suppliers_to_skip)} mostly-failed scrapers)")
            print('#'*60)
            
            for supplier, failures in suppliers_to_retry.items():
                print(f"\n  📍 {supplier}: {len(failures)} regions")
                
                for r, reason, scraper_name in failures:
                    region = r.get("region", "")
                    postcode = r.get("postcode", "")
                    
                    print(f"\n    Retrying: {region} ({postcode})")
                    print(f"    Reason: {reason}")
                    
                    if not scraper_name:
                        print(f"    ⚠ Unknown scraper, skipping")
                        continue
                    
                    config = SCRAPERS[scraper_name]
                    script = config["script"]
                    
                    if not os.path.exists(script):
                        print(f"    ⚠ Script not found: {script}")
                        continue
                    
                    try:
                        cmd = [sys.executable, script, "--test", postcode, "--headless"]
                        print(f"    Running: {script} --test \"{postcode}\"")
                        subprocess.run(cmd, capture_output=False, text=True)
                        print(f"\n    ⏳ Cooling down 30s...")
                        time.sleep(30)
                    except Exception as e:
                        print(f"    ✗ Error: {e}")
            
            print(f"\n  Re-combining results...")
            results = combine_results(scrapers_to_run)
        
        if suppliers_to_skip:
            print(f"\n{'#'*60}")
            print(f"  ⚠ SCRAPERS THAT NEED MANUAL RUN:")
            print('#'*60)
            for supplier in suppliers_to_skip:
                print(f"    - {supplier}")
            print(f"\n  Run locally and upload JSON files.")
    
    if results:
        save_combined_results(results)
        
        # Final report
        print(f"\n{'='*60}")
        print("  DATA QUALITY REPORT")
        print('='*60)
        
        complete = sum(1 for r in results if not check_incomplete_data(r))
        incomplete = len(results) - complete
        pct = 100 * complete / len(results) if results else 0
        
        print(f"  Complete: {complete}/{len(results)} ({pct:.1f}%)")
        print(f"  Failed:   {incomplete}")
        
        if incomplete > 0:
            print(f"\n  Incomplete by supplier:")
            by_supplier = {}
            for r in results:
                reason = check_incomplete_data(r)
                if reason:
                    s = r.get("supplier", "unknown")
                    if s not in by_supplier:
                        by_supplier[s] = []
                    by_supplier[s].append(f"{r.get('region')}")
            
            for s, regions in by_supplier.items():
                print(f"    {s}: {len(regions)} regions")
    else:
        print("\n  ⚠ No results!")


if __name__ == "__main__":
    main()
