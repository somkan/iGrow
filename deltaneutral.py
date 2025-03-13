from datetime import datetime, timedelta
#from papertrade import PaperTrade
import math

class DeltaNeutralStrategy:

    def __init__(self, underlying_symbol='NIFTY', options_chain=None):
        self.underlying_symbol = underlying_symbol
        self.options_chain = options_chain
        self.positions = []
        self.backtest_results = None
        self.risk_parameters = {
            'max_loss_per_trade': 50,  # Max allowed loss per trade
            'max_delta_deviation': 0.2,  # Max allowed delta deviation from neutral
            'position_size': 75  # Default position size
        }

    def calculate_delta(self, option_type, moneyness, days_to_expiry):
        """Simple delta approximation based on moneyness and time"""
        if option_type == 'CE':
            return min(0.5 + (moneyness * 0.1) + (1 / (days_to_expiry + 1)), 0.99)
        else:
            return max(-0.5 + (moneyness * 0.1) - (1 / (days_to_expiry + 1)), -0.99)

    def find_neutral_combination(self, spot_price):
        """Find the best Delta Neutral combination"""
        if not self.options_chain:
            return None

        candidates = []

        for expiry in self.options_chain['records']['data']:
            moneyness = (spot_price - expiry['strikePrice']) / spot_price
            days_to_expiry = (datetime.strptime(expiry['expiryDate'], "%d-%b-%Y") - datetime.now()).days

            # Call option
            if 'CE' in expiry:
                call_delta = self.calculate_delta('CE', moneyness, days_to_expiry)
                call_price = expiry['CE']['lastPrice']
            else:
                call_delta = 0
                call_price = None

            # Put option
            if 'PE' in expiry:
                put_delta = self.calculate_delta('PE', moneyness, days_to_expiry)
                put_price = expiry['PE']['lastPrice']
            else:
                put_delta = 0
                put_price = None

            if call_price and put_price:
                candidates.append({
                    'expiry': expiry['expiryDate'],
                    'strike': expiry['strikePrice'],
                    'call_delta': call_delta,
                    'put_delta': put_delta,
                    'call_price': call_price,
                    'put_price': put_price,
                    'net_delta': call_delta + put_delta,
                    'premium_collected': call_price + put_price
                })

        # Filter candidates based on risk parameters
        filtered_candidates = [
            c for c in candidates
            if abs(c['net_delta']) <= self.risk_parameters['max_delta_deviation']
        ]

        # Sort by premium collected (descending)
        filtered_candidates.sort(key=lambda x: x['premium_collected'], reverse=True)

        return filtered_candidates[0] if filtered_candidates else None

    def open_position(self, spot_price, combination):
        """Open a Delta Neutral position"""
        if not combination:
            return False

        position = {
            'entry_date': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'entry_price': spot_price,
            'strike': combination['strike'],
            'call_price': combination['call_price'],
            'put_price': combination['put_price'],
            'net_delta': combination['net_delta'],
            'premium_collected': combination['premium_collected'],
            'exit_date': None,
            'exit_price': None,
            'pnl': 0
        }
        self.positions.append(position)
        return True

    def monitor_positions(self, spot_price):
        """Monitor and adjust open positions"""
        for position in self.positions:
            if not position['exit_date']:
                # Calculate current PnL
                position['pnl'] = (spot_price - position['entry_price']) * self.risk_parameters['position_size']

                # Check for exit conditions
                if position['pnl'] <= -self.risk_parameters['max_loss_per_trade']:
                    position['exit_date'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    position['exit_price'] = spot_price

    def get_open_positions(self):
        """Get all open positions"""
        return [p for p in self.positions if not p['exit_date']]

    def get_closed_positions(self):
        """Get all closed positions"""
        return [p for p in self.positions if p['exit_date']]

    def backtest(self, historical_data):
        """Backtest the strategy"""
        results = []
        for i in range(1, len(historical_data)):
            current = historical_data[i]
            prev = historical_data[i - 1]

            # Open position if conditions are met
            combination = self.find_neutral_combination(float(current['EOD_CLOSE_INDEX_VAL']))
            if combination:
                self.open_position(float(current['EOD_CLOSE_INDEX_VAL']), combination)

            # Monitor and close positions
            self.monitor_positions(float(current['EOD_CLOSE_INDEX_VAL']))

            # Record closed positions
            results.extend(self.get_closed_positions())

        self.backtest_results = results
        return results

    def get_backtest_metrics(self):
        """Calculate backtest performance metrics"""
        if not self.backtest_results:
            return {}

        pnls = [trade['pnl'] for trade in self.backtest_results]
        return {
            'total_trades': len(self.backtest_results),
            'profitable_trades': sum(1 for pnl in pnls if pnl > 0),
            'total_return': sum(pnls),
            'win_rate': sum(1 for pnl in pnls if pnl > 0) / len(pnls) if pnls else 0,
            'max_drawdown': min(pnls) if pnls else 0
        }
    def generate_signals(self, combination, spot_price):
         signals = {
             'underlying_action': 'HOLD',
             'call_action': 'HOLD',
             'put_action': 'HOLD',
             'reasoning': [],
             'iv_discrepancies': []  # Add IV discrepancies to signals
             }

         try:
        # Existing put-call parity logic
           risk_free_rate = 0.01
           days_to_expiry = combination['days_to_expiry']
           time_to_expiry = max(days_to_expiry, 1) / 365

           discount_factor = math.exp(-risk_free_rate * time_to_expiry)
           theoretical_put = combination['call_price'] - spot_price + (combination['strike'] * discount_factor)
           theoretical_call = spot_price - (combination['strike'] * discount_factor) + combination['put_price']

        # Delta-based signals
           if combination['net_delta'] > 0.1:
              signals['underlying_action'] = "SELL"
              signals['reasoning'].append(f"Delta Deviation: {combination['net_delta']:.2f} > 0.1")
           elif combination['net_delta'] < -0.1:
              signals['underlying_action'] = "BUY"
              signals['reasoning'].append(f"Delta Deviation: {combination['net_delta']:.2f} < -0.1")

        # Put-call parity valuation
           call_valuation = (combination['call_price'] - theoretical_call) / theoretical_call
           put_valuation = (combination['put_price'] - theoretical_put) / theoretical_put
        
           if abs(call_valuation) > 0.01:
              signals['call_action'] = "SELL" if call_valuation > 0 else "BUY"
              signals['reasoning'].append(
                f"Call {('Overvalued' if call_valuation > 0 else 'Undervalued')} by {abs(call_valuation)*100:.1f}% vs Parity"
              )

           if abs(put_valuation) > 0.01:
              signals['put_action'] = "SELL" if put_valuation > 0 else "BUY"
              signals['reasoning'].append(
                f"Put {('Overvalued' if put_valuation > 0 else 'Undervalued')} by {abs(put_valuation)*100:.1f}% vs Parity"
              )

        # Add IV discrepancy analysis
           if self.options_chain:
              call_90th, put_10th = self.calculate_iv_percentiles()
              iv_discrepancies = self.find_iv_discrepancies()
              signals['iv_discrepancies'] = iv_discrepancies
            
              for disc in iv_discrepancies:
                if disc['type'] == 'CE' and disc['iv'] > call_90th:
                    signals['reasoning'].append(
                        f"Call IV {disc['iv']}% > 90th percentile ({call_90th}%)"
                    )
                elif disc['type'] == 'PE' and disc['iv'] < put_10th:
                    signals['reasoning'].append(
                        f"Put IV {disc['iv']}% < 10th percentile ({put_10th}%)"
                    )

         except Exception as e:
             signals['reasoning'].append(f"Signal error: {str(e)}")
    
         return signals
      
    def generate_signals1(self, combination, spot_price):
        """Generate buy/sell signals based on Delta Neutral criteria"""
        signals = {
            'underlying_action': 'HOLD',
            'call_action': 'HOLD',
            'put_action': 'HOLD',
            'reasoning': []
               }

        try:
            # Calculate theoretical values using Put-Call Parity
            risk_free_rate = 0.01
            days_to_expiry = combination['days_to_expiry']
            time_to_expiry = max(days_to_expiry, 1) / 365  # Prevent division by zero

            discount_factor = math.exp(-risk_free_rate * time_to_expiry)
            theoretical_put = combination['call_price'] - spot_price + (combination['strike'] * discount_factor)
            theoretical_call = spot_price - (combination['strike'] * discount_factor) + combination['put_price']

            # Underlying Action
            if combination['net_delta'] > 0.1:
                signals['underlying_action'] = "SELL"
                signals['reasoning'].append(f"Net Delta {combination['net_delta']:.2f} > 0.1")
            elif combination['net_delta'] < -0.1:
                signals['underlying_action'] = "BUY"
                signals['reasoning'].append(f"Net Delta {combination['net_delta']:.2f} < -0.1")

            # Call Option Action
            if combination['call_price'] > theoretical_call * 1.05:
                signals['call_action'] = "SELL"
                signals['reasoning'].append(
                    f"Call overpriced by {(combination['call_price'] / theoretical_call - 1) * 100:.1f}%")
            elif combination['call_price'] < theoretical_call * 0.95:
                signals['call_action'] = "BUY"
                signals['reasoning'].append(
                    f"Call underpriced by {(1 - combination['call_price'] / theoretical_call) * 100:.1f}%")

            # Put Option Action
            if combination['put_price'] > theoretical_put * 1.05:
                signals['put_action'] = "SELL"
                signals['reasoning'].append(
                    f"Put overpriced by {(combination['put_price'] / theoretical_put - 1) * 100:.1f}%")
            elif combination['put_price'] < theoretical_put * 0.95:
                signals['put_action'] = "BUY"
                signals['reasoning'].append(
                    f"Put underpriced by {(1 - combination['put_price'] / theoretical_put) * 100:.1f}%")

        except Exception as e:
            signals['reasoning'].append(f"Signal error: {str(e)}")

        return signals
      
    def calculate_iv_percentiles(self):
        """Calculate IV percentiles for calls and puts without using numpy"""
        call_ivs = []
        put_ivs = []

        for expiry in self.options_chain['records']['data']:
            if 'CE' in expiry:
                call_ivs.append(expiry['CE']['impliedVolatility'])
            if 'PE' in expiry:
                put_ivs.append(expiry['PE']['impliedVolatility'])

        # Sort IVs to calculate percentiles
        call_ivs_sorted = sorted(call_ivs)
        put_ivs_sorted = sorted(put_ivs)

        # Calculate 90th percentile for calls
        if call_ivs_sorted:
            index_90th = int(0.9 * len(call_ivs_sorted))
            call_90th_percentile = call_ivs_sorted[index_90th]
        else:
            call_90th_percentile = None

        # Calculate 10th percentile for puts
        if put_ivs_sorted:
            index_10th = int(0.1 * len(put_ivs_sorted))
            put_10th_percentile = put_ivs_sorted[index_10th]
        else:
            put_10th_percentile = None

        return call_90th_percentile, put_10th_percentile

    def find_iv_discrepancies(self):
        """Find options with IV discrepancies without using numpy"""
        call_90th, put_10th = self.calculate_iv_percentiles()
        discrepancies = []

        for expiry in self.options_chain['records']['data']:
            if 'CE' in expiry and expiry['CE']['impliedVolatility'] > call_90th:
                discrepancies.append({
                    'type': 'CE',
                    'strike': expiry['strikePrice'],
                    'iv': expiry['CE']['impliedVolatility'],
                    'percentile': 90
                })
            if 'PE' in expiry and expiry['PE']['impliedVolatility'] < put_10th:
                discrepancies.append({
                    'type': 'PE',
                    'strike': expiry['strikePrice'],
                    'iv': expiry['PE']['impliedVolatility'],
                    'percentile': 10
                })

        return discrepancies