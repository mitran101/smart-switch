"""
One-shot migration: Google Sheets -> Supabase signups table.
Run once after deploying the Supabase changes.

Requirements:
  pip install gspread google-auth requests

Env vars needed:
  GOOGLE_SERVICE_ACCOUNT  - service account JSON (already used in GitHub Actions)
  SUPABASE_SERVICE_KEY    - Supabase service_role key
"""

import os
import sys
import json
import requests
from google.oauth2.service_account import Credentials
import gspread

SUPABASE_URL = 'https://jkiyisnoetcxndwtqoom.supabase.co'
SHEET_ID = '10r_oruP0YcfRHH_k_nhjSDQ6knwgd89EqJ0vfx-v2No'


def get_sheets_client():
    creds_json = os.getenv('GOOGLE_SERVICE_ACCOUNT')
    if not creds_json:
        print("ERROR: GOOGLE_SERVICE_ACCOUNT not set")
        sys.exit(1)
    creds = Credentials.from_service_account_info(
        json.loads(creds_json),
        scopes=['https://www.googleapis.com/auth/spreadsheets.readonly']
    )
    return gspread.authorize(creds)


def get_supabase_headers():
    key = os.getenv('SUPABASE_SERVICE_KEY')
    if not key:
        print("ERROR: SUPABASE_SERVICE_KEY not set")
        sys.exit(1)
    return {
        'apikey': key,
        'Authorization': f'Bearer {key}',
        'Content-Type': 'application/json',
        'Prefer': 'resolution=ignore-duplicates,return=minimal'
    }


def fetch_waitlist(client):
    sheet = client.open_by_key(SHEET_ID).sheet1
    rows = sheet.get_all_values()[1:]  # skip header
    records = []
    for row in rows:
        # Columns: Date(0), Email(1), Unsubscribed(2), Postcode(3),
        #          HouseNumber(4), Street(5), City(6), Region(7),
        #          EnergyRegion(8), ElecUsage(9), GasUsage(10), Source(11)
        email = row[1].strip().lower() if len(row) > 1 else ''
        if not email or '@' not in email:
            continue
        records.append({
            'type': 'waitlist',
            'email': email,
            'unsubscribed': row[2].strip().lower() == 'yes' if len(row) > 2 else False,
            'postcode': row[3].strip() if len(row) > 3 else None,
            'house_number': row[4].strip() if len(row) > 4 else None,
            'street': row[5].strip() if len(row) > 5 else None,
            'city': row[6].strip() if len(row) > 6 else None,
            'region': row[7].strip() if len(row) > 7 else None,
            'energy_region': row[8].strip() if len(row) > 8 else None,
            'elec_usage': float(row[9]) if len(row) > 9 and row[9].strip() else None,
            'gas_usage': float(row[10]) if len(row) > 10 and row[10].strip() else None,
            'source': row[11].strip() if len(row) > 11 and row[11].strip() else 'homepage',
        })
    return records


def fetch_newsletter(client):
    ss = client.open_by_key(SHEET_ID)
    try:
        sheet = ss.worksheet('NewsletterSignups')
    except gspread.exceptions.WorksheetNotFound:
        print("No NewsletterSignups sheet found - skipping")
        return []
    rows = sheet.get_all_values()[1:]  # skip header
    records = []
    for row in rows:
        # Columns: Date(0), Email(1), Unsubscribed(2), Source(3), PageURL(4)
        email = row[1].strip().lower() if len(row) > 1 else ''
        if not email or '@' not in email:
            continue
        records.append({
            'type': 'newsletter',
            'email': email,
            'unsubscribed': row[2].strip().lower() == 'yes' if len(row) > 2 else False,
            'source': row[3].strip() if len(row) > 3 and row[3].strip() else 'switchinsights',
            'page_url': row[4].strip() if len(row) > 4 else None,
        })
    return records


def insert_batch(records, headers, batch_size=100):
    total = len(records)
    inserted = 0
    skipped = 0

    for i in range(0, total, batch_size):
        batch = records[i:i + batch_size]
        res = requests.post(
            f'{SUPABASE_URL}/rest/v1/signups',
            headers=headers,
            json=batch
        )
        if res.ok:
            inserted += len(batch)
        else:
            print(f"  Batch {i}-{i+len(batch)} error {res.status_code}: {res.text[:200]}")
            skipped += len(batch)

    return inserted, skipped


if __name__ == '__main__':
    print("Connecting to Google Sheets...")
    client = get_sheets_client()
    headers = get_supabase_headers()

    print("Fetching waitlist signups...")
    waitlist = fetch_waitlist(client)
    print(f"  Found {len(waitlist)} waitlist records")

    print("Fetching newsletter signups...")
    newsletter = fetch_newsletter(client)
    print(f"  Found {len(newsletter)} newsletter records")

    all_records = waitlist + newsletter
    print(f"\nInserting {len(all_records)} total records into Supabase (duplicates ignored)...")

    ins, skip = insert_batch(all_records, headers)
    print(f"\nDone - Inserted: {ins} | Errors: {skip}")
    print("Duplicates (emails already in Supabase) were silently ignored.")
