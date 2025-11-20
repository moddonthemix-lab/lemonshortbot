"""
🍋 LEMON SQUEEZE v3.4 - OPTIMIZED EDITION 🍋
Fast + Complete Pattern Detection
- All original patterns (3-1 + inside bars)
- Configurable stock counts for speed
- Original accuracy maintained
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
import warnings
warnings.filterwarnings('ignore')

app = Flask(__name__)

# ===== SPEED CONTROL =====
# Adjust these to control speed vs coverage
STOCK_COUNTS = {
    'daily_plays': 30,      # Lower = faster (try 20-50)
    'hourly_plays': 15,     # Lower = faster (try 10-30)
    'weekly_plays': 20,     # Lower = faster (try 15-40)
    'volemon': 50,          # Lower = faster (try 30-100)
    'usuals': 20            # Your watchlist (10-30)
}

MAX_WORKERS = 10  # Threads (5=slower/stable, 15=faster/aggressive)

# ===== API CONFIG =====
TRADIER_API_KEY = "Yuvcbpb7jfPIKyyUf8FDNATV48Hc"
TRADIER_BASE_URL = "https://api.tradier.com/v1"
TRADIER_HEADERS = {
    "Authorization": f"Bearer {TRADIER_API_KEY}",
    "Accept": "application/json"
}

# Caching
CACHE_DURATION = 300
cache = {}
cache_lock = Lock()
last_request_time = {}
rate_limit_lock = Lock()

def rate_limit(key):
    """Rate limiting"""
    with rate_limit_lock:
        current_time = time.time()
        if key in last_request_time:
            time_since_last = current_time - last_request_time[key]
            if time_since_last < 0.05:
                time.sleep(0.05 - time_since_last)
        last_request_time[key] = time.time()

def get_cached(key):
    """Get from cache"""
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

def get_tradier_quotes_batch(tickers):
    """Batch get quotes"""
    try:
        url = f"{TRADIER_BASE_URL}/markets/quotes"
        symbols = ','.join(tickers[:50])
        response = requests.get(url, headers=TRADIER_HEADERS, params={"symbols": symbols}, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if 'quotes' in data and 'quote' in data['quotes']:
                quotes = data['quotes']['quote']
                if isinstance(quotes, dict):
                    return {quotes['symbol']: quotes}
                elif isinstance(quotes, list):
                    return {q['symbol']: q for q in quotes}
        return {}
    except:
        return {}

def get_stock_data_hybrid(ticker):
    """Hybrid data with cache"""
    cached = get_cached(f"stock_{ticker}")
    if cached:
        return cached
    
    data_source = "yfinance"
    
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
    
    info = {
        'longName': quote.get('description', ticker),
        'marketCap': 0,
        'floatShares': 0
    }
    
    result = (None, info, data_source, None)
    set_cache(f"stock_{ticker}", result)
    return result

def load_stock_data():
    """Load from CSV"""
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
    """Check for 3-1 pattern (ORIGINAL)"""
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

def check_inside_bar(hist):
    """Check for inside bar (RESTORED!)"""
    if hist is None or len(hist) < 2:
        return False
    
    current = hist.iloc[-1]
    previous = hist.iloc[-2]
    
    is_inside = (current['High'] < previous['High'] and 
                 current['Low'] > previous['Low'])
    
    return is_inside

def check_all_patterns(hist):
    """Check ALL patterns like original (COMPLETE!)"""
    patterns = {}
    
    if hist is None or len(hist) < 3:
        return patterns
    
    # Check 3-1 pattern first
    has_31, pattern_data = check_strat_31(hist)
    
    if has_31:
        patterns['type'] = '3-1 Strat'
        patterns['direction'] = pattern_data['direction']
        patterns['data'] = pattern_data
    else:
        # Check for inside bar
        if check_inside_bar(hist):
            patterns['type'] = 'Inside Bar (1)'
            patterns['direction'] = 'neutral'
        else:
            patterns['type'] = None
            patterns['direction'] = None
    
    return patterns

# ===== STOCK LISTS (BALANCED) =====
TOP_STOCKS = [
    # Tech
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'META', 'NVDA', 'AMD', 'INTC', 'CRM',
    'ADBE', 'CSCO', 'ORCL', 'AVGO', 'QCOM', 'TXN', 'NOW', 'INTU', 'AMAT', 'MU',
    'PLTR', 'SNOW', 'NET', 'DDOG', 'ZS', 'CRWD', 'PANW', 'COIN', 'BLOCK', 'SHOP',
    # Finance
    'JPM', 'BAC', 'WFC', 'C', 'GS', 'MS', 'V', 'MA', 'PYPL', 'SOFI',
    'AFRM', 'UPST', 'LC', 'NU', 'HOOD', 'BLK', 'SCHW', 'AXP', 'USB', 'COF',
    # Auto/EV
    'F', 'GM', 'NIO', 'XPEV', 'LI', 'RIVN', 'LCID', 'FSR', 'WKHS',
    # Energy
    'XOM', 'CVX', 'COP', 'SLB', 'EOG', 'MPC', 'PSX', 'VLO', 'OXY', 'FANG',
    # Consumer
    'WMT', 'HD', 'COST', 'TGT', 'LOW', 'NKE', 'LULU', 'SBUX', 'MCD', 'CMG',
    # Healthcare
    'UNH', 'JNJ', 'LLY', 'ABBV', 'MRK', 'PFE', 'TMO', 'ABT', 'MRNA', 'BNTX',
    # Meme/Popular
    'GME', 'AMC', 'BBBY', 'BB', 'DKNG', 'PENN', 'TLRY', 'SNDL', 'SPCE', 'NKLA',
    # ETFs
    'SPY', 'QQQ', 'IWM', 'DIA', 'VTI'
]

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
    
    return "<h1>🍋 Lemon Squeeze v3.4 - Optimized</h1><p>Place HTML in same directory</p>"

@app.route('/api/scan', methods=['POST'])
def scan():
    """Squeeze scanner"""
    try:
        data = request.json
        min_short = float(data.get('minShort', 25))
        min_gain = float(data.get('minGain', 15))
        min_vol_ratio = float(data.get('minVolRatio', 1.5))
        min_risk = float(data.get('minRisk', 60))
        
        stocks = load_stock_data()
        results = []
        
        print(f"\n🔍 Scanning {len(stocks)} stocks with {MAX_WORKERS} threads...")
        start_time = time.time()
        
        def scan_one(stock):
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
                    stock['short_interest'], daily_change, volume_ratio,
                    days_to_cover, float_shares
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
            except:
                return None
        
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = [executor.submit(scan_one, stock) for stock in stocks]
            
            for future in as_completed(futures):
                result = future.result()
                if result and (
                    result['shortInterest'] >= min_short and 
                    result['dailyChange'] >= min_gain and 
                    result['volumeRatio'] >= min_vol_ratio and
                    result['riskScore'] >= min_risk
                ):
                    results.append(result)
        
        results.sort(key=lambda x: x['riskScore'], reverse=True)
        elapsed = time.time() - start_time
        
        print(f"⚡ Done in {elapsed:.1f}s! Found {len(results)} candidates\n")
        
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
    """Daily plays with FULL pattern detection"""
    try:
        tickers = TOP_STOCKS[:STOCK_COUNTS['daily_plays']]
        
        print(f"\n🎯 Daily Plays: {len(tickers)} stocks...")
        start_time = time.time()
        results = []
        
        def scan_pattern(ticker):
            try:
                hist, info, source, _ = get_stock_data_hybrid(ticker)
                
                if hist is None or len(hist) < 3:
                    return None
                
                # Check ALL patterns (3-1 AND inside bars!)
                patterns = check_all_patterns(hist)
                
                if patterns.get('type'):  # Has any pattern
                    current_price = hist['Close'].iloc[-1]
                    previous_close = hist['Close'].iloc[-2]
                    daily_change = ((current_price - previous_close) / previous_close) * 100
                    
                    return {
                        'ticker': ticker,
                        'company': info.get('longName', ticker),
                        'currentPrice': float(current_price),
                        'dailyChange': float(daily_change),
                        'volume': int(hist['Volume'].iloc[-1]),
                        'avgVolume': int(hist['Volume'].mean()),
                        'marketCap': int(info.get('marketCap', 0)),
                        'pattern': patterns,
                        'dataSource': source
                    }
            except:
                return None
        
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = [executor.submit(scan_pattern, ticker) for ticker in tickers]
            
            for future in as_completed(futures):
                result = future.result()
                if result:
                    results.append(result)
        
        elapsed = time.time() - start_time
        print(f"⚡ Done in {elapsed:.1f}s! Found {len(results)} patterns\n")
        
        return jsonify({
            'success': True,
            'results': results,
            'scan_time': round(elapsed, 1)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/hourly-plays', methods=['POST'])
def hourly_plays():
    """Hourly with full patterns"""
    try:
        tickers = TOP_STOCKS[:STOCK_COUNTS['hourly_plays']]
        
        print(f"\n⏰ Hourly: {len(tickers)} stocks...")
        results = []
        
        for ticker in tickers:
            try:
                stock_data = yf.Ticker(ticker)
                hist = stock_data.history(period='5d', interval='1h').dropna()
                
                if len(hist) < 3:
                    continue
                
                patterns = check_all_patterns(hist)
                
                if patterns.get('type'):
                    info = stock_data.info
                    results.append({
                        'ticker': ticker,
                        'company': info.get('longName', ticker),
                        'currentPrice': float(hist['Close'].iloc[-1]),
                        'volume': int(hist['Volume'].iloc[-1]),
                        'pattern': patterns,
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
    """Weekly with full patterns"""
    try:
        tickers = TOP_STOCKS[:STOCK_COUNTS['weekly_plays']]
        
        print(f"\n📅 Weekly: {len(tickers)} stocks...")
        results = []
        
        for ticker in tickers:
            try:
                stock_data = yf.Ticker(ticker)
                hist = stock_data.history(period='6mo', interval='1wk')
                
                if len(hist) < 3:
                    continue
                
                patterns = check_all_patterns(hist)
                
                if patterns.get('type'):
                    info = stock_data.info
                    results.append({
                        'ticker': ticker,
                        'company': info.get('longName', ticker),
                        'currentPrice': float(hist['Close'].iloc[-1]),
                        'volume': int(hist['Volume'].iloc[-1]),
                        'pattern': patterns,
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
    """Crypto scanner"""
    try:
        crypto_tickers = ['BTC-USD', 'ETH-USD', 'XRP-USD', 'SOL-USD', 'DOGE-USD', 'ADA-USD']
        results = []
        
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
        
        return jsonify({'success': True, 'results': results})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/volemon-scan', methods=['POST'])
def volemon_scan():
    """Volume scanner"""
    try:
        data = request.json
        min_volume_multiple = data.get('min_volume_multiple', 2.0)
        
        tickers = TOP_STOCKS[:STOCK_COUNTS['volemon']]
        
        print(f"\n🔊 Volemon: {len(tickers)} stocks ({min_volume_multiple}x)...")
        start_time = time.time()
        results = []
        
        def scan_vol(ticker):
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
        
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = [executor.submit(scan_vol, ticker) for ticker in tickers]
            
            for future in as_completed(futures):
                result = future.result()
                if result:
                    results.append(result)
        
        results.sort(key=lambda x: x['volume_multiple'], reverse=True)
        elapsed = time.time() - start_time
        
        print(f"⚡ Done in {elapsed:.1f}s! Found {len(results)}\n")
        
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
    """Usuals with full patterns"""
    try:
        data = request.json
        tickers = data.get('tickers', TOP_STOCKS[:STOCK_COUNTS['usuals']])
        
        print(f"\n⭐ Usuals: {len(tickers)} stocks...")
        start_time = time.time()
        results = []
        
        def scan_usual(ticker):
            try:
                hist, info, source, stock_data = get_stock_data_hybrid(ticker)
                
                if hist is None or len(hist) < 3:
                    return None
                
                current_price = hist['Close'].iloc[-1]
                prev_price = hist['Close'].iloc[-2]
                change_pct = ((current_price - prev_price) / prev_price) * 100
                
                current_volume = hist['Volume'].iloc[-1]
                avg_volume = hist['Volume'].iloc[:-1].mean()
                volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1
                
                # Check ALL patterns
                patterns_daily = check_all_patterns(hist)
                patterns_output = {}
                
                if patterns_daily.get('type'):
                    patterns_output['daily'] = patterns_daily
                
                # Try weekly too if we have stock_data
                if stock_data:
                    try:
                        hist_weekly = stock_data.history(period='6mo', interval='1wk')
                        if len(hist_weekly) >= 3:
                            patterns_weekly = check_all_patterns(hist_weekly)
                            if patterns_weekly.get('type'):
                                patterns_output['weekly'] = patterns_weekly
                    except:
                        pass
                
                return {
                    'ticker': ticker,
                    'company': info.get('longName', ticker),
                    'price': float(current_price),
                    'change': float(change_pct),
                    'volume': int(current_volume),
                    'avg_volume': int(avg_volume),
                    'volume_ratio': float(volume_ratio),
                    'patterns': patterns_output,
                    'dataSource': source
                }
            except:
                return None
        
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = [executor.submit(scan_usual, ticker) for ticker in tickers]
            
            for future in as_completed(futures):
                result = future.result()
                if result:
                    results.append(result)
        
        elapsed = time.time() - start_time
        print(f"⚡ Done in {elapsed:.1f}s!\n")
        
        return jsonify({
            'success': True,
            'results': results,
            'count': len(results),
            'scan_time': round(elapsed, 1)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    
    print("\n" + "="*70)
    print("🍋 LEMON SQUEEZE v3.4 - OPTIMIZED EDITION 🍋")
    print("="*70)
    print("\n⚙️  SPEED CONTROLS (edit in code):")
    print(f"  • Threads: {MAX_WORKERS} (5=stable, 15=fast)")
    print(f"  • Daily Plays: {STOCK_COUNTS['daily_plays']} stocks")
    print(f"  • Hourly Plays: {STOCK_COUNTS['hourly_plays']} stocks")
    print(f"  • Weekly Plays: {STOCK_COUNTS['weekly_plays']} stocks")
    print(f"  • Volemon: {STOCK_COUNTS['volemon']} stocks")
    print(f"  • Usuals: {STOCK_COUNTS['usuals']} stocks")
    print("\n✅ PATTERN DETECTION:")
    print("  • 3-1 Strat patterns ✓")
    print("  • Inside bars (1) ✓")
    print("  • All timeframes ✓")
    print("\n💡 TIP: Lower stock counts = faster scans!")
    print("     Edit STOCK_COUNTS at top of file")
    print("\n📱 Open: http://localhost:8080")
    print("🛑 Press Ctrl+C to stop")
    print("\n" + "="*70 + "\n")
    
    app.run(debug=False, host='0.0.0.0', port=port)
