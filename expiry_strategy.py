from datetime import datetime, timedelta
import math
from mongodb_connection import MongoDBConnection
from nse_interactions import NSEInteractions
from fyers_interactions import FyersInteractions
from signals import DeltaNeutralTrader
import pytz

    
class ExpiryStrategy:
    def __init__(self, symbol, user, api_key, mongo_endpoints):
        self.symbol = symbol
        self.user = user
        self.api_key = api_key
        self.mongo_endpoints = mongo_endpoints
        self.mongo_connection = MongoDBConnection(api_key, mongo_endpoints)
        self.nse_interactions = NSEInteractions()
        self.processed_trades_collection = "processed_trades"
        self.trade_collection = "trade_signals"  # Collection name
        self.db_name = "myFirstDatabase"         # Database name
        

        # Original initialization with credentials
        self.fyers_interactions = FyersInteractions(
            client_id=self.read_auth(user),
            access_token=self.read_file(user)
        )
        
        self.processed_buy_signals = set()
        self.TRADE_SCHEMA = {
            "user": {"type": str, "required": True},
            "symbol": {"type": str, "required": True},
            "generated_symbol": {"type": str, "required": True},
            "signal": {"type": str, "enum": ["BUY", "SELL"], "required": True},
            "signal_price": {"type": float, "required": True},
            "status": {"type": str, "enum": ["PENDING", "EXECUTED", "FAILED"], "default": "PENDING"},
            "execution_price": {"type": float},
            "error": {"type": str},
            "signal_timestamp": {"type": datetime, "default": datetime.utcnow},
            "execution_timestamp": {"type": datetime},
            "quantity": {"type": int, "required": True}
             }
        try:
            client_id = self.read_auth(user)
            access_token = self.read_file(user)
            self.fyers_interactions = FyersInteractions(client_id, access_token)
        except Exception as e:
            print(f"Failed to initialize Fyers: {e}")
            self.fyers_interactions = None  # Explicitly set to None
  
    
    # Add new token management methods
    def refresh_auth_token(self):
     """Refresh access token using refresh token"""
     try:
        # Get refresh token from MongoDB
        response = self.mongo_connection.find_one(
            "refresh_tokens", "myFirstDatabase", {"userid": self.user}
        )
        
        # Check if response contains the expected data
        if not response or 'document' not in response or 'refresh_token' not in response['document']:
            raise ValueError("Invalid or missing refresh token in MongoDB response")
        
        refresh_token = response["document"]["refresh_token"]
        
        # Get new access token
        new_token = FyersInteractions.refresh_token(
            self.read_auth(self.user), refresh_token
        )
        
        # Update MongoDB
        self.mongo_connection.update_one(
            "access_token", "myFirstDatabase",
            {"userid": self.user},
            {"$set": {"access_token": new_token}}
        )
        
        # Update current instance
        self.fyers_interactions.update_token(new_token)
        return new_token
        
     except Exception as e:
        print(f"Token refresh failed: {e}")
        raise

    def get_valid_token(self):
        """Get token with validity check"""
        try:
            # Test token validity
            test_response = self.fyers_interactions.get_quotes("NSE:NIFTY50-INDEX")
            if test_response.get('code') != 200:
                raise ValueError("Token validation failed")
            return self.read_file(self.user)
        except Exception as e:
            if "invalid access token" in str(e).lower():
                return self.refresh_auth_token()
            raise

    
    
    def read_auth(self, user):
        response = self.mongo_connection.find_one("Auth_Data", "myFirstDatabase", {"userid": user})
        if response and "document" in response:
            return response["document"]["app_id"]
        raise ValueError(f"No document found for user {user} in Auth_Data collection.")

    def read_file(self, user):
        response = self.mongo_connection.find_one("access_token", "myFirstDatabase", {"userid": user})
        if response and "document" in response:
            return response["document"]["access_token"]
        raise ValueError(f"No access token found for user {user}.")
    
    # In ExpiryStrategy class
    def determine_order_type(self):
    # Your strategy logic to determine BUY/SELL
      if self.market_condition() == 'OVERSOLD':
        return 'BUY'
      elif self.market_condition() == 'OVERBOUGHT':
        return 'SELL'
      return None
    def execute_order(self, order_type):
        if order_type == 'BUY':
            self._execute_buy()
        elif order_type == 'SELL':
            self._execute_sell()

    def _execute_buy(self):
        symbol = f"NSE:{self.symbol}24FUT"  # Example futures symbol
        self.fyers_interactions.place_order(
        symbol=symbol,
        quantity=75,
        side=1  # Buy
         )

    def _execute_sell(self):
       symbol = f"NSE:{self.symbol}24FUT"  # Example futures symbol
       self.fyers_interactions.place_order(
        symbol=symbol,
        quantity=75,
        side=-1  # Sell
         )
      
    def get_trading_data(self, symbols, place_order=False):
        trading_data = []
        for symbol in symbols:
            try:
                print(f"\nProcessing {symbol}")

                # Fetch and validate option chain
                option_chain = self.nse_interactions.fetch_option_chain(symbol)
                if not option_chain or 'records' not in option_chain:
                    print(f"Skipping {symbol}: Invalid NSE response")
                    continue

                # Extract spot price safely
                spot_price = option_chain['records']['underlyingValue']
                if not spot_price or spot_price <= 0:
                    raise ValueError(f"Invalid spot price for {symbol}")

                # Extract expiry date
                expiry = option_chain["records"]["expiryDates"][0]
                date_obj = datetime.strptime(expiry, "%d-%b-%Y")
                days_to_expiry = (date_obj - datetime.now()).days + 1

                # Fetch futures data with token refresh
                fut_symbol = self._generate_futures_symbol(symbol, date_obj)
                fut_response = self._get_fyers_quotes(fut_symbol)
                
                if not fut_response:
                    raise ValueError(f"Invalid futures data for {symbol}")

                fut_data = fut_response['d'][0]['v']
                prev_close = fut_data['prev_close_price']
                current_open = fut_data['open_price']

                # Determine option parameters
                option_type, strike_price = self._calculate_option_params(
                    current_open, prev_close, spot_price
                )

                # Generate proper Fyers symbol
                option_symbol = self._generate_option_symbol(
                    symbol, date_obj, strike_price, option_type
                )

                # Fetch and validate option data
                opt_response = self._get_fyers_quotes(option_symbol)
                if not opt_response:
                    raise ValueError(f"Invalid option data for {symbol}")
                opt_data = opt_response['d'][0]['v']

                # Get IV from option chain
                iv = self._get_implied_volatility(
                    option_chain, strike_price, option_type
                )

                  # Generate signals
                dn_trader = DeltaNeutralTrader(symbol=symbol)
                signals = dn_trader.generate_signals()
                matched_signal = next(
                    (sig for sig in signals 
                     if isinstance(sig, dict) 
                     and sig.get('strike') == strike_price 
                     and sig.get('option_type') == option_type),
                    None
                )

                # Build trading data with actual signals
                trading_data.append(self._build_trading_data(
                    symbol, 
                    fut_data,
                    opt_data,
                    option_type,
                    strike_price,
                    iv,
                    option_symbol,
                    matched_signal  # Pass the matched signal
                ))

                # Order execution logic
                self._handle_order_execution(symbol, option_symbol, place_order, opt_data)

            except Exception as e:
                print(f"Error processing {symbol}: {e}")
                trading_data.append({'symbol': symbol, 'error': str(e)})

        return trading_data

    def _generate_futures_symbol(self, symbol, date_obj):
        """Generate futures symbol based on expiry date"""
        return f"NSE:{symbol}{date_obj.strftime('%y%b').upper()}FUT"

    def _get_fyers_quotes(self, symbol):
        """Get quotes with token refresh handling"""
        response = self.fyers_interactions.get_quotes(symbol)
        if response.get('code') == -15:  # Token expired
            print("Refreshing access token...")
            self.refresh_auth_token()
            response = self.fyers_interactions.get_quotes(symbol)
        return response

    def _calculate_option_params(self, current_open, prev_close, spot_price):
        """Calculate option type and strike price"""
        price_diff = current_open - prev_close
        option_type = 'CE' if price_diff < 0 else 'PE'
        strike_base = current_open
        
        # Calculate nearest valid strike price
        if option_type == 'CE':
            strike_price = (math.floor(strike_base / 100) * 100) + 100
        else:
            strike_price = (math.ceil(strike_base / 100) * 100) - 100
            
        if strike_price <= 0:
            raise ValueError(f"Invalid calculated strike price: {strike_price}")
            
        return option_type, strike_price

    def _generate_option_symbol(self, symbol, date_obj, strike_price, option_type):
      """Generate Fyers-compliant option symbol for weekly/monthly expiry"""
      # Format strike price as integer without decimals
      strike = str(int(strike_price))
    
      if symbol == "NIFTY" and not self.is_last_thursday(date_obj):
        # Weekly expiry format: YYMDD (e.g., 25313 for 13-Mar-2025)
        year_short = date_obj.strftime("%y")          # "25"
        month_raw = str(date_obj.month)               # "3" (no zero-pad)
        day_padded = date_obj.strftime("%d")          # "13"
        expiry_part = f"{year_short}{month_raw}{day_padded}"  # "25313"
      else:
        # Monthly expiry format: YYMON (e.g., 25MAR)
        expiry_part = date_obj.strftime("%y%b").upper()  # "25MAR"
    
      return f"NSE:{symbol}{expiry_part}{strike}{option_type}"
    def _get_implied_volatility(self, option_chain, strike_price, option_type):
        """Safely get implied volatility from option chain"""
        try:
            return next(
                item[option_type]['impliedVolatility']
                for item in option_chain['records']['data']
                if option_type in item and item['strikePrice'] == strike_price
            )
        except StopIteration:
            print(f"No IV data found for {strike_price}{option_type}")
            return 0

    # Modify the _build_trading_data method
    def _build_trading_data(self, symbol, fut_data, opt_data, option_type,
                      strike_price, iv, option_symbol, matched_signal):
       """Construct the trading data dictionary using actual signals"""
       return {
          'symbol': symbol,
          'futures': {
            'previousClose': fut_data['prev_close_price'],
            'currentOpen': fut_data['open_price']
            },
        'option': {
            'open': opt_data['open_price'],
            'current': opt_data['lp'],
            'high': opt_data['high_price'],
            'type': option_type,
            'strike': strike_price,
            'iv': iv
            },
        'valuation': {
            'status': '|'.join(matched_signal.get('details', {}).get('trigger_reasons', [])) if matched_signal else 'NO_SIGNAL',
            'message': matched_signal.get('valuation_message', 'No message') if matched_signal else 'No matching signal',
            'signal': matched_signal.get('action', 'HOLD') if matched_signal else 'HOLD',
            'iv_discrepancies': [matched_signal.get('details', {}).get('iv_discrepancy', 0)] if matched_signal else []
             },
        'generated_symbol': option_symbol
           }

       # Update where trading data is appended
       trading_data.append(self._build_trading_data(
       symbol, fut_data, opt_data, option_type,
       strike_price, iv, option_symbol, matched_signal  # Add matched_signal
        ))

    def _get_valuation_data(self, strike_price, option_type):
        """Generate valuation data from signals"""
        # Implement your signal generation logic here
        return {
            'status': 'NO_SIGNAL',
            'message': 'Placeholder',
            'signal': 'HOLD',
            'iv_discrepancies': []
        }

    def _handle_order_execution(self, symbol, option_symbol, place_order, opt_data):
        """Handle order execution logic"""
        if place_order:
            try:
                self.fyers_interactions.place_order(
                    symbol=option_symbol,
                    quantity=75 if symbol == "NIFTY" else 30,
                    side=-1 if opt_data['lp'] < opt_data['open_price'] else 1,
                    limit_price=opt_data['open_price'],
                    stop_loss=opt_data['open_price'] * 0.98,
                    take_profit=opt_data['open_price'] * 1.02
                )
            except Exception as e:
                print(f"Order failed for {option_symbol}: {e}")
    
    def exit_pos(self, symbol, option_strike):
        try:
            self.fyers_interactions.exit_position(option_strike)
            print(f"Exited position for {symbol}: {option_strike}")
        except Exception as e:
            print(f"Error exiting position for {symbol}: {e}")

    def is_last_thursday(self, date):
        last_day = (date.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        return date.weekday() == 3 and (last_day - date).days < 7
   
    def check_trade_exists(self, symbol, generated_symbol, current_date):
      """Check if a valid trade exists for today with matching criteria"""
      try:
        # Convert date to MongoDB's date format
        start_of_day = datetime(current_date.year, current_date.month, current_date.day)
        iso_date = start_of_day.isoformat() + 'Z'

        response = self.mongo_connection.find_one(
            self.trade_collection,
            self.db_name,
            {
                "symbol": symbol,
                "generated_symbol": generated_symbol,
                "user": self.user,
                "signal_timestamp": {"$gte": iso_date},
                "status": {"$in": ["executed", "pending"]}
            }
        )
        
        # Debug log the actual query
        print(f"Trade check query: symbol={symbol}, generated_symbol={generated_symbol}, date={iso_date}")
        print(f"Query response: {response}")

        return bool(response and response.get('document'))

      except Exception as e:
        print(f"Trade check error: {str(e)}")
        return False  # Assume no existing trade if check fails
    def store_trade(self, trade_details):
     utc_now = datetime.utcnow()
    
       # Convert UTC to IST
     ist_timezone = pytz.timezone('Asia/Kolkata')
     ist_now = utc_now.replace(tzinfo=pytz.utc).astimezone(ist_timezone)
    
     print(f"Storing trade: {trade_details}")  # Debug
     try:
        # Add validation
        required_fields = ['symbol', 'generated_symbol', 'signal', 'quantity']
        for field in required_fields:
            if field not in trade_details:
                raise ValueError(f"Missing required field: {field}")
         # Add IST timestamps to trade details
        trade_details.update({
            "signal_timestamp": ist_now.isoformat()  # IST timestamp
         #   "signal_timestamp_utc": utc_now.isoformat()  # Optional: Store UTC as well
        })
        result = self.mongo_connection.insert_one(
            self.trade_collection,
            self.db_name,
            trade_details
        )
        print(f"MongoDB insert result: {result}")  # Debug
        return result
     except Exception as e:
        print(f"Error storing trade: {str(e)}")
        return {"error": str(e)}

    def update_trade_status(self, trade_id, status, execution_price=None, error=None):
       utc_now = datetime.utcnow()
    
       # Convert UTC to IST
       ist_timezone = pytz.timezone('Asia/Kolkata')
       ist_now = utc_now.replace(tzinfo=pytz.utc).astimezone(ist_timezone)
    
       update_data = {
        "$set": {  # Add $set operator here
            "status": status,
            "execution_timestamp": ist_now.isoformat()
        }
        }
    
       if execution_price is not None:
          update_data["$set"]["execution_price"] = execution_price
        
       if error is not None:
         update_data["$set"]["error"] = str(error)[:250]

       return self.mongo_connection.update_one(
         self.trade_collection,
         self.db_name,
         {"_id": {"$oid": trade_id}},
         update_data  # Pass the full update document
         )
       print(f"MongoDB update result: {result}")  # Debug
       return result
     
        
    def record_new_trade(self, symbol, signal_details):
     trade_doc = {
        "user": self.user,
        "symbol": symbol,
        "generated_symbol": signal_details['generated_symbol'],
        "signal": signal_details['signal'],
        "signal_price": signal_details['current_price'],
        "quantity": signal_details['quantity'],
        "status": "PENDING"
     }
    
     self._validate_trade_doc(trade_doc)  # Optional validation
    
     return self.mongo_connection.insert_one(
        self.trade_collection,  # Collection name
        self.db_name,           # Database name
        trade_doc
    )

    def execute_order(self, order_type):
     try:
        if order_type == 'BUY':
            response = self._execute_buy()
        elif order_type == 'SELL':
            response = self._execute_sell()
        
        # Check if the order was successfully placed
        if response and response.get('code') == 200:
            self.update_trade_status(response['id'], "EXECUTED", execution_price=response['price'])
        else:
            self.update_trade_status(response['id'], "FAILED", error="Order placement failed")
     except Exception as e:
        self.update_trade_status(response['id'], "FAILED", error=str(e))

    def _execute_buy(self):
      symbol = f"NSE:{self.symbol}24FUT"  # Example futures symbol
      response = self.fyers_interactions.place_order(
        symbol=symbol,
        quantity=75,
        side=1  # Buy
      )
      return response

    def _execute_sell(self):
     symbol = f"NSE:{self.symbol}24FUT"  # Example futures symbol
     response = self.fyers_interactions.place_order(
        symbol=symbol,
        quantity=75,
        side=-1  # Sell
     )
     return response

    def get_pending_trades(self):
        """Retrieve pending trades"""
        return self.mongo_connection.find_all(
            self.trades_collection,
            "myFirstDatabase",
            {"status": "pending"}
        )
    def _validate_trade_doc(self, document):
        """Optional validation using schema"""
        for field, config in self.TRADE_SCHEMA.items():
            if config.get('required') and field not in document:
                raise ValueError(f"Missing required field: {field}")
            if field in document and not isinstance(document[field], config['type']):
                raise TypeError(f"Invalid type for {field}. Expected {config['type']}")        
    