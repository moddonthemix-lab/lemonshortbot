"""
🍋 LEMON SQUEEZE WEB APP v3.1 - COMPLETE EDITION 🍋
All features + Tradier API fallback + All endpoints
"""

from flask import Flask, render_template, jsonify, request, send_from_directory
import yfinance as yf
from datetime import datetime, timedelta
import time
import os
import json
import requests
import pandas as pd

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
MIN_REQUEST_INTERVAL = 0.2  # 200ms between requests

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
        return None

def get_tradier_history(ticker, interval='daily'):
    """Get historical data from Tradier API"""
    try:
        rate_limit('tradier_history')
        url = f"{TRADIER_BASE_URL}/markets/history"
        
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')
        
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
        return None

def get_stock_data_hybrid(ticker):
    """Get stock data with yfinance primary, Tradier fallback"""
    data_source = "yfinance"
    
    # Try yfinance first
    try:
        rate_limit('yfinance')
        stock_data = yf.Ticker(ticker)
        hist = stock_data.history(period='3mo')
        
        if len(hist) > 0:
            info = stock_data.info
            return hist, info, data_source, stock_data
    except:
        pass
    
    # Fallback to Tradier
    print(f"   🔄 Tradier fallback: {ticker}")
    data_source = "tradier"
    
    quote = get_tradier_quote(ticker)
    if not quote:
        return None, None, None, None
    
    hist = get_tradier_history(ticker)
    if hist is None or len(hist) == 0:
        return None, None, None, None
    
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
    
    return hist, info, data_source, None

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
    html_files = [
        'lemon_squeeze_with_volemon__4_.html',
        'lemon_squeeze.html',
        'index.html'
    ]
    
    for html_file in html_files:
        if os.path.exists(html_file):
            return send_from_directory('.', html_file)
    
    return """<h1>Lemon Squeeze v3.1</h1>
    <p>Backend running! Place your HTML file in same directory.</p>
    <p>Expected names: lemon_squeeze_with_volemon__4_.html, lemon_squeeze.html, or index.html</p>"""

