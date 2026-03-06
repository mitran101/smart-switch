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

    # Open your spreadsheet - update this to your sheet's name or ID
    sheet = client.open("SwitchPilot Subscribers").sheet1
    
    # Get column B (emails), skip header
    emails = sheet.col_values(2)[1:]
    
    # Filter valid emails
    emails = [e.strip() for e in emails if e and '@' in e]
    return emails

if __name__ == "__main__":
    for email in fetch_subscribers():
        print(email)
