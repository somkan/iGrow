# app.py
from flask import Flask, jsonify, request, render_template, redirect, url_for, session
from flask_cors import CORS
from expiry_strategy import ExpiryStrategy
from iron_fly_strategy import IronFlyStrategy
from screener_module import Screener
import os
import json
import requests
import subprocess
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import atexit

app = Flask(__name__)
CORS(app)
app.secret_key = 'your_secret_key'  # Required for session management


# MongoDB API key
try:
    api = json.loads(open('api_key.json', 'r').read())
    api_key = api["API_KEY"]
except Exception as e:
    api_key = os.getenv("API_KEY")

# MongoDB endpoints
mongo_endpoints = {
    "find": "https://ap-south-1.aws.data.mongodb-api.com/app/data-kpqgeul/endpoint/data/v1/action/findOne",
    "find_all": "https://ap-south-1.aws.data.mongodb-api.com/app/data-kpqgeul/endpoint/data/v1/action/find",
    "insert": "https://ap-south-1.aws.data.mongodb-api.com/app/data-kpqgeul/endpoint/data/v1/action/insertOne",
     "insert_all": "https://ap-south-1.aws.data.mongodb-api.com/app/data-kpqgeul/endpoint/data/v1/action/insertMany",
    "update": "https://ap-south-1.aws.data.mongodb-api.com/app/data-kpqgeul/endpoint/data/v1/action/updateOne",
    "delete_many": "https://ap-south-1.aws.data.mongodb-api.com/app/data-kpqgeul/endpoint/data/v1/action/deleteMany"  # Add this line
}
# In app.py initialization
try:
    expiry_strategy = ExpiryStrategy(
        symbol="NIFTY",
        user="XS06414",
        api_key=api_key,
        mongo_endpoints=mongo_endpoints
    )
    # Check if Fyers was initialized
    if not expiry_strategy.fyers_interactions:
        raise RuntimeError("Fyers API initialization failed")
except Exception as e:
    print(f'Expiry Strategy initialize error: {e}')
    expiry_strategy = None

# Initialize IronFlyStrategy
iron_fly_strategy = IronFlyStrategy(
    symbol="NIFTY",
    lot_size=75,
    breach_level=100,
    user="XS06414",
    api_key=api_key,
    mongo_endpoints=mongo_endpoints
)


# Initialize the screener
screener = Screener(api_key, mongo_endpoints)

# Login route
@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        # Authenticate user with MongoDB
        payload = json.dumps({
            "collection": "Auth_Data",
            "database": "myFirstDatabase",
            "dataSource": "Cluster0",
            "filter": {"userid": username, "pin": password}
        })
        response = requests.post(mongo_endpoints["find"], headers={"api-key": api_key, "Content-Type": "application/json"}, data=payload)
        user_data = response.json()

        if user_data and 'document' in user_data:
            session['user'] = username  # Store user in session
            try:
                subprocess.run(['python', '830.py'], check=True)
                print(f'Mass Login successful - 830.py Executed')
            except subprocess.CalledProcessError as e:
                print(f'Error Running 830.py: {e}')
            return redirect(url_for('dashboard'))
        else:
            return render_template('stockboard.html', error="Invalid credentials")

    return render_template('stockboard.html')

# Dashboard route
@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect(url_for('login'))

    return render_template('dashboard.html')

# Admin Dashboard route
@app.route('/admin_dashboard')
def admin_dashboard():
    return render_template('admin_dash.html')

# Logout route
@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

@app.route('/get-signals', methods=['GET'])
def get_signals():
    user = session.get('user')  # Get user from session
    symbol = request.args.get('symbol')
    signals = mongo_connection.get_pending_signals(user, symbol)
    return jsonify(signals)
    
# Function to reset the processed_buy_signals set
def reset_processed_buy_signals():
    global processed_buy_signals
    processed_buy_signals = set()
    print("Processed buy signals have been reset.")


@app.route('/reset-signals', methods=['POST'])  # Updated endpoint
def reset_signals():
    auto_processing['processed_signals'].clear()
    print("All processed signals reset")
    return jsonify({"message": "Reset all processed signals"})

# Remove old reset-buy-signals endpoint
# Strategy Details route
@app.route('/strategy-details', methods=['GET'])
def get_strategy_details():
    strategy_name = request.args.get('strategy')
    if strategy_name == 'iron-fly':
        try:
            strategy_details = iron_fly_strategy.get_strategy_details()
            return jsonify(strategy_details)
        except Exception as e:
            print(f"Error fetching strategy details: {e}")
            return jsonify({"error": "Failed to fetch strategy details."}), 500