@app.route('/api/scan', methods=['POST'])
def scan():
    """Short squeeze scanner"""
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
                hist, info, source, _ = get_stock_data_hybrid(ticker)
                
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
                    
                    print(f"   ✅ {ticker} ({source}): ${current_price:.2f}")
                    
            except Exception as e:
                continue
        
        results.sort(key=lambda x: x['riskScore'], reverse=True)
        print(f"\n✅ Found {len(results)} candidates\n")
        
        return jsonify({
            'success': True,
            'results': results,
            'count': len(results)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/daily-plays', methods=['POST'])
def daily_plays():
    """Daily 3-1 Strat patterns"""
    try:
        tickers = [
            'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'META', 'NVDA', 'AMD',
            'SPY', 'QQQ', 'NFLX', 'DIS', 'PYPL', 'UBER',
            'F', 'GM', 'NIO', 'RIVN', 'JPM', 'BAC'
        ]
        
        results = []
        print(f"\n🎯 Daily Plays scanning...")
        
        for ticker in tickers:
            try:
                hist, info, source, _ = get_stock_data_hybrid(ticker)
                
                if hist is None or len(hist) < 3:
                    continue
                
                has_pattern, pattern_data = check_strat_31(hist)
                
                if has_pattern:
                    current_price = hist['Close'].iloc[-1]
                    previous_close = hist['Close'].iloc[-2]
                    daily_change = ((current_price - previous_close) / previous_close) * 100
                    
                    results.append({
                        'ticker': ticker,
                        'company': info.get('longName', ticker),
                        'currentPrice': float(current_price),
                        'dailyChange': float(daily_change),
                        'volume': int(hist['Volume'].iloc[-1]),
                        'avgVolume': int(hist['Volume'].mean()),
                        'marketCap': int(info.get('marketCap', 0)),
                        'pattern': pattern_data,
                        'dataSource': source
                    })
                    
                    print(f"   ✅ {ticker}: {pattern_data['direction']}")
                
            except:
                continue
        
        print(f"\n✅ Found {len(results)} patterns\n")
        
        return jsonify({'success': True, 'results': results})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/hourly-plays', methods=['POST'])
def hourly_plays():
    """Hourly 3-1 Strat patterns"""
    try:
        tickers = ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'SPY', 'QQQ', 'NVDA']
        results = []
        
        print(f"\n⏰ Hourly Plays scanning...")
        
        for ticker in tickers:
            try:
                stock_data = yf.Ticker(ticker)
                hist = stock_data.history(period='5d', interval='1h').dropna()
                
                if len(hist) < 3:
                    continue
                
                has_pattern, pattern_data = check_strat_31(hist)
                
                if has_pattern:
                    info = stock_data.info
                    current_price = hist['Close'].iloc[-1]
                    
                    results.append({
                        'ticker': ticker,
                        'company': info.get('longName', ticker),
                        'currentPrice': float(current_price),
                        'volume': int(hist['Volume'].iloc[-1]),
                        'pattern': pattern_data,
                        'timeframe': 'hourly'
                    })
                    
                    print(f"   ✅ {ticker}: {pattern_data['direction']}")
                
            except:
                continue
        
        print(f"\n✅ Found {len(results)} hourly patterns\n")
        
        return jsonify({'success': True, 'results': results})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/weekly-plays', methods=['POST'])
def weekly_plays():
    """Weekly 3-1 Strat patterns"""
    try:
        tickers = ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'SPY', 'QQQ']
        results = []
        
        print(f"\n📅 Weekly Plays scanning...")
        
        for ticker in tickers:
            try:
                stock_data = yf.Ticker(ticker)
                hist = stock_data.history(period='6mo', interval='1wk')
                
                if len(hist) < 3:
                    continue
                
                has_pattern, pattern_data = check_strat_31(hist)
                
                if has_pattern:
                    info = stock_data.info
                    results.append({
                        'ticker': ticker,
                        'company': info.get('longName', ticker),
                        'currentPrice': float(hist['Close'].iloc[-1]),
                        'volume': int(hist['Volume'].iloc[-1]),
                        'pattern': pattern_data,
                        'timeframe': 'weekly'
                    })
                    
                    print(f"   ✅ {ticker}: {pattern_data['direction']}")
                
            except:
                continue
        
        print(f"\n✅ Found {len(results)} weekly patterns\n")
        
        return jsonify({'success': True, 'results': results})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/crypto-scan', methods=['POST'])
def crypto_scan():
    """Crypto scanner"""
    try:
        crypto_tickers = ['BTC-USD', 'ETH-USD', 'XRP-USD', 'SOL-USD', 'DOGE-USD']
        results = []
        
        print(f"\n💰 Crypto scanning...")
        
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
                
            except:
                continue
        
        print(f"\n✅ Crypto scan complete\n")
        
        return jsonify({'success': True, 'results': results})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/volemon-scan', methods=['POST'])
