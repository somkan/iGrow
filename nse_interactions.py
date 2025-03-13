# nse_interactions.py
import requests
from datetime import datetime

class NSEInteractions:
    def __init__(self):
        
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.nseindia.com/get-quotes/derivatives",
        }

    def fetch_option_chain(self, symbol):
        url = f"https://www.nseindia.com/api/option-chain-indices?symbol={symbol}"
        session = requests.Session()
        session.get("https://www.nseindia.com", headers=self.headers)  # Generate cookies
        response = session.get(url, headers=self.headers)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Failed to fetch options chain data. Status code: {response.status_code}")
            return None
    # Add this method to NSEInteractions class
    def _fallback_expiry(self):
      """Calculate next Thursday if API fails"""
      today = datetime.now().date()
      days_to_thursday = (3 - today.weekday()) % 7
      return (today + timedelta(days=days_to_thursday)).strftime("%d-%b-%Y")

    def get_expiry_dates(self, option_chain):
        return option_chain["records"]["expiryDates"]

    def get_underlying_price(self, option_chain):
        return option_chain["records"]["underlyingValue"]