# Execute Strategy route
@app.route('/execute-strategy', methods=['POST'])
def execute_strategy():
    data = request.json
    strategy_name = data.get('strategy')
    if strategy_name == 'iron-fly':
        try:
            iron_fly_strategy.execute_strategy()
            return jsonify({"status": "success", "message": "Iron Fly strategy executed successfully."})
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500
    else:
        return jsonify({"error": "Strategy not found."}), 404


@app.route('/screen', methods=['GET'])
def screen():
    symbols = request.args.get('symbols', 'NIFTY,BANKNIFTY').split(',')
    alerts = []
    for symbol in symbols:
        opportunities = screener.screen_opportunities(symbol)
        alerts.extend(opportunities)
    if alerts:
        screener.save_alerts(alerts)
    return jsonify(alerts)
    
@app.route('/update-alert', methods=['POST'])
def update_alert():
    data = request.json
    alert_id = data.get('alert_id')
    status = data.get('status')
    profit = data.get('profit')
    trade_outcome = data.get('trade_outcome')

    if not alert_id or not status:
        return jsonify({"error": "Missing alert_id or status"}), 400

    result = screener.update_alert_status(alert_id, status, profit, trade_outcome)
    return jsonify(result)
    
@app.route('/alerts', methods=['GET'])
def get_alerts():
    symbol = request.args.get('symbol')
    alerts = screener.get_alerts(symbol)
  #  print(alerts)
    return jsonify(alerts)
    
#expiry_strategy = ExpiryStrategy("NIFTY", "XS06414", api_key, mongo_endpoints)
#expiry_strategy = ExpiryStrategy("BANKNIFTY", "XS06414", api_key, mongo_endpoints)

@app.route('/auto-processing-status', methods=['GET'])
def get_processing_status():
    return jsonify({"enabled": auto_processing_enabled})

# Global state for signal processing
auto_processing = {
    'enabled': False,  # Master toggle
    'processed_signals': set()  # Track both buy/sell signals
}

@app.route('/toggle-auto-processing', methods=['POST'])
def toggle_auto_processing():
    auto_processing['enabled'] = not auto_processing['enabled']
    return jsonify({
        "status": "success",
        "message": f"Auto processing {'ENABLED' if auto_processing['enabled'] else 'DISABLED'}",
        "enabled": auto_processing['enabled']
    })

# Add at the top with other imports
from datetime import datetime
import traceback

# Global auto-processing configuration
auto_processing = {
    'enabled': False,
    'processed_signals': {},
    'lot_sizes': {'NIFTY': 75, 'BANKNIFTY': 30},
    'cooldown': 300  # 5 minutes in seconds
}

@app.route('/refresh-token', methods=['POST'])
def refresh_token():
    try:
        if not expiry_strategy:
            return jsonify({"error": "Strategy not initialized"}), 500
            
        new_token = expiry_strategy.refresh_auth_token()
        return jsonify({"status": "success", "new_token": new_token})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
