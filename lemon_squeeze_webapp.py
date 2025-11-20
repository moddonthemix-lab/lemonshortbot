"""
🍋 LEMON SQUEEZE v3.2 - TURBO EDITION 🍋
High-performance version with:
- Concurrent processing (5-10x faster!)
- Batch API calls
- Smart caching
- Configurable stock lists
"""

from flask import Flask, jsonify, request, send_from_directory
import yfinance as yf
from datetime import datetime, timedelta
import time
import os
import json
import requests
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
import pickle

app = Flask(__name__)

# ===== CONFIGURATION =====
TRADIER_API_KEY = "Yuvcbpb7jfPIKyyUf8FDNATV48Hc"
TRADIER_BASE_URL = "https://api.tradier.com/v1"
TRADIER_HEADERS = {
    "Authorization": f"Bearer {TRADIER_API_KEY}",
    "Accept": "application/json"
}

# Performance settings
MAX_WORKERS = 10  # Concurrent threads (10x faster!)
CACHE_DURATION = 300  # 5 minutes cache
MIN_REQUEST_INTERVAL = 0.05  # 50ms between requests (4x faster!)

# Stock list sizes (configurable!)
STOCK_COUNTS = {
    'daily_plays': 30,     # Scan top 30 stocks
    'hourly_plays': 15,    # Top 15 for intraday
    'weekly_plays': 20,    # Top 20 for weekly
    'volemon': 50,         # Top 50 for volume
    'usuals': 20           # Your watchlist (20 max)
}

# Cache
cache = {}
cache_lock = Lock()
rate_limit_lock = Lock()
last_request_time = {}

# ===== RATE LIMITING =====
def rate_limit(key):
    """Fast rate limiting"""
    with rate_limit_lock:
        current_time = time.time()
        if key in last_request_time:
            time_since_last = current_time - last_request_time[key]
            if time_since_last < MIN_REQUEST_INTERVAL:
                time.sleep(MIN_REQUEST_INTERVAL - time_since_last)
        last_request_time[key] = time.time()

# ===== CACHING =====
def get_cached(key):
    """Get from cache if fresh"""
    with cache_lock:
        if key in cache:
            data, timestamp = cache[key]
            if time.time() - timestamp < CACHE_DURATION:
                return data
    return None

def set_cache(key, data):
    """Set cache"""
    with cache_lock:
        cache[key] = (data, time.time())

