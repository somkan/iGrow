# screener_module.py
from datetime import datetime
from signals import DeltaNeutralTrader
from mongodb_connection import MongoDBConnection
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import time

class Screener:
   def __init__(self, api_key, mongo_endpoints):
        self.mongo_connection = MongoDBConnection(api_key, mongo_endpoints)
        self.session = self._create_robust_session()
        self.last_request_time = 0
        self.request_interval = 2  # 2-second delay between requests
        self._strategies = {}  # Symbol-specific strategy cache

   def _get_strategy(self, symbol):
        """Get or create strategy instance for each symbol"""
        if symbol not in self._strategies:
            self._strategies[symbol] = DeltaNeutralTrader(symbol=symbol)
            print(f"Initialized strategy for {symbol}")
        return self._strategies[symbol]

   def _create_robust_session(self):
        """Create session with enhanced retry logic and headers"""
        session = requests.Session()
        
        retry = Retry(
            total=5,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"]
        )
        
        adapter = HTTPAdapter(
            max_retries=retry,
            pool_connections=15,
            pool_maxsize=15
        )
        
        session.mount('https://', adapter)
        
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            'Accept': 'application/json',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.nseindia.com/',
            'Connection': 'keep-alive'
        })
        
        return session

   def _rate_limited_request(self, url):
        """Enforce rate limiting and maintain session cookies"""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.request_interval:
            time.sleep(self.request_interval - elapsed)
        
        try:
            # Refresh cookies every 5 minutes
            if not self.session.cookies or time.time() - self.last_request_time > 300:
                self.session.get('https://www.nseindia.com', timeout=15)
            
            response = self.session.get(url, timeout=25)
            response.raise_for_status()
            self.last_request_time = time.time()
            return response.json()
            
        except Exception as e:
            print(f"Request failed: {str(e)}")
            # Reset session on critical errors
            if isinstance(e, (requests.exceptions.ConnectionError, 
                            requests.exceptions.Timeout)):
                self.session = self._create_robust_session()
            return None

   def fetch_option_chain(self, symbol):
        """Fetch option chain for given symbol"""
        url = f'https://www.nseindia.com/api/option-chain-indices?symbol={symbol}'
        return self._rate_limited_request(url)

   def screen_opportunities(self, symbol):
        try:
            # Get symbol-specific strategy
            strategy = self._get_strategy(symbol)
            
            # Fetch option chain
            option_chain = self.fetch_option_chain(symbol)
            if not option_chain or 'records' not in option_chain:
                print(f"Invalid/missing data for {symbol}")
                return []

            # Refresh strategy with latest data
            strategy._refresh_data()
            
            # Generate signals for current symbol
            signals = strategy.generate_signals()

            # Extract common data
            spot_price = option_chain['records']['data'][0]['PE']['underlyingValue']
            expiry = option_chain['records']['expiryDates'][0]

            opportunities = []
            for record in option_chain['records']['data']:
                if record['expiryDate'] != expiry:
                    continue

                if 'CE' not in record or 'PE' not in record:
                    continue

                # Extract strike details
                strike = record['strikePrice']
                call = record['CE']
                put = record['PE']

                # Find matching signals
                ce_signal = next(
                    (sig for sig in signals
                     if sig['strike'] == strike and sig['option_type'] == 'CE'),
                    None
                )
                pe_signal = next(
                    (sig for sig in signals
                     if sig['strike'] == strike and sig['option_type'] == 'PE'),
                    None
                )

                if not ce_signal or not pe_signal:
                    continue

                # Calculate composite scores
                ce_score = ce_signal.get('score', 0.5)
                pe_score = pe_signal.get('score', 0.5)
                
                # Trigger conditions
                composite_trigger = (ce_score <= 0.3 or ce_score >= 0.7 or
                                    pe_score <= 0.3 or pe_score >= 0.7)
                delta_trigger = abs(ce_signal['details']['delta'] + 
                                   pe_signal['details']['delta']) > 0.1
                parity_trigger = (abs(ce_signal['details']['parity_mispricing']) > 0.1 or
                                 abs(pe_signal['details']['parity_mispricing']) > 0.1)
                iv_trigger = (ce_signal['details']['iv_discrepancy'] > 0.5 or
                             pe_signal['details']['iv_discrepancy'] > 0.5)

                # Open Interest analysis
                ce_oi = call.get('openInterest', 0)
                pe_oi = put.get('openInterest', 0)
                ce_oi_change = call.get('pChangeinOpenInterest', 0)
                pe_oi_change = put.get('pChangeinOpenInterest', 0)
                oi_trigger = (ce_oi_change > 10 or pe_oi_change > 10 or
                             ce_oi > 1000000 or pe_oi > 1000000)

                if any([composite_trigger, delta_trigger, 
                       parity_trigger, iv_trigger, oi_trigger]):
                    
                    opportunities.append({
                        'symbol': symbol,
                        'strike': strike,
                        'expiry': expiry,
                        'call_price': call.get('bidprice', 0),
                        'put_price': put.get('askPrice', 0),
                        'call_action': ce_signal['action'],
                        'put_action': pe_signal['action'],
                        'reasoning': [
                            f"CE: {ce_signal['valuation_message']} (Score: {ce_score:.2f})",
                            f"PE: {pe_signal['valuation_message']} (Score: {pe_score:.2f})",
                            f"Composite Score: {(ce_score + pe_score)/2:.2f}",
                            f"CE OI: {ce_oi:,} ({ce_oi_change:.1f}%)",
                            f"PE OI: {pe_oi:,} ({pe_oi_change:.1f}%)"
                        ],
                        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        'status': 'OPEN',
                        'iv_discrepancies': {
                            'CE': ce_signal['details']['iv_discrepancy'],
                            'PE': pe_signal['details']['iv_discrepancy']
                        },
                        'open_interest': {
                            'CE': ce_oi,
                            'PE': pe_oi,
                            'CE_change': ce_oi_change,
                            'PE_change': pe_oi_change
                        },
                        'trigger_reasons': [
                            *(['Delta'] if delta_trigger else []),
                            *(['Parity'] if parity_trigger else []),
                            *(['IV'] if iv_trigger else []),
                            *(['Composite'] if composite_trigger else []),
                            *(['OI'] if oi_trigger else [])
                        ]
                    })

            return opportunities

        except Exception as e:
            print(f"Error screening {symbol}: {str(e)}")
            return []
   def get_alerts(self, symbol=None):
      """Fetch alerts from MongoDB. Handle empty results gracefully."""
      try:
        # Define the filter based on the symbol
        filter = {"symbol": symbol} if symbol else {}

        # Fetch alerts from MongoDB using find operation
        alerts = self.mongo_connection.find_many(
            "alerts", "myFirstDatabase",
            filter=filter,
            sort={"timestamp": -1},  # Sort by timestamp in descending order
            limit=10  # Limit to the last 10 alerts
        )

        # Check if alerts is None or empty
        if not alerts:
            return []  # Return an empty list if no alerts are found

        return alerts

      except Exception as e:  # Properly indented under try
        print(f"Error fetching alerts: {e}")
        return []  # Return an empty list in case of any error
   def save_alerts(self, alerts):
     """Save alerts with enhanced validation"""
     if not alerts:
        print("No alerts to save")
        return {"status": "skipped"}

    # Validate alert structure
     valid_alerts = []
     for alert in alerts:
        if not all(key in alert for key in ['symbol', 'strike', 'timestamp']):
            print(f"Invalid alert skipped: {alert}")
            continue
        valid_alerts.append(alert)

    # Delete existing alerts
     symbols = list({alert['symbol'] for alert in valid_alerts})
     delete_results = []
     for symbol in symbols:
        result = self.mongo_connection.delete_many(
            "alerts", "myFirstDatabase",
            {"symbol": symbol}
        )
        if result:
            delete_results.append(result)
            print(f"Deleted {result.get('deletedCount', 0)} {symbol} alerts")
        else:
            print(f"Failed to delete {symbol} alerts")

    # Insert new alerts
     insert_result = self.mongo_connection.insert_many(
        "alerts", "myFirstDatabase", valid_alerts
         )
    
     if insert_result:
         print(f"Inserted {len(valid_alerts)} alerts")
         return {
            "deleted": sum(r.get('deletedCount', 0) for r in delete_results),
            "inserted": len(valid_alerts)
          }
         return {"error": "Failed to save alerts"}

   def update_alert_status(self, alert_id, status, profit=None, trade_outcome=None):
        """Update alert status with proper type conversion"""
        update_data = {"status": status}
        if profit is not None:
            update_data["profit"] = float(profit)
        if trade_outcome is not None:
            update_data["trade_outcome"] = str(trade_outcome)

        return self.mongo_connection.update_one(
            "alerts", "myFirstDatabase",
            {"_id": {"$oid": alert_id}},
            {"$set": update_data}
        )
    
   def get_available_strikes(self, symbol):
        """Get available strike prices for a symbol"""
        option_chain = self.fetch_option_chain(symbol)
        if not option_chain:
            return []
            
        return sorted({
            record['strikePrice'] 
            for record in option_chain['records']['data']
            if record['expiryDate'] == option_chain['records']['expiryDates'][0]
        })

   def get_option_details(self, symbol, strike):
    """Get detailed analysis for specific symbol/strike"""
    try:
        strike = float(strike)
        opportunities = self.screen_opportunities(symbol)
        
        # Find matching opportunity
        for opp in opportunities:
            if opp['strike'] == strike:
                # Fetch the correct spot price and expiry from the option chain
                option_chain = self.fetch_option_chain(symbol)
                if not option_chain or 'records' not in option_chain:
                    return {'error': 'Failed to fetch option chain data'}
                
                # Extract spot price and expiry date
                spot_price = option_chain['records']['data'][0]['PE']['underlyingValue']
                expiry_date = option_chain['records']['expiryDates'][0]  # Nearest expiry
                
                return {
                    'symbol': opp['symbol'],
                    'strike': opp['strike'],
                    'expiry_date': expiry_date,  # Add expiry date
                    'call_price': opp['call_price'],
                    'put_price': opp['put_price'],
                    'call_action': opp['call_action'],
                    'put_action': opp['put_action'],
                    'iv_discrepancies': opp['iv_discrepancies'],
                    'reasoning': opp['reasoning'],
                    'open_interest': opp['open_interest'],
                    'trigger_reasons': opp['trigger_reasons'],
                    'call_valuation': f"{opp['call_action']} (Score: {opp['reasoning'][0].split('Score: ')[1].split(')')[0]})",
                    'put_valuation': f"{opp['put_action']} (Score: {opp['reasoning'][1].split('Score: ')[1].split(')')[0]})",
                    'composite_score_ce': float(opp['reasoning'][0].split('Score: ')[1].split(')')[0]),
                    'composite_score_pe': float(opp['reasoning'][1].split('Score: ')[1].split(')')[0]),
                    'spot_price': spot_price
                }
        
        return {'error': 'No data found for selected parameters'}
        
    except Exception as e:
        print(f"Error getting details: {str(e)}")
        return {'error': str(e)}