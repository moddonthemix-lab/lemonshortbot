"""
🍋 LEMON SQUEEZE WEB APP v2.0 🍋
Flask-based web interface with:
- Short Squeeze Scanner
- Daily Plays (3-1 Strat Pattern Scanner)
"""

from flask import Flask, render_template, jsonify, request, send_from_directory
import yfinance as yf
from datetime import datetime
import time
import os
import json

app = Flask(__name__)

# Load high short interest stocks
def load_stock_data():
    """Load stocks from CSV"""
    stocks = []
    csv_path = 'high_short_stocks.csv'
    
    if os.path.exists(csv_path):
        with open(csv_path, 'r') as f:
            for line in f:
                parts = line.strip().split(',')
                if len(parts) == 3:
                    ticker, company, short_pct = parts
                    # Clean ticker - remove $ and whitespace
                    ticker = ticker.strip().replace('$', '')
                    try:
                        short_interest = float(short_pct)
                        if short_interest >= 25.0 and ticker:  # Make sure ticker isn't empty
                            stocks.append({
                                'ticker': ticker,
                                'company': company,
                                'short_interest': short_interest
                            })
                    except ValueError:
                        continue
    
    return stocks

def calculate_risk_score(short_interest, daily_change, volume_ratio, days_to_cover, float_shares):
    """Calculate risk score 0-100"""
    
    short_score = min(short_interest * 2, 100)
    gain_score = min(daily_change * 2, 100)
    vol_score = min(volume_ratio * 20, 100)
    
    if days_to_cover < 1:
        dtc_score = days_to_cover * 20
    elif days_to_cover <= 10:
        dtc_score = 100
    else:
        dtc_score = max(100 - (days_to_cover - 10) * 5, 0)
    
    float_millions = float_shares / 1_000_000 if float_shares > 0 else 999
    if float_millions < 50:
        float_score = 100
    elif float_millions < 100:
        float_score = 80
    elif float_millions < 200:
        float_score = 60
    elif float_millions < 500:
        float_score = 40
    else:
        float_score = 20
    
    risk_score = (
        short_score * 0.30 +
        gain_score * 0.25 +
        vol_score * 0.20 +
        dtc_score * 0.15 +
        float_score * 0.10
    )
    
    return round(risk_score, 1)

def check_strat_31(hist):
    """
    Check if stock has a 3-1 pattern (The Strat)
    3 = Outside bar (higher high + lower low than previous)
    1 = Inside bar (lower high + higher low than previous)
    """
    if len(hist) < 3:
        return False, None
    
    # Get last 3 candles
    current = hist.iloc[-1]
    previous = hist.iloc[-2]
    before_prev = hist.iloc[-3]
    
    # Check if previous candle is a "3" (outside bar)
    is_three = (previous['High'] > before_prev['High'] and 
                previous['Low'] < before_prev['Low'])
    
    # Check if current candle is a "1" (inside bar)
    is_one = (current['High'] < previous['High'] and 
              current['Low'] > previous['Low'])
    
    # Is bullish or bearish?
    direction = "bullish" if current['Close'] > current['Open'] else "bearish"
    
    if is_three and is_one:
        pattern_data = {
            'has_pattern': True,
            'direction': direction,
            'three_candle': {
                'high': float(previous['High']),
                'low': float(previous['Low']),
                'close': float(previous['Close']),
                'date': previous.name.strftime('%Y-%m-%d')
            },
            'one_candle': {
                'high': float(current['High']),
                'low': float(current['Low']),
                'close': float(current['Close']),
                'open': float(current['Open']),
                'date': current.name.strftime('%Y-%m-%d')
            }
        }
        return True, pattern_data
    
    return False, None

@app.route('/')
def index():
    """Serve the main page"""
    return send_from_directory('.', 'lemon_squeeze_webapp.html')