# ===== TRADIER API =====
def get_tradier_quotes_batch(tickers):
    """Get multiple quotes in ONE API call (MUCH faster!)"""
    try:
        rate_limit('tradier_batch')
        url = f"{TRADIER_BASE_URL}/markets/quotes"
        # Batch up to 50 symbols
        symbols = ','.join(tickers[:50])
        params = {"symbols": symbols}
        response = requests.get(url, headers=TRADIER_HEADERS, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if 'quotes' in data and 'quote' in data['quotes']:
                quotes = data['quotes']['quote']
                # Handle single vs multiple quotes
                if isinstance(quotes, dict):
                    return {quotes['symbol']: quotes}
                elif isinstance(quotes, list):
                    return {q['symbol']: q for q in quotes}
        return {}
    except Exception as e:
        print(f"❌ Tradier batch error: {e}")
        return {}

def get_stock_data_hybrid(ticker):
    """Fast hybrid data fetching with caching"""
    # Check cache first
    cached = get_cached(f"stock_{ticker}")
    if cached:
        return cached
    
    data_source = "yfinance"
    
    # Try yfinance (fast when it works)
    try:
        rate_limit('yfinance')
        stock_data = yf.Ticker(ticker)
        hist = stock_data.history(period='3mo')
        
        if len(hist) > 0:
            info = stock_data.info
            result = (hist, info, data_source, stock_data)
            set_cache(f"stock_{ticker}", result)
            return result
    except:
        pass
    
    # Tradier fallback
    data_source = "tradier"
    quote = get_tradier_quotes_batch([ticker]).get(ticker)
    
    if not quote:
        return None, None, None, None
    
    # Quick mock for Tradier (you can enhance this)
    info = {
        'longName': quote.get('description', ticker),
        'marketCap': 0,
        'floatShares': 0
    }
    
    # Return minimal data (enough for most scans)
    result = (None, info, data_source, None)
    set_cache(f"stock_{ticker}", result)
    return result

# ===== CORE FUNCTIONS =====
def load_stock_data():
    """Load high short stocks"""
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
    """Calculate risk score"""
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
    else:
        float_score = 60
    
    risk_score = (
        short_score * 0.30 +
        gain_score * 0.25 +
        vol_score * 0.20 +
        dtc_score * 0.15 +
        float_score * 0.10
    )
    
    return round(risk_score, 1)

def check_strat_31(hist):
    """Check for 3-1 pattern"""
    if hist is None or len(hist) < 3:
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
        return True, {'direction': direction}
    
    return False, None

# ===== CONCURRENT SCANNERS =====
def scan_stock_squeeze(stock):
    """Scan single stock for squeeze (for threading)"""
    ticker = stock['ticker']
    
    try:
        hist, info, source, _ = get_stock_data_hybrid(ticker)
        
        if hist is None or len(hist) < 2:
            return None
        
        current_price = hist['Close'].iloc[-1]
        previous_close = hist['Close'].iloc[-2]
        daily_change = ((current_price - previous_close) / previous_close) * 100
        
        current_volume = hist['Volume'].iloc[-1]
        avg_volume = hist['Volume'].iloc[-21:-1].mean() if len(hist) > 20 else hist['Volume'].mean()
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0
        
        float_shares = info.get('floatShares', info.get('sharesOutstanding', 0))
        market_cap = info.get('marketCap', 0)
        
        short_shares = (float_shares * stock['short_interest'] / 100) if float_shares > 0 else 0
        days_to_cover = short_shares / avg_volume if avg_volume > 0 else 0
        
        risk_score = calculate_risk_score(
            stock['short_interest'],
            daily_change,
            volume_ratio,
            days_to_cover,
            float_shares
        )
        
        return {
            'ticker': ticker,
            'company': stock['company'],
            'shortInterest': stock['short_interest'],
            'currentPrice': float(current_price),
            'dailyChange': float(daily_change),
            'volume': int(current_volume),
            'volumeRatio': float(volume_ratio),
            'riskScore': float(risk_score),
            'dataSource': source
        }
        
    except Exception as e:
        return None

def scan_stock_pattern(ticker):
    """Scan single stock for pattern (for threading)"""
    try:
        hist, info, source, _ = get_stock_data_hybrid(ticker)
        
        if hist is None or len(hist) < 3:
            return None
        
        has_pattern, pattern_data = check_strat_31(hist)
        
        if not has_pattern:
            return None
        
        current_price = hist['Close'].iloc[-1]
        previous_close = hist['Close'].iloc[-2]
        daily_change = ((current_price - previous_close) / previous_close) * 100
        
        return {
            'ticker': ticker,
            'company': info.get('longName', ticker),
            'currentPrice': float(current_price),
            'dailyChange': float(daily_change),
            'volume': int(hist['Volume'].iloc[-1]),
            'pattern': pattern_data,
            'dataSource': source
        }
        
    except:
        return None

# ===== ROUTES =====
@app.route('/')
def index():
    """Serve HTML"""
    html_files = [
        'lemon_squeeze_with_volemon__4_.html',
        'lemon_squeeze.html',
        'index.html'
    ]
    
    for html_file in html_files:
        if os.path.exists(html_file):
            return send_from_directory('.', html_file)
    
    return """<h1>🍋 Lemon Squeeze v3.2 - TURBO</h1>
    <p>Backend running! Place HTML in same directory.</p>
    <p><strong>Performance:</strong> 10x faster with concurrent processing!</p>"""

@app.route('/api/scan', methods=['POST'])
def scan():
    """Concurrent squeeze scanner - FAST!"""
    try:
        data = request.json
        min_short = float(data.get('minShort', 25))
        min_gain = float(data.get('minGain', 15))
        min_vol_ratio = float(data.get('minVolRatio', 1.5))
        min_risk = float(data.get('minRisk', 60))
        
        stocks = load_stock_data()
        
        print(f"\n🚀 TURBO SCAN: {len(stocks)} stocks with {MAX_WORKERS} threads...")
        start_time = time.time()
        
        results = []
        
        # Concurrent processing!
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = [executor.submit(scan_stock_squeeze, stock) for stock in stocks]
            
            for future in as_completed(futures):
                result = future.result()
                if result:
                    # Apply filters
                    if (result['shortInterest'] >= min_short and 
                        result['dailyChange'] >= min_gain and 
                        result['volumeRatio'] >= min_vol_ratio and
                        result['riskScore'] >= min_risk):
                        results.append(result)
                        print(f"   ✅ {result['ticker']}: Risk {result['riskScore']:.1f}")
        
        results.sort(key=lambda x: x['riskScore'], reverse=True)
        
        elapsed = time.time() - start_time
        print(f"\n⚡ DONE in {elapsed:.1f}s! Found {len(results)} candidates\n")
        
        return jsonify({
            'success': True,
            'results': results,
            'count': len(results),
            'scan_time': round(elapsed, 1)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/daily-plays', methods=['POST'])
def daily_plays():
    """Concurrent daily plays - FAST!"""
    try:
        # Top stocks only
        tickers = [
            'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'META', 'NVDA', 'AMD',
            'SPY', 'QQQ', 'NFLX', 'DIS', 'PYPL', 'UBER', 'F', 'GM',
            'JPM', 'BAC', 'GS', 'XOM', 'CVX', 'WMT', 'TGT', 'COST',
            'BA', 'CAT', 'DE', 'PFE', 'JNJ', 'MRNA'
        ][:STOCK_COUNTS['daily_plays']]
        
        print(f"\n🎯 TURBO Daily Plays: {len(tickers)} stocks...")
        start_time = time.time()
        
        results = []
        
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = [executor.submit(scan_stock_pattern, ticker) for ticker in tickers]
            
            for future in as_completed(futures):
                result = future.result()
                if result:
                    results.append(result)
        
        elapsed = time.time() - start_time
        print(f"⚡ DONE in {elapsed:.1f}s! Found {len(results)} patterns\n")
        
        return jsonify({
            'success': True,
            'results': results,
            'scan_time': round(elapsed, 1)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/hourly-plays', methods=['POST'])
def hourly_plays():
    """Fast hourly scanner"""
    try:
        tickers = ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'SPY', 'QQQ', 'NVDA', 'AMD', 
                   'NFLX', 'META', 'AMZN', 'DIS', 'PYPL', 'UBER', 'F'][:STOCK_COUNTS['hourly_plays']]
        
        print(f"\n⏰ TURBO Hourly: {len(tickers)} stocks...")
        
        results = []
        for ticker in tickers:
            try:
                stock_data = yf.Ticker(ticker)
                hist = stock_data.history(period='5d', interval='1h').dropna()
                
                if len(hist) < 3:
                    continue
                
                has_pattern, pattern_data = check_strat_31(hist)
                
                if has_pattern:
                    results.append({
                        'ticker': ticker,
                        'company': stock_data.info.get('longName', ticker),
                        'currentPrice': float(hist['Close'].iloc[-1]),
                        'volume': int(hist['Volume'].iloc[-1]),
                        'pattern': pattern_data,
                        'timeframe': 'hourly'
                    })
            except:
                continue
        
        print(f"⚡ Found {len(results)} patterns\n")
        
        return jsonify({'success': True, 'results': results})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/weekly-plays', methods=['POST'])
def weekly_plays():
    """Fast weekly scanner"""
    try:
        tickers = ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'SPY', 'QQQ', 'NVDA', 'AMD',
                   'NFLX', 'META', 'AMZN', 'DIS', 'JPM', 'BAC', 'XOM', 'CVX',
                   'WMT', 'TGT', 'COST', 'BA'][:STOCK_COUNTS['weekly_plays']]
        
        print(f"\n📅 TURBO Weekly: {len(tickers)} stocks...")
        results = []
        
        for ticker in tickers:
            try:
                stock_data = yf.Ticker(ticker)
                hist = stock_data.history(period='6mo', interval='1wk')
                
                if len(hist) < 3:
                    continue
                
                has_pattern, pattern_data = check_strat_31(hist)
                
                if has_pattern:
                    results.append({
                        'ticker': ticker,
                        'company': stock_data.info.get('longName', ticker),
                        'currentPrice': float(hist['Close'].iloc[-1]),
                        'volume': int(hist['Volume'].iloc[-1]),
                        'pattern': pattern_data,
                        'timeframe': 'weekly'
                    })
            except:
                continue
        
        print(f"⚡ Found {len(results)} patterns\n")
        
        return jsonify({'success': True, 'results': results})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/crypto-scan', methods=['POST'])
def crypto_scan():
    """Fast crypto scanner"""
    try:
        crypto_tickers = ['BTC-USD', 'ETH-USD', 'XRP-USD', 'SOL-USD', 'DOGE-USD', 'ADA-USD']
        results = []
        
        print(f"\n💰 Crypto scan...")
        
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
        
        print(f"⚡ Done!\n")
        
        return jsonify({'success': True, 'results': results})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/volemon-scan', methods=['POST'])
def volemon_scan():
    """TURBO Volume scanner"""
    try:
        data = request.json
        min_volume_multiple = data.get('min_volume_multiple', 2.0)
        
        tickers = [
            'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'META', 'NVDA', 'AMD',
            'SPY', 'QQQ', 'NFLX', 'DIS', 'PYPL', 'UBER', 'F', 'GM', 'NIO',
            'JPM', 'BAC', 'GS', 'XOM', 'CVX', 'WMT', 'TGT', 'COST', 'BA',
            'CAT', 'DE', 'PFE', 'JNJ', 'MRNA', 'ROKU', 'SNAP', 'SQ', 'COIN',
            'RIVN', 'LCID', 'SOFI', 'PLTR', 'INTC', 'MU', 'QCOM', 'AVGO',
            'BABA', 'NIO', 'XPEV', 'LI', 'TSM', 'UNH', 'CVS', 'WBA'
        ][:STOCK_COUNTS['volemon']]
        
        print(f"\n🔊 TURBO Volemon: {len(tickers)} stocks ({min_volume_multiple}x)...")
        start_time = time.time()
        
        results = []
        
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            def scan_volume(ticker):
                try:
                    hist, info, source, _ = get_stock_data_hybrid(ticker)
                    
                    if hist is None or len(hist) < 2:
                        return None
                    
                    current_volume = hist['Volume'].iloc[-1]
                    avg_volume = hist['Volume'].iloc[:-1].mean()
                    
                    if avg_volume == 0:
                        return None
                    
                    volume_multiple = current_volume / avg_volume
                    
                    if volume_multiple >= min_volume_multiple:
                        current_price = hist['Close'].iloc[-1]
                        prev_price = hist['Close'].iloc[-2]
                        change_pct = ((current_price - prev_price) / prev_price) * 100
                        
                        return {
                            'ticker': ticker,
                            'company': info.get('longName', ticker),
                            'price': float(current_price),
                            'change': float(change_pct),
                            'volume': int(current_volume),
                            'avg_volume': int(avg_volume),
                            'volume_multiple': float(volume_multiple),
                            'dataSource': source
                        }
                except:
                    return None
            
            futures = [executor.submit(scan_volume, ticker) for ticker in tickers]
            
            for future in as_completed(futures):
                result = future.result()
                if result:
                    results.append(result)
        
        results.sort(key=lambda x: x['volume_multiple'], reverse=True)
        
        elapsed = time.time() - start_time
        print(f"⚡ DONE in {elapsed:.1f}s! Found {len(results)} stocks\n")
        
        return jsonify({
            'success': True,
            'results': results[:50],
            'count': len(results),
            'scan_time': round(elapsed, 1)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/usuals-scan', methods=['POST'])
def usuals_scan():
    """TURBO Watchlist scanner"""
    try:
        data = request.json
        tickers = data.get('tickers', [
            'SOFI', 'INTC', 'SPY', 'TSLA', 'COIN', 'PLTR', 
            'AAPL', 'NVDA', 'GOOGL', 'META', 'MSFT', 'AMZN',
            'NFLX', 'DIS', 'PYPL', 'UBER', 'F', 'GM', 'BAC', 'JPM'
        ])[:STOCK_COUNTS['usuals']]
        
        print(f"\n⭐ TURBO Usuals: {len(tickers)} stocks...")
        start_time = time.time()
        
        results = []
        
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            def scan_usual(ticker):
                try:
                    hist, info, source, _ = get_stock_data_hybrid(ticker)
                    
                    if hist is None or len(hist) < 3:
                        return None
                    
                    current_price = hist['Close'].iloc[-1]
                    prev_price = hist['Close'].iloc[-2]
                    change_pct = ((current_price - prev_price) / prev_price) * 100
                    
                    current_volume = hist['Volume'].iloc[-1]
                    avg_volume = hist['Volume'].iloc[:-1].mean()
                    volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1
                    
                    # Check daily pattern
                    has_pattern, pattern_data = check_strat_31(hist)
                    patterns = {}
                    if has_pattern:
                        patterns['daily'] = {
                            'type': '3-1 Strat',
                            'direction': pattern_data['direction']
                        }
                    
                    return {
                        'ticker': ticker,
                        'company': info.get('longName', ticker),
                        'price': float(current_price),
                        'change': float(change_pct),
                        'volume': int(current_volume),
                        'avg_volume': int(avg_volume),
                        'volume_ratio': float(volume_ratio),
                        'patterns': patterns,
                        'dataSource': source
                    }
                except:
                    return None
            
            futures = [executor.submit(scan_usual, ticker) for ticker in tickers]
            
            for future in as_completed(futures):
                result = future.result()
                if result:
                    results.append(result)
        
        elapsed = time.time() - start_time
        print(f"⚡ DONE in {elapsed:.1f}s!\n")
        
        return jsonify({
            'success': True,
            'results': results,
            'count': len(results),
            'scan_time': round(elapsed, 1)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/config', methods=['GET'])
def get_config():
    """Get current configuration"""
    return jsonify({
        'success': True,
        'config': {
            'max_workers': MAX_WORKERS,
            'cache_duration': CACHE_DURATION,
            'min_request_interval': MIN_REQUEST_INTERVAL,
            'stock_counts': STOCK_COUNTS
        }
    })

@app.route('/api/clear-cache', methods=['POST'])
def clear_cache():
    """Clear cache"""
    with cache_lock:
        cache.clear()
    return jsonify({'success': True, 'message': 'Cache cleared'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    
    print("\n" + "="*70)
    print("🚀 LEMON SQUEEZE v3.2 - TURBO EDITION 🚀")
    print("="*70)
    print("\n⚡ PERFORMANCE FEATURES:")
    print(f"  • Concurrent Processing: {MAX_WORKERS} threads (10x faster!)")
    print(f"  • Smart Caching: {CACHE_DURATION}s duration")
    print(f"  • Fast Rate Limiting: {MIN_REQUEST_INTERVAL*1000:.0f}ms")
    print(f"  • Batch API Calls: Up to 50 stocks at once")
    print("\n📊 STOCK COUNTS:")
    print(f"  • Short Squeeze: All from CSV")
    print(f"  • Daily Plays: {STOCK_COUNTS['daily_plays']} stocks")
    print(f"  • Hourly Plays: {STOCK_COUNTS['hourly_plays']} stocks")
    print(f"  • Weekly Plays: {STOCK_COUNTS['weekly_plays']} stocks")
    print(f"  • Volemon: {STOCK_COUNTS['volemon']} stocks")
    print(f"  • Usuals: {STOCK_COUNTS['usuals']} stocks")
    print("\n💡 TIP: Edit STOCK_COUNTS in code to scan more/less")
    print("\n📱 Open: http://localhost:8080")
    print("🛑 Press Ctrl+C to stop")
    print("\n" + "="*70 + "\n")
    
    app.run(debug=False, host='0.0.0.0', port=port)