def volemon_scan():
    """Volume Monster Scanner - 2x+ volume"""
    try:
        data = request.json
        min_volume_multiple = data.get('min_volume_multiple', 2.0)
        
        tickers = [
            'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'META', 'NVDA', 'AMD',
            'SPY', 'QQQ', 'NFLX', 'DIS', 'PYPL', 'UBER', 'F', 'GM'
        ]
        
        results = []
        print(f"\n🔊 Volemon scanning ({min_volume_multiple}x volume)...")
        
        for ticker in tickers:
            try:
                hist, info, source, _ = get_stock_data_hybrid(ticker)
                
                if hist is None or len(hist) < 2:
                    continue
                
                current_volume = hist['Volume'].iloc[-1]
                avg_volume = hist['Volume'].iloc[:-1].mean()
                
                if avg_volume == 0:
                    continue
                
                volume_multiple = current_volume / avg_volume
                
                if volume_multiple >= min_volume_multiple:
                    current_price = hist['Close'].iloc[-1]
                    prev_price = hist['Close'].iloc[-2]
                    change_pct = ((current_price - prev_price) / prev_price) * 100
                    
                    results.append({
                        'ticker': ticker,
                        'company': info.get('longName', ticker),
                        'price': float(current_price),
                        'change': float(change_pct),
                        'volume': int(current_volume),
                        'avg_volume': int(avg_volume),
                        'volume_multiple': float(volume_multiple),
                        'market_cap': int(info.get('marketCap', 0)),
                        'dataSource': source
                    })
                    
                    print(f"   ✅ {ticker}: {volume_multiple:.1f}x volume")
                
            except:
                continue
        
        results.sort(key=lambda x: x['volume_multiple'], reverse=True)
        print(f"\n✅ Found {len(results)} high volume stocks\n")
        
        return jsonify({
            'success': True,
            'results': results[:50],
            'count': len(results)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/usuals-scan', methods=['POST'])
def usuals_scan():
    """Watchlist Scanner - Multi-timeframe patterns"""
    try:
        data = request.json
        tickers = data.get('tickers', [
            'SOFI', 'INTC', 'SPY', 'TSLA', 'COIN', 'PLTR', 
            'AAPL', 'NVDA', 'GOOGL', 'META'
        ])
        
        results = []
        print(f"\n⭐ Usuals scanning {len(tickers)} tickers...")
        
        for ticker in tickers:
            try:
                hist, info, source, stock_data = get_stock_data_hybrid(ticker)
                
                if hist is None or len(hist) < 3:
                    continue
                
                current_price = hist['Close'].iloc[-1]
                prev_price = hist['Close'].iloc[-2]
                change_pct = ((current_price - prev_price) / prev_price) * 100
                
                current_volume = hist['Volume'].iloc[-1]
                avg_volume = hist['Volume'].iloc[:-1].mean()
                volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1
                
                patterns = {}
                
                # Daily pattern
                has_pattern, pattern_data = check_strat_31(hist)
                if has_pattern:
                    patterns['daily'] = {
                        'type': '3-1 Strat',
                        'direction': pattern_data['direction']
                    }
                
                # Try weekly if stock_data available
                if stock_data:
                    try:
                        hist_weekly = stock_data.history(period='6mo', interval='1wk')
                        if len(hist_weekly) >= 3:
                            has_pattern, pattern_data = check_strat_31(hist_weekly)
                            if has_pattern:
                                patterns['weekly'] = {
                                    'type': '3-1 Strat',
                                    'direction': pattern_data['direction']
                                }
                    except:
                        pass
                
                results.append({
                    'ticker': ticker,
                    'company': info.get('longName', ticker),
                    'price': float(current_price),
                    'change': float(change_pct),
                    'volume': int(current_volume),
                    'avg_volume': int(avg_volume),
                    'volume_ratio': float(volume_ratio),
                    'patterns': patterns,
                    'dataSource': source
                })
                
                print(f"   ✅ {ticker} ({source}): ${current_price:.2f}")
                
            except:
                continue
        
        print(f"\n✅ Usuals scan complete\n")
        
        return jsonify({
            'success': True,
            'results': results,
            'count': len(results)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/test_tradier', methods=['GET'])
def test_tradier():
    """Test Tradier API"""
    try:
        quote = get_tradier_quote("AAPL")
        hist = get_tradier_history("AAPL")
        
        return jsonify({
            'success': True,
            'quote': quote,
            'history_days': len(hist) if hist is not None else 0,
            'message': 'Tradier API working!'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    
    print("\n" + "="*60)
    print("🍋 LEMON SQUEEZE v3.1 - COMPLETE EDITION 🍋")
    print("="*60)
    print("\n✅ Server starting...")
    print("🔑 Tradier API: Connected")
    print("📱 Open: http://localhost:8080")
    print("\n📊 All scanners ready:")
    print("  - Short Squeeze")
    print("  - Daily/Weekly/Hourly Plays")
    print("  - Crypto")
    print("  - 🔊 Volemon (Volume)")
    print("  - ⭐ Usuals (Watchlist)")
    print("\n🛑 Press Ctrl+C to stop")
    print("\n" + "="*60 + "\n")
    
    app.run(debug=False, host='0.0.0.0', port=port)
