"""
🍋 LEMON SQUEEZE WEB APP v3.0 - COMPLETE TRADIER EDITION 🍋
Flask-based web interface with:
- Short Squeeze Scanner
- Daily/Weekly/Hourly Plays (3-1 Strat Pattern Scanner)
- Crypto Scanner
- 🔊 Volemon (Auto Volume Scanner)
- ⭐ Usuals (Watchlist Scanner)
- 🔄 Tradier API Integration (reliable data source)
"""

from flask import Flask, render_template, jsonify, request, send_from_directory
import yfinance as yf
from datetime import datetime, timedelta
import time
import os
import json
import requests
import pandas as pd
from threading import Thread

app = Flask(__name__)

# Tradier API Configuration
TRADIER_API_KEY = "Yuvcbpb7jfPIKyyUf8FDNATV48Hc"
TRADIER_BASE_URL = "https://api.tradier.com/v1"
TRADIER_HEADERS = {
    "Authorization": f"Bearer {TRADIER_API_KEY}",
    "Accept": "application/json"
}

# Rate limiting
last_request_time = {}
MIN_REQUEST_INTERVAL = 0.3  # 300ms between requests

# Global state for auto-scanners
volemon_active = False
usuals_active = False
volemon_results = []
usuals_results = []

def rate_limit(key):
    """Simple rate limiting"""
    current_time = time.time()
    if key in last_request_time:
        time_since_last = current_time - last_request_time[key]
        if time_since_last < MIN_REQUEST_INTERVAL:
            time.sleep(MIN_REQUEST_INTERVAL - time_since_last)
    last_request_time[key] = time.time()

