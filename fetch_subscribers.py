import gspread
import json
import os
from google.oauth2.service_account import Credentials

def fetch_subscribers():
    """Fetch email addresses from Sheet1, column B"""
    creds_json = os.getenv('GOOGLE_SERVICE_ACCOUNT')
    if not creds_json:
        print("ERROR: GOOGLE_SERVICE_ACCOUNT secret not set", file=__import__('sys').stderr)
        return []

    creds_dict = json.loads(creds_json)
    creds = Credentials.from_service_account_info(creds_dict, scopes=[
        'https://www.googleapis.com/auth/spreadsheets.readonly'
    ])
    client = gspread.authorize(creds)

    # Open by ID from your Apps Script
    sheet = client.open_by_key("10r_oruP0YcfRHH_k_nhjSDQ6knwgd89EqJ0vfx-v2No").sheet1
    
    # Get all data, skip header
    rows = sheet.get_all_values()[1:]
    
    # Column B = email, Column C = unsubscribed ("yes" means skip)
    emails = [row[1].strip() for row in rows if row[1] and '@' in row[1] and row[2] != 'yes']
    return emails

if __name__ == "__main__":
    for email in fetch_subscribers():
        print(email)
