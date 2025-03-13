# signals.py
from nse_interactions import NSEInteractions  # Import the base class
import math
import time
from datetime import datetime, timedelta
import requests
from bs4 import BeautifulSoup


def telegram(message1,message2):
    bot_token = '1720457948:AAF1VSmBzyhp70b4QGrLGDe23pKRhWP4iKw'  # paste bot_token
    #bot_chatID = '-579138108'  # paste your chatid where you want to send alert(group or channel or personal)
    bot_chatID = '-1001206209234'  # chatid of Telegram group Monitor Signal
    bot_message = str(message1) + str(message2)
    send_text = 'https://api.telegram.org/bot' + bot_token + '/sendMessage?chat_id=' + bot_chatID + '&parse_mode=Markdown&text=' + bot_message
    response = requests.get(send_text)
    return response.json()

class DeltaNeutralTrader(NSEInteractions):  # Inherit from NSEInteractions
    def __init__(self, symbol="NIFTY"):
        super().__init__()  # Initialize parent class
        self.symbol = symbol
        print(self.symbol)
        self.lot_size = self._get_lot_size()
        self.risk_free_rate = 6.5
        self.expiry_date = self._get_nearest_expiry()
        self.spot_price = 0
        self.option_chain = None
        self._refresh_data()

    def _get_nearest_expiry(self):
        """Get expiry date using parent class methods"""
        option_chain = self.fetch_option_chain(self.symbol)
        if option_chain:
            return self.get_expiry_dates(option_chain)[0]
        return super()._fallback_expiry()

    def _refresh_data(self):
        """Refresh data with empty chain check."""
        try:
            option_chain = self.fetch_option_chain(self.symbol)
            if not option_chain or 'records' not in option_chain:
                raise ValueError("Invalid option chain structure")

            self.spot_price = self.get_underlying_price(option_chain)
            self.expiry_date = self.get_expiry_dates(option_chain)[0]

            filtered_chain = [
                entry for entry in option_chain['records']['data']
                if entry['expiryDate'] == self.expiry_date
                   and 'CE' in entry and 'PE' in entry
            ]

            if not filtered_chain:
                print("No valid strikes found for expiry")
                self.option_chain = []
                return

            self.option_chain = filtered_chain
            self._calculate_iv_percentiles()
            print("Spot price:", self.spot_price)
            print("Expiry date:", self.expiry_date)
        except Exception as e:
            print(f"Data refresh failed: {str(e)}")
            self.option_chain = []
            self.spot_price = 0

    def _fetch_risk_free_rate(self):
        """Fetch the latest 10-year bond yield from Investing.com."""
        url = "https://in.investing.com/rates-bonds/india-10-year-bond-yield-historical-data"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }

        try:
            response = requests.get(url, headers=headers)
            soup = BeautifulSoup(response.text, 'html.parser')

            # Locate the latest yield value
            yield_value = soup.find('span', {'class': 'text-2xl'}).text.strip()
            self.risk_free_rate = float(yield_value)
            print(f"Fetched risk-free rate: {self.risk_free_rate}%")
        except Exception as e:
            print(f"Failed to fetch risk-free rate: {e}")
            self.risk_free_rate = 6.5  # Fallback to default rate

    def _get_lot_size(self):
        """Fetch contract lot size from NSE"""
        try:
            url = f"{self.base_url}/api/contracts-indices?symbol={self.symbol}"
            response = self.session.get(url, timeout=10)
            return response.json()['data'][0]['marketLot']
        except:
            # Default lot sizes for common symbols
            lot_sizes = {
                'NIFTY': 75,
                'BANKNIFTY': 30,
                'FINNIFTY': 40,
                'MIDCPNIFTY': 75,
            }
            return lot_sizes.get(self.symbol, 30)  # Default to 30 for unknown symbols

    def _process_option(self, option):
        """Process individual option data"""
        if not option:
            return None

        return {
            'price': option['lastPrice'],
            'iv': option['impliedVolatility'],
            'oi': option['openInterest'],
            'oi_change_pct': option['pChangeinOpenInterest'],
            'volume': option['totalTradedVolume']
        }

    def _calculate_iv_percentiles(self):
        """Calculate IV percentiles with null checks"""
        call_ivs = []
        put_ivs = []

        for strike in self.option_chain:
            ce = strike.get('CE', {})
            pe = strike.get('PE', {})
            # Check for CE IV
            if ce and 'impliedVolatility' in ce:
                call_ivs.append(ce['impliedVolatility'])
            # Check for PE IV
            if pe and 'impliedVolatility' in pe:
                put_ivs.append(pe['impliedVolatility'])

        # Handle empty IV lists
        self.call_iv_90 = sorted(call_ivs)[int(len(call_ivs) * 0.9)] if call_ivs else 30  # Fallback IV
        self.put_iv_10 = sorted(put_ivs)[int(len(put_ivs) * 0.1)] if put_ivs else 30

    def calculate_delta(self, option_type, moneyness, days_to_expiry):
        """Dynamic delta calculation"""
        if option_type == 'CE':
            return 0.5 / (1 + math.exp(-moneyness * math.sqrt(days_to_expiry / 365)))
        else:
            return -0.5 / (1 + math.exp(-moneyness * math.sqrt(days_to_expiry / 365)))

    def generate_signals(self):
        """Generate trading signals with composite scoring."""
        if not self.option_chain:
            print("No option chain data available.")
            return []

        signals = []
        for strike in self.option_chain:
            if 'strikePrice' not in strike or not strike.get('CE') or not strike.get('PE'):
                print("Skipping invalid strike:", strike)
                continue

            # Calculate moneyness
            moneyness = (self.spot_price - strike['strikePrice']) / strike['strikePrice']

            # Calculate deltas
            days_to_exp = (datetime.strptime(self.expiry_date, "%d-%b-%Y") - datetime.now()).days +1
            delta_ce = self.calculate_delta('CE', moneyness, days_to_exp)
            delta_pe = self.calculate_delta('PE', moneyness, days_to_exp)

            # Composite scoring for both CE and PE
            score_ce = self._calculate_composite_score(strike, delta_ce, option_type='CE')
            score_pe = self._calculate_composite_score(strike, delta_pe, option_type='PE')

            # Determine actions for CE and PE
            action_ce = self._determine_action(score_ce, strike, option_type='CE')
            action_pe = self._determine_action(score_pe, strike, option_type='PE')

            # Generate valuation message based on composite score
            def get_valuation_message(score):
                if score >= 0.7:
                    return "Overvalued (Strong Signal)"
                elif score <= 0.3:
                    return "Undervalued (Strong Signal)"
                else:
                    return "Fairly Priced (Neutral Signal)"

            # Create signals for CE and PE
            signal_ce = {
                'symbol': self.symbol,
                'strike': strike['strikePrice'],
                'option_type': 'CE',  # Add option type
                'action': action_ce,
                'score': round(score_ce, 2),
                'valuation_message': get_valuation_message(score_ce),  # Add valuation message
                'details': {
                    'delta': round(delta_ce, 3),
                    'iv_discrepancy': self._get_iv_discrepancy(strike, option_type='CE'),
                    'oi_strength': self._get_oi_strength(strike, option_type='CE'),
                    'parity_mispricing': self._get_parity_mispricing(strike, option_type='CE')
                }
            }

            signal_pe = {
                'symbol': self.symbol,
                'strike': strike['strikePrice'],
                'option_type': 'PE',  # Add option type
                'action': action_pe,
                'score': round(score_pe, 2),
                'valuation_message': get_valuation_message(score_pe),  # Add valuation message
                'details': {
                    'delta': round(delta_pe, 3),
                    'iv_discrepancy': self._get_iv_discrepancy(strike, option_type='PE'),
                    'oi_strength': self._get_oi_strength(strike, option_type='PE'),
                    'parity_mispricing': self._get_parity_mispricing(strike, option_type='PE')
                }
            }

            signals.append(signal_ce)
            signals.append(signal_pe)

       # print("Generated signals:", signals)
        return signals

    def _calculate_composite_score(self, strike, delta, option_type):
        """Calculate normalized composite score for a specific option type."""
        iv_score = 0.4 * self._get_iv_discrepancy(strike, option_type)
        oi_score = 0.3 * self._get_oi_strength(strike, option_type)
        parity_score = 0.2 * self._get_parity_mispricing(strike, option_type)
        delta_score = 0.1 * (1 - abs(delta))

        return iv_score + oi_score + parity_score + delta_score

    def _get_iv_discrepancy(self, strike, option_type):
        """Calculate IV discrepancy score for a specific option type."""
        if option_type == 'CE':
            return 0.7 if strike['CE']['impliedVolatility'] > self.call_iv_90 else 0
        elif option_type == 'PE':
            return 0.3 if strike['PE']['impliedVolatility'] < self.put_iv_10 else 0
        return 0

    def _get_oi_strength(self, strike, option_type):
        """Calculate Open Interest strength for a specific option type."""
        if option_type == 'CE':
            return strike['CE']['pchangeinOpenInterest'] / 100
        elif option_type == 'PE':
            return strike['PE']['pchangeinOpenInterest'] / 100
        return 0

    def _get_parity_mispricing(self, strike, option_type):
        """Calculate put-call parity mispricing for a specific option type."""
        strike_price = strike['strikePrice']
        t = (datetime.strptime(self.expiry_date, "%d-%b-%Y") - datetime.now()).days / 365
        df = math.exp(-self.risk_free_rate / 100 * t)

        if option_type == 'CE':
            theoretical_put = strike['CE']['lastPrice'] - self.spot_price + strike_price * df
            actual_put = strike['PE']['lastPrice']
        elif option_type == 'PE':
            theoretical_call = strike['PE']['lastPrice'] + self.spot_price - strike_price * df
            actual_call = strike['CE']['lastPrice']

        return (actual_put - theoretical_put) / theoretical_put if option_type == 'CE' else (
                                                                                                        actual_call - theoretical_call) / theoretical_call

    def _determine_action(self, score, strike, option_type):
        """Determine trading action based on score and option type."""
        if score >= 0.7:
            return 'BUY' if strike['strikePrice'] < self.spot_price else 'SELL'
        elif score <= 0.3:
            return 'SELL' if strike['strikePrice'] < self.spot_price else 'BUY'
        return 'HOLD'



# Example Usage
if __name__ == "__main__":
    # Initialize with your Telegram credentials
    trader = DeltaNeutralTrader(
        symbol='NIFTY' 
    )

    # Generate and display signals
    signals = trader.generate_signals()
    #print(signals)
    for sig in signals[:]:  # Show top 5 signals
        print(f"\n{sig['action']} at {sig['strike']}")
        print(f"Score: {sig['score']}")
        print(f"Details: {sig['details']}")
        #telegram(f'\n{sig['action']} {sig['symbol']} {sig['strike']} {sig['option_type']} ', f" Score: {sig['score']}")