def get_tradier_quote(ticker):
    """Get real-time quote from Tradier API"""
    try:
        rate_limit('tradier_quote')
        url = f"{TRADIER_BASE_URL}/markets/quotes"
        params = {"symbols": ticker}
        response = requests.get(url, headers=TRADIER_HEADERS, params=params, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            if 'quotes' in data and 'quote' in data['quotes']:
                return data['quotes']['quote']
        return None
    except Exception as e:
        print(f"❌ Tradier quote error for {ticker}: {e}")
        return None

def get_tradier_history(ticker, interval='daily', start_date=None, end_date=None):
    """
    Get historical data from Tradier API
    interval: 'daily', 'weekly', 'monthly'
    """
    try:
        rate_limit('tradier_history')
        url = f"{TRADIER_BASE_URL}/markets/history"
        
        if not end_date:
            end_date = datetime.now().strftime('%Y-%m-%d')
        if not start_date:
            if interval == 'daily':
                start_date = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')
            elif interval == 'weekly':
                start_date = (datetime.now() - timedelta(days=180)).strftime('%Y-%m-%d')
            else:
                start_date = (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d')
        
        params = {
            "symbol": ticker,
            "interval": interval,
            "start": start_date,
            "end": end_date
        }
        
        response = requests.get(url, headers=TRADIER_HEADERS, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if 'history' in data and data['history'] and 'day' in data['history']:
                days = data['history']['day']
                if not isinstance(days, list):
                    days = [days]
                
                df = pd.DataFrame(days)
                df['date'] = pd.to_datetime(df['date'])
                df = df.set_index('date')
                df = df.rename(columns={
                    'open': 'Open',
                    'high': 'High',
                    'low': 'Low',
                    'close': 'Close',
                    'volume': 'Volume'
                })
                return df
        return None
    except Exception as e:
        print(f"❌ Tradier history error for {ticker}: {e}")
        return None

def get_stock_data_hybrid(ticker, fallback_to_tradier=True):
    """
    Get stock data with yfinance primary, Tradier fallback
    Returns: (hist_data, info_dict, data_source)
    """
    data_source = "yfinance"
    
    # Try yfinance first
    try:
        rate_limit('yfinance')
        stock_data = yf.Ticker(ticker)
        hist = stock_data.history(period='3mo')
        
        if len(hist) > 0:
            info = stock_data.info
            return hist, info, data_source
        else:
            raise Exception("No data returned from yfinance")
            
    except Exception as e:
        if fallback_to_tradier:
            print(f"   🔄 Tradier fallback for {ticker}")
            data_source = "tradier"
            
            quote = get_tradier_quote(ticker)
            if not quote:
                return None, None, None
            
            hist = get_tradier_history(ticker, interval='daily')
            if hist is None or len(hist) == 0:
                return None, None, None
            
            info = {
                'floatShares': quote.get('average_volume', 0) * 30,
                'sharesOutstanding': quote.get('average_volume', 0) * 50,
                'marketCap': quote.get('last', 0) * quote.get('average_volume', 0) * 50,
                'fiftyTwoWeekHigh': quote.get('week_52_high', quote.get('last', 0)),
                'fiftyTwoWeekLow': quote.get('week_52_low', quote.get('last', 0)),
                'shortName': quote.get('description', ticker),
                'longName': quote.get('description', ticker),
                'averageVolume': quote.get('average_volume', 0)
            }
            
            return hist, info, data_source
        
        return None, None, None

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
                    ticker = ticker.strip().replace('$', '')
                    try:
                        short_interest = float(short_pct)
                        if short_interest >= 25.0 and ticker:
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
    """Check if stock has a 3-1 pattern (The Strat)"""
    if len(hist) < 3:
        return False, None
    
    current = hist.iloc[-1]
    previous = hist.iloc[-2]
    before_prev = hist.iloc[-3]
    
    is_three = (previous['High'] > before_prev['High'] and 
                previous['Low'] < before_prev['Low'])
    
    is_one = (current['High'] < previous['High'] and 
              current['Low'] > previous['Low'])
    
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
    # Try different HTML filenames
    html_files = [
        'lemon_squeeze_with_volemon__4_.html',
        'lemon_squeeze.html',
        'index.html'
    ]
    
    for html_file in html_files:
        if os.path.exists(html_file):
            return send_from_directory('.', html_file)
    
    # If no HTML file found, return a simple interface
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Lemon Squeeze v3.0</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                max-width: 800px;
                margin: 50px auto;
                padding: 20px;
                background: linear-gradient(135deg, #FFD700 0%, #FFA500 100%);
            }
            .container {
                background: white;
                padding: 40px;
                border-radius: 20px;
                box-shadow: 0 10px 30px rgba(0,0,0,0.3);
            }
            h1 { color: #FFA500; }
            button {
                background: #FFD700;
                border: none;
                padding: 15px 30px;
                font-size: 18px;
                border-radius: 10px;
                cursor: pointer;
                margin: 10px 5px;
            }
            button:hover { background: #FFA500; }
            .results {
                margin-top: 20px;
                padding: 20px;
                background: #f5f5f5;
                border-radius: 10px;
            }
            .error { color: red; }
            .success { color: green; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🍋 Lemon Squeeze v3.0</h1>
            <p>Backend is running! Put your HTML file in the same directory as the Python file.</p>
            
            <h3>Expected HTML filename:</h3>
            <ul>
                <li>lemon_squeeze_with_volemon__4_.html</li>
                <li>lemon_squeeze.html</li>
                <li>index.html</li>
            </ul>
            
            <h3>Quick Test:</h3>
            <button onclick="testTradier()">Test Tradier API</button>
            <button onclick="testScan()">Test Scanner</button>
            
            <div id="results" class="results" style="display:none;">
                <h3>Results:</h3>
                <pre id="output"></pre>
            </div>
        </div>
        
        <script>
            async function testTradier() {
                const results = document.getElementById('results');
                const output = document.getElementById('output');
                results.style.display = 'block';
                output.textContent = 'Testing Tradier API...';
                
                try {
                    const response = await fetch('/api/test_tradier');
                    const data = await response.json();
                    output.textContent = JSON.stringify(data, null, 2);
                    output.className = data.success ? 'success' : 'error';
                } catch (error) {
                    output.textContent = 'Error: ' + error.message;
                    output.className = 'error';
                }
            }
            
            async function testScan() {
                const results = document.getElementById('results');
                const output = document.getElementById('output');
                results.style.display = 'block';
                output.textContent = 'Running scan...';
                
                try {
                    const response = await fetch('/api/scan', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            minShort: 25,
                            minGain: 10,
                            minVolRatio: 1.5,
                            minRisk: 50
                        })
                    });
                    const data = await response.json();
                    output.textContent = JSON.stringify(data, null, 2);
                    output.className = data.success ? 'success' : 'error';
                } catch (error) {
                    output.textContent = 'Error: ' + error.message;
                    output.className = 'error';
                }
            }
        </script>
    </body>
    </html>
    """

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
        
        print(f"\n🔍 Scanning {len(stocks)} stocks...")
        
        for stock in stocks:
            ticker = stock['ticker']
            
            try:
                hist, info, source = get_stock_data_hybrid(ticker)
                
                if hist is None or len(hist) < 2:
                    continue
                
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
                        'riskScore': float(risk_score),
                        'dataSource': source
                    })
                    
                    print(f"   ✅ {ticker} ({source}): ${current_price:.2f} (+{daily_change:.1f}%)")
                    
            except Exception as e:
                continue
        
        results.sort(key=lambda x: x['riskScore'], reverse=True)
        
        print(f"\n✅ Scan complete! Found {len(results)} candidates\n")
        
        return jsonify({
            'success': True,
            'results': results,
            'count': len(results)
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/daily-plays', methods=['POST'])
def daily_plays():
    """Scan for daily 3-1 Strat patterns"""
    try:
        popular_tickers = [
            'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'META', 'NVDA', 'AMD',
            'SPY', 'QQQ', 'IWM', 'DIA',
            'NFLX', 'DIS', 'PYPL', 'SQ', 'ROKU', 'UBER',
            'F', 'GM', 'NIO', 'RIVN',
            'JPM', 'BAC', 'GS', 'MS', 'C',
            'XOM', 'CVX', 'COP',
            'PFE', 'JNJ', 'MRNA',
            'WMT', 'TGT', 'COST', 'HD',
        ]
        
        high_short_stocks = load_stock_data()
        for stock in high_short_stocks:
            if stock['ticker'] not in popular_tickers:
                popular_tickers.append(stock['ticker'])
        
        results = []
        
        print(f"\n🎯 Daily Plays scan starting...")
        
        for ticker in popular_tickers:
            try:
                hist, info, source = get_stock_data_hybrid(ticker)
                
                if hist is None or len(hist) < 3:
                    continue
                
                has_pattern, pattern_data = check_strat_31(hist)
                
                if has_pattern:
                    current_price = hist['Close'].iloc[-1]
                    previous_close = hist['Close'].iloc[-2]
                    daily_change = ((current_price - previous_close) / previous_close) * 100
                    current_volume = hist['Volume'].iloc[-1]
                    avg_volume = hist['Volume'].mean()
                    
                    results.append({
                        'ticker': ticker,
                        'company': info.get('longName', ticker),
                        'currentPrice': float(current_price),
                        'dailyChange': float(daily_change),
                        'volume': int(current_volume),
                        'avgVolume': int(avg_volume),
                        'marketCap': int(info.get('marketCap', 0)),
                        'pattern': pattern_data,
                        'dataSource': source
                    })
                    
                    print(f"   ✅ {ticker} ({source}): {pattern_data['direction']}")
                
            except Exception as e:
                continue
        
        results.sort(key=lambda x: x['volume'], reverse=True)
        
        print(f"\n✅ Found {len(results)} daily patterns\n")
        
        return jsonify({
            'success': True,
            'results': results
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/hourly-plays', methods=['POST'])
def hourly_plays():
    """Scan for hourly 3-1 Strat patterns"""
    try:
        popular_tickers = [
            'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'META', 'NVDA', 'AMD',
            'SPY', 'QQQ', 'NFLX', 'DIS'
        ]
        
        results = []
        
        print(f"\n⏰ Hourly Plays scan starting...")
        
        for ticker in popular_tickers:
            try:
                stock_data = yf.Ticker(ticker)
                hist = stock_data.history(period='5d', interval='1h')
                hist = hist.dropna()
                
                if len(hist) < 3:
                    continue
                
                has_pattern, pattern_data = check_strat_31(hist)
                
                if has_pattern:
                    info = stock_data.info
                    current_price = hist['Close'].iloc[-1]
                    previous_close = hist['Close'].iloc[-2]
                    hourly_change = ((current_price - previous_close) / previous_close) * 100
                    
                    results.append({
                        'ticker': ticker,
                        'company': info.get('longName', ticker),
                        'currentPrice': float(current_price),
                        'hourlyChange': float(hourly_change),
                        'volume': int(hist['Volume'].iloc[-1]),
                        'pattern': pattern_data,
                        'timeframe': 'hourly',
                        'dataSource': 'yfinance'
                    })
                    
                    print(f"   ✅ {ticker}: {pattern_data['direction']} hourly")
                
            except Exception as e:
                continue
        
        results.sort(key=lambda x: x['volume'], reverse=True)
        
        print(f"\n✅ Found {len(results)} hourly patterns\n")
        
        return jsonify({
            'success': True,
            'results': results
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/weekly-plays', methods=['POST'])
def weekly_plays():
    """Scan for weekly 3-1 Strat patterns"""
    try:
        popular_tickers = [
            'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'META', 'NVDA', 'AMD',
            'SPY', 'QQQ', 'IWM', 'DIA'
        ]
        
        results = []
        
        print(f"\n📅 Weekly Plays scan starting...")
        
        for ticker in popular_tickers:
            try:
                stock_data = yf.Ticker(ticker)
                hist = stock_data.history(period='6mo', interval='1wk')
                
                if len(hist) < 3:
                    continue
                
                has_pattern, pattern_data = check_strat_31(hist)
                
                if has_pattern:
                    info = stock_data.info
                    current_price = hist['Close'].iloc[-1]
                    previous_close = hist['Close'].iloc[-2]
                    weekly_change = ((current_price - previous_close) / previous_close) * 100
                    
                    results.append({
                        'ticker': ticker,
                        'company': info.get('longName', ticker),
                        'currentPrice': float(current_price),
                        'weeklyChange': float(weekly_change),
                        'volume': int(hist['Volume'].iloc[-1]),
                        'pattern': pattern_data,
                        'timeframe': 'weekly',
                        'dataSource': 'yfinance'
                    })
                    
                    print(f"   ✅ {ticker}: {pattern_data['direction']} weekly")
                
            except Exception as e:
                continue
        
        results.sort(key=lambda x: x['volume'], reverse=True)
        
        print(f"\n✅ Found {len(results)} weekly patterns\n")
        
        return jsonify({
            'success': True,
            'results': results
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/crypto-scan', methods=['POST'])
def crypto_scan():
    """Scan crypto"""
    try:
        crypto_tickers = ['BTC-USD', 'ETH-USD', 'XRP-USD', 'SOL-USD', 'DOGE-USD', 'ADA-USD']
        results = []
        
        print(f"\n💰 Crypto scan starting...")
        
        for ticker in crypto_tickers:
            try:
                crypto = yf.Ticker(ticker)
                hist = crypto.history(period='1mo')
                
                if len(hist) < 2:
                    continue
                
                current_price = hist['Close'].iloc[-1]
                previous_close = hist['Close'].iloc[-2]
                daily_change = ((current_price - previous_close) / previous_close) * 100
                
                results.append({
                    'ticker': ticker.replace('-USD', ''),
                    'price': float(current_price),
                    'change': float(daily_change),
                    'volume': int(hist['Volume'].iloc[-1])
                })
                
                print(f"   ✅ {ticker}: ${current_price:.2f}")
                
            except Exception as e:
                continue
        
        print(f"\n✅ Crypto scan complete\n")
        
        return jsonify({
            'success': True,
            'results': results
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/test_tradier', methods=['GET'])
def test_tradier():
    """Test Tradier API"""
    try:
        ticker = "AAPL"
        quote = get_tradier_quote(ticker)
        hist = get_tradier_history(ticker)
        
        return jsonify({
            'success': True,
            'quote': quote,
            'history_days': len(hist) if hist is not None else 0,
            'message': 'Tradier API is working!'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    
    print("\n" + "="*60)
    print("🍋 LEMON SQUEEZE WEB APP v3.0 - TRADIER EDITION 🍋")
    print("="*60)
    print("\n✅ Server starting...")
    print("🔑 Tradier API: Connected")
    print("📱 Open: http://localhost:8080")
    print("\n📊 Features:")
    print("  - Short Squeeze Scanner")
    print("  - Hourly/Daily/Weekly Plays (3-1 Strat)")
    print("  - Crypto Scanner")
    print("  - 🔄 Hybrid API (yfinance + Tradier)")
    print("\n🛑 Press Ctrl+C to stop")
    print("\n" + "="*60 + "\n")
    
    app.run(debug=False, host='0.0.0.0', port=port)
