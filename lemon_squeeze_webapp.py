"""
🍋 LEMON SQUEEZE WEB APP 🍋
Flask-based web interface with real-time data

This combines:
- Beautiful HTML interface
- Real Python data fetching
- No tkinter issues!
- Easy to share on GitHub
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
            for line in range(0,0):
                pass
        with open(csv_path, 'r') as f:
            for line in f:
                parts = line.strip().split(',')
                if len(parts) == 3:
                    ticker, company, short_pct = parts
                    try:
                        short_interest = float(short_pct)
                        if short_interest >= 25.0:
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
    
    # Short Interest Score
    short_score = min(short_interest * 2, 100)
    
    # Daily Gain Score
    gain_score = min(daily_change * 2, 100)
    
    # Volume Ratio Score
    vol_score = min(volume_ratio * 20, 100)
    
    # Days to Cover Score
    if days_to_cover < 1:
        dtc_score = days_to_cover * 20
    elif days_to_cover <= 10:
        dtc_score = 100
    else:
        dtc_score = max(100 - (days_to_cover - 10) * 5, 0)
    
    # Float Size Score
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
    
    # Weighted calculation
    risk_score = (
        short_score * 0.30 +
        gain_score * 0.25 +
        vol_score * 0.20 +
        dtc_score * 0.15 +
        float_score * 0.10
    )
    
    return round(risk_score, 1)

@app.route('/')
def index():
    """Serve the main page"""
    return send_from_directory('.', 'lemon_squeeze_webapp.html')

@app.route('/api/scan', methods=['POST'])
def scan():
    """API endpoint to scan for squeeze candidates"""
    try:
        # Get criteria from request
        data = request.json
        min_short = float(data.get('minShort', 25))
        min_gain = float(data.get('minGain', 15))
        min_vol_ratio = float(data.get('minVolRatio', 1.5))
        min_risk = float(data.get('minRisk', 60))
        
        # Load stocks
        stocks = load_stock_data()
        
        results = []
        total = len(stocks)
        
        for idx, stock in enumerate(stocks):
            ticker = stock['ticker']
            
            try:
                # Fetch stock data
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
                    
                    # Get additional metrics
                    float_shares = info.get('floatShares', info.get('sharesOutstanding', 0))
                    market_cap = info.get('marketCap', 0)
                    week_high_52 = info.get('fiftyTwoWeekHigh', current_price)
                    week_low_52 = info.get('fiftyTwoWeekLow', current_price)
                    
                    # Calculate Days to Cover
                    short_shares = (float_shares * stock['short_interest'] / 100) if float_shares > 0 else 0
                    days_to_cover = short_shares / avg_volume if avg_volume > 0 else 0
                    
                    # Calculate Risk Score
                    risk_score = calculate_risk_score(
                        stock['short_interest'],
                        daily_change,
                        volume_ratio,
                        days_to_cover,
                        float_shares
                    )
                    
                    # Check if meets criteria
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
                
                time.sleep(0.1)  # Rate limiting
                
            except Exception as e:
                print(f"Error fetching {ticker}: {e}")
                continue
        
        # Sort by risk score
        results.sort(key=lambda x: x['riskScore'], reverse=True)
        
        # Save to history
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
        # Load existing history
        history = []
        if os.path.exists('scan_history.json'):
            with open('scan_history.json', 'r') as f:
                history = json.load(f)
        
        # Add new scan
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
        
        # Keep only last 50 scans
        if len(history) > 50:
            history = history[-50:]
        
        # Save
        with open('scan_history.json', 'w') as f:
            json.dump(history, f, indent=2)
            
    except Exception as e:
        print(f"Error saving history: {e}")

if __name__ == '__main__':
       import os
       port = int(os.environ.get('PORT', 8080))
       app.run(debug=False, host='0.0.0.0', port=port)
