# market_analyzer.py
from screener_module import Screener
from signals import DeltaNeutralTrader
import math
from datetime import datetime

class AdvancedMarketAnalyzer(Screener):
  def __init__(self, api_key, mongo_endpoints):
        # Store credentials explicitly in child class
        self.api_key = api_key
        self.mongo_endpoints = mongo_endpoints
        
        # Initialize parent with required params
        super().__init__(api_key, mongo_endpoints)
        
        self._volume_profile_cache = {}
        self._oi_cache = {}
    # ... rest of existing code ...
    
  def calculate_volume_profile(self, symbol, window=30):
    historical = self._fetch_historical(symbol, window)
    if not historical:
        return None
        
    try:
        closes = [d['close'] for d in historical if 'close' in d]
        volumes = [d['volume'] for d in historical if 'volume' in d]
        
        if len(closes) != len(volumes) or len(closes) == 0:
            return None
            
        # Rest of existing calculation...
        return profile
        
    except KeyError as e:
        print(f"Missing field in historical data: {str(e)}")
        return None
  def analyze_oi_concentration(self, symbol):
    """Standalone OI analysis with validation"""
    chain = self.fetch_option_chain(symbol)
    if not chain or 'records' not in chain:
        return None
        
    valid_calls = []
    valid_puts = []
    
    for s in chain['records']['data']:
        # Validate CE data
        if 'CE' in s and 'openInterest' in s['CE']:
            valid_calls.append((s['strikePrice'], s['CE']['openInterest']))
        # Validate PE data
        if 'PE' in s and 'openInterest' in s['PE']:
            valid_puts.append((s['strikePrice'], s['PE']['openInterest']))

    if not valid_calls or not valid_puts:
        return None

    max_call = max(valid_calls, key=lambda x: x[1], default=(0, 0))
    max_put = max(valid_puts, key=lambda x: x[1], default=(0, 0))

    return {
        'call_max_oi': max_call[0],
        'put_max_oi': max_put[0],
        'call_oi': max_call[1],
        'put_oi': max_put[1]
    }
        
    
  def _fetch_historical(self, symbol, days=30):
        """Fetch historical price data from MongoDB"""
        try:
            return self.mongo_connection.find_many(
                "historical_data",
                "myFirstDatabase",
                filter={"symbol": symbol},
                sort={"date": -1},
                limit=days
            )
        except Exception as e:
            print(f"Historical data fetch failed: {str(e)}")
            return None

  def _fetch_intraday_data(self, symbol):
        """Fetch intraday data from MongoDB"""
        try:
            return self.mongo_connection.find_many(
                "intraday_data",
                "myFirstDatabase",
                filter={"symbol": symbol},
                sort={"timestamp": -1},
                limit=100  # Last 100 data points
            )
        except Exception as e:
            print(f"Intraday data fetch failed: {str(e)}")
            return None

class IntradayBandGenerator:
   def __init__(self, api_key, mongo_endpoints):  # No "symbol" parameter
        self.api_key = api_key
        self.mongo_endpoints = mongo_endpoints

    
   def calculate_dynamic_bands(self, intraday_data):
    try:
        if not intraday_data or len(intraday_data) < 10:
            raise ValueError("Insufficient intraday data points")
            
        highs = [d['high'] for d in intraday_data if 'high' in d]
        lows = [d['low'] for d in intraday_data if 'low' in d]
        closes = [d['close'] for d in intraday_data if 'close' in d]
        
        if len(highs) != len(lows) or len(highs) == 0:
            raise ValueError("Invalid intraday data format")

        # Calculate True Range
        tr = [highs[0] - lows[0]]
        for i in range(1, len(closes)):
            tr.append(max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i-1]),
                abs(lows[i] - closes[i-1])
            ))
        
        # Validate ATR calculation
        atr_values = tr[-self.atr_window:]
        if len(atr_values) == 0:
            raise ValueError("No data available for ATR calculation")
            
        atr = sum(atr_values) / len(atr_values)
        
        return {
            'upper': closes[-1] + 2*atr,
            'lower': closes[-1] - 2*atr,
            'atr': atr,
            'timestamp': datetime.now().isoformat()
        }
        
    except Exception as e:
        print(f"Band Calculation Error: {str(e)}")
        return None