@app.route('/trading-data', methods=['GET'])
def get_trading_data():
    if not expiry_strategy or not expiry_strategy.fyers_interactions:
        return jsonify({"error": "Strategy not properly initialized"}), 500
    
    try:
        symbols = request.args.get('symbol', 'NIFTY').split(',')
        trading_data = expiry_strategy.get_trading_data(symbols)
        print(f"MongoDB endpoints: {mongo_endpoints}")
        print(f"API key present: {bool(api_key)}")
        
        symbols = request.args.get('symbol', 'NIFTY').split(',')
        print(f"Processing symbols: {symbols}")
        
        trading_data = expiry_strategy.get_trading_data(symbols)
        print(f"Raw trading data: {json.dumps(trading_data, indent=2)}")

        if auto_processing['enabled']:
            current_time = datetime.now()
            
            for entry in trading_data:
                try:
                    if 'error' in entry or 'valuation' not in entry:
                        continue

                    # Ensure all required fields exist
                    symbol = entry.get('symbol')
                    if not symbol:
                        raise KeyError("Missing 'symbol' in trading data entry")
                        
                    valuation = entry.get('valuation', {})
                    generated_symbol = entry.get('generated_symbol', '')
                    
                    if not generated_symbol or valuation.get('signal') not in ('BUY', 'SELL'):
                        continue

                    # Trade existence check
                          # Improved trade existence check
                    trade_exists = expiry_strategy.check_trade_exists(
                    symbol, 
                    generated_symbol,
                    current_time.date()
                     )
                    if trade_exists:
                        print(f"Trade exists: {symbol}-{generated_symbol}")
                        entry['trade_status'] = 'exists'
                        continue

                    # Signal processing logic
                    prev_state = auto_processing['processed_signals'].get(symbol, {})
                    current_signal = valuation.get('signal')
                    
                    # Validate signal transition
                    if prev_state.get('signal') == current_signal:
                        continue
                    
                    # Execute trade
                    quantity = auto_processing['lot_sizes'].get(symbol, 75)
                    side = -1 if current_signal == 'SELL' else 1
                    
                    # Get strike price safely
                    try:
                        strike_part = generated_symbol.split(symbol)[-1][:-2]
                        strike = int(''.join(filter(str.isdigit, strike_part)))
                    except (IndexError, ValueError) as e:
                        print(f"Strike parsing failed: {str(e)}")
                        strike = 0

                    # Record trade before execution attempt
                    trade_record = {
                        'symbol': symbol,
                        'generated_symbol': generated_symbol,
                        'signal': current_signal,
                        'strike': strike,
                        'quantity': quantity,
                        'signal_price': entry['option'].get('current'),
                        'status': 'pending'
                    }
                    insert_result = expiry_strategy.store_trade(trade_record)
                    trade_id = insert_result.get('insertedId')

                    # Execute order
                    order_response = expiry_strategy.fyers_interactions.place_order(
                        symbol=generated_symbol,
                        quantity=quantity,
                        side=side,
                        strike=strike
                    )

                    # Update trade status
                    if order_response.get('code') == 200:
                        expiry_strategy.update_trade_status(
                            trade_id,
                            "executed",
                            execution_price=order_response.get('averagePrice')
                        )
                        entry.update({
                            'trade_status': 'executed',
                            'execution_price': order_response.get('averagePrice')
                        })
                    else:
                        raise Exception(f"Order failed: {order_response.get('message')}")

                except Exception as e:
                    print(f"Trade processing failed for {symbol if 'symbol' in locals() else 'unknown'}: {str(e)}")
                    print(traceback.format_exc())
                    if 'trade_id' in locals():
                        print(f"Final trade status: {entry.get('trade_status')}")
                        print(f"Execution price: {entry.get('execution_price')}")
                        expiry_strategy.update_trade_status(
                            trade_id,
                            "failed",
                            error=str(e)
                        )
                    entry['trade_status'] = 'failed'

        return jsonify(trading_data)
        
    except Exception as e:
        print(f"Critical error: {traceback.format_exc()}")
        return jsonify({"error": "Internal server error"}), 500
        
@app.route('/trade-history')
def get_trade_history():
    user = session.get('user')
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
        
    try:
        trades = expiry_strategy.mongo_connection.find_all(
            "trade_history",
            "myFirstDatabase",
            {"user": user},
            sort={"signal_timestamp": -1},
            limit=50
        )
        return jsonify(trades.get('documents', []))
    except Exception as e:
        return jsonify({"error": str(e)}), 500
# Example Flask routes
@app.route('/get-strikes')
def get_strikes():
    symbol = request.args.get('symbol')
    return jsonify(screener.get_available_strikes(symbol))

@app.route('/get-option-details')
def get_option_details():
    symbol = request.args.get('symbol')
    strike = request.args.get('strike')
    return jsonify(screener.get_option_details(symbol, strike))
    
@app.route('/get-iv-crush-opportunities')
def get_iv_crush_opportunities():
    symbol = request.args.get('symbol')
    try:
        # Fetch option chain data
        option_chain = screener.fetch_option_chain(symbol)
        if not option_chain:
            return jsonify({"error": "Failed to fetch option chain"})

        # Identify IV Crush opportunities
        opportunities = []
        for record in option_chain['records']['data']:
            ce_iv = record['CE'].get('impliedVolatility', 0)
            pe_iv = record['PE'].get('impliedVolatility', 0)
            iv_discrepancy = abs(ce_iv - pe_iv)

            # Check for significant IV discrepancy
            if iv_discrepancy > 5:  # Threshold for IV discrepancy
                opportunities.append({
                    "strike": record['strikePrice'],
                    "iv_discrepancy": iv_discrepancy,
                    "event": "Earnings",  # Placeholder for event detection
                    "expiry": record['expiryDate'],
                    "recommendation": "Sell options to capitalize on IV crush"
                })

        return jsonify(opportunities)

    except Exception as e:
        return jsonify({"error": str(e)})
        
@app.route('/option-details')
def option_details():
    return render_template('option-details.html')

@app.route('/recomend')
def rexomend():
    return render_template('recomend.html')
# Add these utility endpoints
@app.route('/api-status')
def api_status():
    return jsonify({
        "enhanced-signals": check_endpoint('/enhanced-signals/NIFTY'),
        "volume-profile": check_endpoint('/volume-profile/NIFTY'),
        "oi-levels": check_endpoint('/oi-levels/NIFTY'),
        "dynamic-bands": check_endpoint('/dynamic-bands/NIFTY')
    })

