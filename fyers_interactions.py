# fyers_interactions.py
from fyers_apiv3 import fyersModel
import os
import requests
import json

class FyersInteractions:
    def __init__(self, client_id, access_token):
        self.client_id = client_id
        self.access_token = access_token
        self.fyers = self._initialize_fyers()

    def _initialize_fyers(self):
        return fyersModel.FyersModel(
            client_id=self.client_id,
            token=self.access_token,
            log_path=os.getcwd()
        )

    def update_token(self, new_token):
        """Update access token dynamically"""
        self.access_token = new_token
        self.fyers = self._initialize_fyers()

    @staticmethod
    def refresh_token(client_id, refresh_token):
        """Static method to refresh access token"""
        url = "https://api.fyers.in/api/v2/validate-refresh-token"
        payload = {
            "grant_type": "refresh_token",
            "appId": client_id,
            "refresh_token": refresh_token
        }
        response = requests.post(url, json=payload)
        return response.json()['access_token']

    # Rest of existing methods remain unchanged
    
    def place_order(self, symbol, quantity, side, strike, order_type=2):
        """Place orders through Fyers API with strike validation
        Args:
            symbol: Full option symbol (e.g., NSE:NIFTY25MAR22400CE)
            quantity: Number of lots
            side: -1 = Sell, 1 = Buy
            strike: Expected strike price for validation
            order_type: 2 = Limit Order (default)
        """
        try:
            # Extract strike from symbol
            parts = symbol.split(self.client_id.split('-')[0])[-1].split('CE')[0].split('PE')[0]
            current_strike = int(''.join(filter(str.isdigit, parts)))
            
            if current_strike != strike:
                raise ValueError(f"Strike mismatch: {current_strike} vs {strike}")

            payload = {
                "symbol": symbol,
                "qty": quantity,
                "type": order_type,
                "side": side,
                "productType": "INTRADAY",
                "validity": "DAY"
            }
            
            response = self.fyers.place_order(data=payload)
            return response
        
        except Exception as e:
            print(f"Order placement failed: {str(e)}")
            return None

    def exit_position(self, symbol):
        data = {"id": f"{symbol}-INTRADAY"}
        return self.fyers.exit_positions(data=data)
    
    def get_quotes(self, symbols):
        return self.fyers.quotes(data={"symbols": symbols})