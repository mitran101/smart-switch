import os
import requests

SUPABASE_URL = 'https://jkiyisnoetcxndwtqoom.supabase.co'

def fetch_subscribers():
    """Fetch all active (non-unsubscribed) email addresses from Supabase."""
    service_key = os.getenv('SUPABASE_SERVICE_KEY')
    if not service_key:
        print("ERROR: SUPABASE_SERVICE_KEY secret not set", file=__import__('sys').stderr)
        return []

    headers = {
        'apikey': service_key,
        'Authorization': f'Bearer {service_key}'
    }

    response = requests.get(
        f'{SUPABASE_URL}/rest/v1/signups?unsubscribed=eq.false&select=email',
        headers=headers
    )
    response.raise_for_status()
    return [row['email'] for row in response.json()]

if __name__ == "__main__":
    for email in fetch_subscribers():
        print(email)