def check_endpoint(endpoint):
    try:
        response = requests.get(f'http://localhost:5000{endpoint}')
        return response.status_code == 200 and bool(response.json())
    except:
        return False

# Modify existing endpoints to ensure consistent structure
@app.route('/enhanced-signals/<symbol>')
def enhanced_signals(symbol):
    try:
        signals = screener.screen_opportunities(symbol)
        return jsonify({
            "status": "success",
            "symbol": symbol,
            "signals": signals if signals else [],
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e),
            "signals": []
        }), 500


# Example for /volume-profile
@app.route('/volume-profile/<symbol>')
def volume_profile(symbol):
    try:
        option_chain = screener.fetch_option_chain(symbol)
        if not option_chain:
            return jsonify({"error": "No option chain data"}), 404
            
        return jsonify({
            "volume_profile": option_chain['records']['volumeData'],
            "symbol": symbol
        })
        
    except KeyError:
        return jsonify({"error": "Volume data not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500
# In app.py
@app.route('/dynamic-bands/<symbol>')
def dynamic_bands(symbol):
    try:
        # Get fresh option chain data directly
        option_chain = screener.fetch_option_chain(symbol)
        
        # Safely extract spot price from chain
        spot_price = None
        if option_chain and 'records' in option_chain:
            # First try PE data
            if option_chain['records']['data'] and 'PE' in option_chain['records']['data'][0]:
                spot_price = option_chain['records']['data'][0]['PE'].get('underlyingValue')
            
            # Fallback to direct value
            if not spot_price:
                spot_price = option_chain['records'].get('underlyingValue', 0)

        # Final fallback to hardcoded value
        spot_price = float(spot_price) if spot_price else 22460.3  # Default from your logs
        
        return jsonify({
            "upper": round(spot_price * 1.02, 2),
            "lower": round(spot_price * 0.98, 2),
            "symbol": symbol,
            "source": "direct_api_fetch"
        })
        
    except Exception as e:
        print(f"Dynamic Bands Fallback: Using cached price. Error: {str(e)}")
        return jsonify({
            "upper": 22460.3 * 1.02,
            "lower": 22460.3 * 0.98,
            "symbol": symbol,
            "source": "cached_value",
            "warning": "Live data unavailable"
        })
@app.route('/oi-levels/<symbol>')
def oi_levels(symbol):
    try:
        # Get Open Interest data
        oi_data = screener.fetch_option_chain(symbol).get('records', {})
        return jsonify({
            "CE_OI": oi_data.get('CE', {}).get('openInterest', 0),
            "PE_OI": oi_data.get('PE', {}).get('openInterest', 0)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/verify-db', methods=['GET'])
def verify_db_connection():
    try:
        test_doc = {
            "test": datetime.now().isoformat(),
            "status": "connection_test"
        }
        
        # Test insert
        insert_result = expiry_strategy.mongo_connection.insert_one(
            "connection_tests",
            "myFirstDatabase",
            test_doc
        )
        
        # Test query
        find_result = requests.post(
            mongo_endpoints["find"],
            headers={"api-key": api_key, "Content-Type": "application/json"},
            json={
                "collection": "connection_tests",
                "database": "myFirstDatabase",
                "dataSource": "Cluster0",
                "filter": {"_id": {"$oid": insert_result.get('insertedId')}}
            }
        ).json()

        return jsonify({
            "insert_result": insert_result,
            "find_result": find_result
        })
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500
# Keep other endpoints same
# Scheduler setup
scheduler = BackgroundScheduler()
scheduler.add_job(
    lambda: requests.get('http://localhost:5001/trading-data?symbol=NIFTY&place_order=true'),
    CronTrigger(day_of_week='mon-fri', hour=9, minute=18),
    id='job_one'
)
scheduler.add_job(
    lambda: requests.get('http://localhost:5001/trading-data?symbol=BANKNIFTY&place_order=true'),
    CronTrigger(day_of_week='mon-fri', hour=9, minute=18),
    id='job_two'
)
# Modified scheduler jobs
scheduler.add_job(
    lambda: requests.get('http://localhost:5001/trading-data?symbol=NIFTY&place_order=true'),
    CronTrigger(day_of_week='mon-fri', hour=9, minute=18),
    id='auto_trading_job'
)
from crontab import CronTab

#cron = CronTab()
# Add to your existing scheduler setup
scheduler.add_job(
    lambda: os.system('sh duckdns_update.sh'),
    'interval',
    minutes=60,
    id='duckdns_update'
)

scheduler.start()
atexit.register(scheduler.shutdown)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)