@app.route('/api/scan', methods=['POST'])
def scan():
    """API endpoint to scan for squeeze candidates"""
    try:
        data = request.json
        min_short = float(data.get('minShort', 25))
        min_gain = float(data.get('minGain', 15))
        min_vol_ratio = float(data.get('minVolRatio', 1.5))
        min_risk = float(data.get('minRisk', 60))
        
        stocks = load_stock_data()
        results = []
        
        for stock in stocks:
            ticker = stock['ticker']
            
            try:
                stock_data = yf.Ticker(ticker)
                hist = stock_data.history(period='3mo')
                info = stock_data.info
                
                if len(hist) >= 2:
                    current_price = hist['Close'].iloc[-1]
                    previous_close = hist['Close'].iloc[-2]
                    daily_change = ((current_price - previous_close) / previous_close) * 100
                    
                    current_volume = hist['Volume'].iloc[-1]
                    avg_volume = hist['Volume'].iloc[-21:-1].mean() if len(hist) > 20 else hist['Volume'].mean()
                    volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0
                    
                    float_shares = info.get('floatShares', info.get('sharesOutstanding', 0))
                    market_cap = info.get('marketCap', 0)
                    week_high_52 = info.get('fiftyTwoWeekHigh', current_price)
                    week_low_52 = info.get('fiftyTwoWeekLow', current_price)
                    
                    short_shares = (float_shares * stock['short_interest'] / 100) if float_shares > 0 else 0
                    days_to_cover = short_shares / avg_volume if avg_volume > 0 else 0
                    
                    risk_score = calculate_risk_score(
                        stock['short_interest'],
                        daily_change,
                        volume_ratio,
                        days_to_cover,
                        float_shares
                    )
                    
                    if (stock['short_interest'] >= min_short and 
                        daily_change >= min_gain and 
                        volume_ratio >= min_vol_ratio and
                        risk_score >= min_risk):
                        
                        results.append({
                            'ticker': ticker,
                            'company': stock['company'],
                            'shortInterest': stock['short_interest'],
                            'previousClose': float(previous_close),
                            'currentPrice': float(current_price),
                            'dailyChange': float(daily_change),
                            'volume': int(current_volume),
                            'avgVolume': int(avg_volume),
                            'volumeRatio': float(volume_ratio),
                            'floatShares': int(float_shares),
                            'marketCap': int(market_cap),
                            'daysToCover': float(days_to_cover),
                            'weekHigh52': float(week_high_52),
                            'weekLow52': float(week_low_52),
                            'riskScore': float(risk_score)
                        })
                
                time.sleep(0.1)
                
            except Exception as e:
                continue
        
        results.sort(key=lambda x: x['riskScore'], reverse=True)
        save_scan_to_history(results, min_short, min_gain, min_vol_ratio, min_risk)
        
        return jsonify({
            'success': True,
            'results': results,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/daily-plays', methods=['POST'])
def daily_plays():
    """API endpoint to scan for 3-1 Strat patterns - NO FILTERS"""
    try:
        # Get popular stocks list (you can customize this)
        popular_tickers = [
            'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'META', 'NVDA', 'AMD',
            'SPY', 'QQQ', 'IWM', 'DIA',
            'NFLX', 'DIS', 'BABA', 'PYPL', 'SQ', 'ROKU', 'SNAP', 'UBER',
            'F', 'GM', 'NIO', 'LCID', 'RIVN',
            'BA', 'GE', 'CAT', 'DE',
            'JPM', 'BAC', 'GS', 'MS', 'C',
            'XOM', 'CVX', 'COP', 'SLB',
            'PFE', 'JNJ', 'MRNA', 'BNTX',
            'WMT', 'TGT', 'COST', 'HD', 'LOW',
        ]
        
        # Add high short stocks to the list
        high_short_stocks = load_stock_data()
        for stock in high_short_stocks:
            if stock['ticker'] not in popular_tickers:
                popular_tickers.append(stock['ticker'])
        
        results = []
        processed = 0
        total = len(popular_tickers)
        
        print(f"\n🎯 Starting Daily Plays scan for {total} stocks...")
        
        for ticker in popular_tickers:
            processed += 1
            try:
                stock_data = yf.Ticker(ticker)
                hist = stock_data.history(period='1mo')
                info = stock_data.info
                
                if len(hist) >= 3:
                    has_pattern, pattern_data = check_strat_31(hist)
                    
                    if has_pattern:
                        current_volume = hist['Volume'].iloc[-1]
                        
                        # Calculate daily change
                        current_price = hist['Close'].iloc[-1]
                        previous_close = hist['Close'].iloc[-2]
                        daily_change = ((current_price - previous_close) / previous_close) * 100
                        
                        # Get company name
                        company_name = info.get('longName', ticker)
                        market_cap = info.get('marketCap', 0)
                        avg_volume = hist['Volume'].mean()
                        
                        results.append({
                            'ticker': ticker,
                            'company': company_name,
                            'currentPrice': float(current_price),
                            'dailyChange': float(daily_change),
                            'volume': int(current_volume),
                            'avgVolume': int(avg_volume),
                            'marketCap': int(market_cap),
                            'pattern': pattern_data
                        })
                        
                        print(f"✅ Found {pattern_data['direction']} pattern: {ticker} ({processed}/{total})")
                
                if processed % 10 == 0:
                    print(f"📊 Progress: {processed}/{total} stocks scanned, {len(results)} patterns found")
                
                time.sleep(0.05)  # Faster for more stocks
                
            except Exception as e:
                print(f"❌ Error on {ticker}: {e}")
                continue
        
        # Sort by volume (most active first)
        results.sort(key=lambda x: x['volume'], reverse=True)
        
        print(f"\n✅ Scan complete! Found {len(results)} total patterns")
        
        return jsonify({
            'success': True,
            'results': results,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        print(f"💥 Error in daily_plays: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/history', methods=['GET'])
def get_history():
    """Get scan history"""
    try:
        if os.path.exists('scan_history.json'):
            with open('scan_history.json', 'r') as f:
                history = json.load(f)
                return jsonify({
                    'success': True,
                    'history': history
                })
        return jsonify({
            'success': True,
            'history': []
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

def save_scan_to_history(results, min_short, min_gain, min_vol_ratio, min_risk):
    """Save scan to history"""
    try:
        history = []
        if os.path.exists('scan_history.json'):
            with open('scan_history.json', 'r') as f:
                history = json.load(f)
        
        scan_data = {
            'timestamp': datetime.now().isoformat(),
            'criteria': {
                'min_short': min_short,
                'min_gain': min_gain,
                'min_vol_ratio': min_vol_ratio,
                'min_risk': min_risk
            },
            'results_count': len(results),
            'tickers': [r['ticker'] for r in results],
            'top_risk_scores': [{'ticker': r['ticker'], 'score': r['riskScore']} for r in results[:10]],
            'avg_risk_score': sum(r['riskScore'] for r in results) / len(results) if results else 0
        }
        
        history.append(scan_data)
        
        if len(history) > 50:
            history = history[-50:]
        
        with open('scan_history.json', 'w') as f:
            json.dump(history, f, indent=2)
            
    except Exception as e:
        print(f"Error saving history: {e}")

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 8080))
    
    print("\n" + "="*60)
    print("🍋 LEMON SQUEEZE WEB APP v2.0 🍋")
    print("="*60)
    print("\n✅ Server starting...")
    print("📱 Open your browser and go to: http://localhost:8080")
    print("🛑 Press Ctrl+C to stop the server")
    print("\n" + "="*60 + "\n")
    
    app.run(debug=False, host='0.0.0.0', port=port)
