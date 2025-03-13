# iron_fly_strategy.py
from datetime import datetime
from deltaneutral import DeltaNeutralStrategy
from mongodb_connection import MongoDBConnection
from nse_interactions import NSEInteractions

class IronFlyStrategy:
    def __init__(self, symbol, lot_size, breach_level, user, api_key, mongo_endpoints):
        self.nse_interactions = NSEInteractions()
            
        
        # Rest of existing initialization code
        self.symbol = symbol
        self.lot_size = lot_size
        self.breach_level = breach_level
        self.user = user
        
        self.api_key = api_key
        self.mongo_endpoints = mongo_endpoints
        self.mongo_connection = MongoDBConnection(api_key, mongo_endpoints)
        self.nse_interactions = NSEInteractions()
    
    def get_atm_strike_and_prices(self):
        option_chain = self.nse_interactions.fetch_option_chain(self.symbol)
        if not option_chain:
            return None, None, None, None

        underlying_price = option_chain["records"]["underlyingValue"]
        expiry_dates = option_chain["records"]["expiryDates"]
        nearest_expiry = expiry_dates[0]  # Use the nearest expiry date

        # Find the ATM strike price
        strike_prices = [record["strikePrice"] for record in option_chain["records"]["data"]]
        atm_strike = min(strike_prices, key=lambda x: abs(x - underlying_price))
        
        # Fetch last prices of call and put options for the ATM strike
        call_price = None
        put_price = None
        for record in option_chain["records"]["data"]:
            if record["strikePrice"] == atm_strike:
                if "CE" in record:
                    call_price = record["CE"]["lastPrice"]
                if "PE" in record:
                    put_price = record["PE"]["lastPrice"]
                break

        return atm_strike, call_price, put_price, nearest_expiry

    def calculate_max_profit_loss(self, call_sell_price, put_sell_price, call_buy_price, put_buy_price, strike_diff):
        net_credit = (call_sell_price + put_sell_price) - (call_buy_price + put_buy_price)
        max_profit = net_credit * self.lot_size
        max_loss = strike_diff - net_credit * self.lot_size
        return max_profit, max_loss

    def get_strategy_details(self):
        try:
            # Fetch ATM strike and option prices
            atm_strike, call_sell_price, put_sell_price, expiry_date = self.get_atm_strike_and_prices()
            if not atm_strike:
                return {"error": "Failed to fetch ATM strike price or option prices."}

            # Fetch OTM call and put prices
            ce_buy_price, pe_buy_price = self.get_otm_prices(atm_strike, expiry_date)
            if not ce_buy_price or not pe_buy_price:
                return {"error": "Failed to fetch OTM call or put prices."}

            # Calculate max profit and max loss
            strike_diff = 500  # Difference between strikes
            max_profit, max_loss = self.calculate_max_profit_loss(call_sell_price, put_sell_price, ce_buy_price, pe_buy_price, strike_diff)

            # Define the legs of the Iron Fly strategy
            legs = [
                {"type": "sell", "option_type": "call", "strike": atm_strike, "price": call_sell_price},
                {"type": "buy", "option_type": "call", "strike": atm_strike + 500, "price": ce_buy_price},
                {"type": "sell", "option_type": "put", "strike": atm_strike, "price": put_sell_price},
                {"type": "buy", "option_type": "put", "strike": atm_strike - 500, "price": pe_buy_price}
            ]

            # Return strategy details
            return {
                "strategy": "Iron Fly",
                "symbol": self.symbol,
                "atm_strike": atm_strike,
                "expiry_date": expiry_date,
                "max_profit": max_profit,
                "max_loss": max_loss,
                "legs": legs
            }
        except Exception as e:
            print(f"Error fetching strategy details: {e}")
            return {"error": "Failed to fetch strategy details."}

    def get_otm_prices(self, atm_strike, expiry_date):
        option_chain = self.nse_interactions.fetch_option_chain(self.symbol)
        if not option_chain:
            return None, None

        # Define OTM strikes
        otm_call_strike = atm_strike + 500  # Example: 500 points above ATM
        otm_put_strike = atm_strike - 500   # Example: 500 points below ATM

        # Fetch last prices of OTM call and put options
        ce_buy_price = None
        pe_buy_price = None

        for record in option_chain["records"]["data"]:
            if record["strikePrice"] == otm_call_strike and record["expiryDate"] == expiry_date:
                if "CE" in record:
                    ce_buy_price = record["CE"]["lastPrice"]
            if record["strikePrice"] == otm_put_strike and record["expiryDate"] == expiry_date:
                if "PE" in record:
                    pe_buy_price = record["PE"]["lastPrice"]
                if ce_buy_price and pe_buy_price:
                    break

        return ce_buy_price, pe_buy_price

    def execute_strategy(self):
        # Fetch ATM strike and option prices
        atm_strike, call_sell_price, put_sell_price, expiry_date = self.get_atm_strike_and_prices()
        if not atm_strike:
            print("Error fetching ATM strike price.")
            return

        print(f"ATM Strike Price: {atm_strike}, Call Sell Price: {call_sell_price}, Put Sell Price: {put_sell_price}, Expiry Date: {expiry_date}")

        # Create the Iron Fly strategy
        legs = self.create_iron_fly(self.symbol, atm_strike, expiry_date, call_sell_price, put_sell_price)
        if not legs:
            print("Failed to create Iron Fly strategy.")
            return
        return legs
        print("Iron Fly strategy created with legs:", legs)

    def create_iron_fly(self, symbol, strike_price, expiry_date, call_sell_price, put_sell_price):
        # Fetch OTM call and put premiums
        ce_buy_price, pe_buy_price = self.get_otm_prices(strike_price, expiry_date)
        if not ce_buy_price or not pe_buy_price:
            print("Error fetching OTM call or put premiums.")
            return None

        # Define the legs of the Iron Fly strategy
        legs = [
            {"type": "sell", "option_type": "call", "strike": strike_price, "expiry": expiry_date, "price": call_sell_price},
            {"type": "buy", "option_type": "call", "strike": strike_price + 500, "expiry": expiry_date, "price": ce_buy_price},
            {"type": "sell", "option_type": "put", "strike": strike_price, "expiry": expiry_date, "price": put_sell_price},
            {"type": "buy", "option_type": "put", "strike": strike_price - 500, "expiry": expiry_date, "price": pe_buy_price}
        ]

        # Calculate max profit and max loss
        strike_diff = 500  # Difference between strikes
        max_profit, max_loss = self.calculate_max_profit_loss(call_sell_price, put_sell_price, ce_buy_price, pe_buy_price, strike_diff)
        print(f"Max Profit: {max_profit}, Max Loss: {max_loss}")

        # Store the legs in MongoDB
        payload = json.dumps({
            "collection": "iron_fly",
            "database": "myFirstDatabase",
            "dataSource": "Cluster0",
            "document": {
                "symbol": symbol,
                "strategy": "iron_fly",
                "legs": legs,
                "max_profit": max_profit,
                "max_loss": max_loss,
                "status": "active",
                "created_at": datetime.now().strftime("%d-%m-%Y %H:%M:%S")
            }
        })
        response = requests.post(self.mongo_endpoints["insert"], headers=self.get_headers(), data=payload)
        if response.status_code == 201:
            print("Iron Fly strategy created and stored in MongoDB.")
        else:
            print("Error storing strategy in MongoDB:", response.text)

        return legs