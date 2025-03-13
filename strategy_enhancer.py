# recommendation_enhancer.py
from datetime import datetime
from market_analyzer import AdvancedMarketAnalyzer, IntradayBandGenerator

class StrategyEnhancer:
    """Uses existing classes through composition"""
    def __init__(self, market_analyzer):
        self.analyzer = market_analyzer
        self.band_generator = IntradayBandGenerator(
            # Add required parameters from your implementation
            api_key=market_analyzer.api_key,
            mongo_endpoints=market_analyzer.mongo_endpoints
        )
        
    def generate_enhanced_recommendation(self, symbol):
        """Combine multiple analyses without modifying original signals"""
        base_signals = self.analyzer.screen_opportunities(symbol)
        enhanced = []
        
        vp = self.analyzer.calculate_volume_profile(symbol)
        oi = self.analyzer.analyze_oi_concentration(symbol)
        bands = self.band_generator.calculate_dynamic_bands(
            self.analyzer._fetch_intraday_data(symbol))
            
        for signal in base_signals:
            enhanced.append({
                **signal,
                'volume_profile': vp,
                'oi_levels': oi,
                'intraday_bands': bands,
                'dynamic_targets': self._calculate_targets(signal, vp, oi, bands)
            })
            
        return enhanced
    
    def _calculate_targets(self, signal, vp, oi, bands):
        """Calculate multi-factor targets"""
        return {
            'conservative': vp['std1_high'] if signal['call_action'] == 'BUY' else vp['std1_low'],
            'moderate': oi['call_max_oi'] if signal['call_action'] == 'BUY' else oi['put_max_oi'],
            'aggressive': bands['upper'] if signal['call_action'] == 'BUY' else bands['lower'],
            'stop_loss': bands['lower'] if signal['call_action'] == 'BUY' else bands['upper']
        }

class RecommendationGenerator:
    def generate_dynamic_recommendation(self, alert):
        """Generate recommendation with level-based targets"""
        recommendation = [
            f"Strategy: {alert.get('strategy', 'Unknown')}",
            f"Spot Price: {alert.get('spot_price', 0):.2f}",
            f"VPOC: {alert.get('volume_profile', {}).get('mean', 0):.2f}",
            f"Max OI Levels: Call {alert.get('oi_levels', {}).get('call_max_oi', 0)} | Put {alert.get('oi_levels', {}).get('put_max_oi', 0)}",
            f"Intraday Bands: {alert.get('intraday_bands', {}).get('lower', 0):.2f} - {alert.get('intraday_bands', {}).get('upper', 0):.2f}"
        ]
        
        return '\n'.join(recommendation)