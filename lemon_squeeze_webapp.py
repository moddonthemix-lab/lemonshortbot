"""
🍋 LEMON SQUEEZE v3.3 - MEGA EDITION 🍋
MAXIMUM COVERAGE with expanded stock lists!
- 100+ daily plays
- 200+ volume scans
- All major indices and sectors
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

app = Flask(__name__)

# ===== CONFIGURATION =====
TRADIER_API_KEY = "Yuvcbpb7jfPIKyyUf8FDNATV48Hc"
TRADIER_BASE_URL = "https://api.tradier.com/v1"
TRADIER_HEADERS = {
    "Authorization": f"Bearer {TRADIER_API_KEY}",
    "Accept": "application/json"
}

# Performance settings
MAX_WORKERS = 15  # More threads for more stocks!
CACHE_DURATION = 300  # 5 minutes
MIN_REQUEST_INTERVAL = 0.05  # 50ms

# ===== MEGA STOCK LISTS =====

# MEGA Tech Stocks (50)
TECH_STOCKS = [
    'AAPL', 'MSFT', 'GOOGL', 'GOOG', 'AMZN', 'META', 'NVDA', 'AMD', 'INTC', 'TSM',
    'AVGO', 'ORCL', 'CRM', 'ADBE', 'CSCO', 'ACN', 'IBM', 'QCOM', 'TXN', 'NOW',
    'INTU', 'AMAT', 'MU', 'LRCX', 'KLAC', 'SNPS', 'CDNS', 'NXPI', 'MRVL', 'FTNT',
    'PANW', 'CRWD', 'PLTR', 'SNOW', 'NET', 'DDOG', 'ZS', 'OKTA', 'TEAM', 'HUBS',
    'TWLO', 'ZM', 'DOCU', 'SHOP', 'BLOCK', 'COIN', 'RBLX', 'U', 'ROKU', 'PINS'
]

# MEGA Finance (40)
FINANCE_STOCKS = [
    'JPM', 'BAC', 'WFC', 'C', 'GS', 'MS', 'BLK', 'SCHW', 'AXP', 'USB',
    'PNC', 'TFC', 'COF', 'BK', 'STT', 'NTRS', 'CFG', 'KEY', 'RF', 'FITB',
    'HBAN', 'CMA', 'ZION', 'EWBC', 'MTB', 'FRC', 'WAL', 'SIVB', 'SBNY', 'PACW',
    'V', 'MA', 'PYPL', 'BLOCK', 'SOFI', 'AFRM', 'UPST', 'LC', 'NU', 'HOOD'
]

# MEGA EVs & Auto (30)
AUTO_EV_STOCKS = [
    'TSLA', 'F', 'GM', 'TM', 'HMC', 'STLA', 'NIO', 'XPEV', 'LI', 'RIVN',
    'LCID', 'FSR', 'RIDE', 'WKHS', 'GOEV', 'NKLA', 'HYMTF', 'VWAGY', 'BMWYY', 'POAHY',
    'LEA', 'APTV', 'BWA', 'ALV', 'ADNT', 'VC', 'LAZR', 'VLDR', 'LIDR', 'OUST'
]

# MEGA Energy (35)
ENERGY_STOCKS = [
    'XOM', 'CVX', 'COP', 'SLB', 'EOG', 'MPC', 'PSX', 'VLO', 'OXY', 'DVN',
    'FANG', 'HAL', 'BKR', 'WMB', 'KMI', 'OKE', 'LNG', 'TRGP', 'EPD', 'ET',
    'MRO', 'APA', 'CTRA', 'HES', 'PXD', 'CLR', 'MTDR', 'SM', 'RRC', 'AR',
    'NEE', 'DUK', 'SO', 'D', 'EXC'
]

# MEGA Healthcare & Pharma (40)
HEALTHCARE_STOCKS = [
    'UNH', 'JNJ', 'LLY', 'ABBV', 'MRK', 'TMO', 'ABT', 'DHR', 'PFE', 'BMY',
    'AMGN', 'GILD', 'CVS', 'CI', 'ISRG', 'MDT', 'REGN', 'VRTX', 'BSX', 'SYK',
    'ZTS', 'ELV', 'HCA', 'A', 'BDX', 'MCK', 'CNC', 'IDXX', 'IQV', 'RMD',
    'MRNA', 'BNTX', 'NVAX', 'CRSP', 'EDIT', 'NTLA', 'BEAM', 'EXAS', 'ILMN', 'TWST'
]

# MEGA Consumer & Retail (40)
CONSUMER_STOCKS = [
    'AMZN', 'WMT', 'HD', 'COST', 'TGT', 'LOW', 'TJX', 'ROST', 'DG', 'DLTR',
    'NKE', 'LULU', 'SBUX', 'MCD', 'CMG', 'YUM', 'DPZ', 'QSR', 'WEN', 'JACK',
    'DIS', 'NFLX', 'CMCSA', 'PARA', 'WBD', 'DISCA', 'FOXA', 'LYV', 'MSGS', 'SPGI',
    'PG', 'KO', 'PEP', 'PM', 'MO', 'CL', 'EL', 'CLX', 'CHD', 'KMB'
]

# MEGA Industrials (35)
INDUSTRIAL_STOCKS = [
    'CAT', 'DE', 'BA', 'HON', 'UPS', 'UNP', 'RTX', 'LMT', 'GD', 'NOC',
    'GE', 'MMM', 'EMR', 'ETN', 'ITW', 'CMI', 'PH', 'ROK', 'DOV', 'FTV',
    'IR', 'CARR', 'OTIS', 'PCAR', 'NSC', 'CSX', 'FDX', 'DAL', 'UAL', 'AAL',
    'LUV', 'JBLU', 'ALK', 'HA', 'SAVE'
]

# MEGA Crypto Related (25)
CRYPTO_STOCKS = [
    'COIN', 'MARA', 'RIOT', 'CLSK', 'HUT', 'BITF', 'CIFR', 'BTBT', 'CAN', 'HIVE',
    'MSTR', 'BLOCK', 'PYPL', 'HOOD', 'SOFI', 'AFRM', 'NU', 'UPST', 'LC', 'LMND',
    'SI', 'OPEN', 'RDFN', 'Z', 'COMP'
]

# MEGA Meme/High Short (40)
MEME_STOCKS = [
    'GME', 'AMC', 'BBBY', 'BB', 'NOK', 'WISH', 'CLOV', 'WKHS', 'RIDE', 'SPCE',
    'PLTR', 'SOFI', 'SKLZ', 'DKNG', 'PENN', 'RSI', 'VICI', 'MGM', 'CZR', 'LVS',
    'WYNN', 'BYD', 'RCL', 'CCL', 'NCLH', 'AAL', 'UAL', 'DAL', 'JBLU', 'ALK',
    'SAVE', 'HA', 'PLUG', 'FCEL', 'BLDP', 'BE', 'CLNE', 'BLNK', 'CHPT', 'EVGO'
]

# ETFs & Indices (15)
ETF_STOCKS = [
    'SPY', 'QQQ', 'IWM', 'DIA', 'VTI', 'VOO', 'VEA', 'VWO', 'EEM', 'EFA',
    'GLD', 'SLV', 'USO', 'UNG', 'TLT'
]

# Small Cap Momentum (50)
SMALL_CAP_STOCKS = [
    'DKNG', 'PENN', 'TLRY', 'CGC', 'SNDL', 'ACB', 'HEXO', 'APHA', 'CRON', 'OGI',
    'PTON', 'BYND', 'SPCE', 'NKLA', 'RIDE', 'WKHS', 'HYLN', 'BLNK', 'CHPT', 'EVGO',
    'SKLZ', 'DKNG', 'FUBO', 'VIAC', 'DISCA', 'WISH', 'CLOV', 'BGFV', 'BBIG', 'PROG',
    'ATER', 'CEI', 'IRNT', 'OPAD', 'LIDR', 'VLDR', 'LAZR', 'OUST', 'AEVA', 'INVZ',
    'MULN', 'CYCN', 'NILE', 'IMPP', 'MARPS', 'GFAI', 'RGTI', 'DWAC', 'PHUN', 'MARK'
]

# Combined MEGA list for daily plays
DAILY_PLAYS_MEGA = (
    TECH_STOCKS[:30] + 
    FINANCE_STOCKS[:20] + 
    AUTO_EV_STOCKS[:15] + 
    ENERGY_STOCKS[:15] +
    CONSUMER_STOCKS[:20]
)  # 100 stocks!

# Combined MEGA list for volume scans
VOLEMON_MEGA = (
    TECH_STOCKS[:40] +
    FINANCE_STOCKS[:30] +
    AUTO_EV_STOCKS[:20] +
    ENERGY_STOCKS[:20] +
    HEALTHCARE_STOCKS[:30] +
    CONSUMER_STOCKS[:30] +
    INDUSTRIAL_STOCKS[:20] +
    CRYPTO_STOCKS[:20] +
    MEME_STOCKS[:30] +
    SMALL_CAP_STOCKS[:30]
)  # 270 stocks!

# Cache & locks
cache = {}
cache_lock = Lock()
rate_limit_lock = Lock()
last_request_time = {}

# ===== HELPER FUNCTIONS =====
def rate_limit(key):
    """Fast rate limiting"""
    with rate_limit_lock:
        current_time = time.time()
        if key in last_request_time:
            time_since_last = current_time - last_request_time[key]
            if time_since_last < MIN_REQUEST_INTERVAL:
                time.sleep(MIN_REQUEST_INTERVAL - time_since_last)
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
        rate_limit('tradier_batch')
        url = f"{TRADIER_BASE_URL}/markets/quotes"
        symbols = ','.join(tickers[:50])
        params = {"symbols": symbols}
        response = requests.get(url, headers=TRADIER_HEADERS, params=params, timeout=10)
        
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
        # Suppress yfinance warnings
        import warnings
        warnings.filterwarnings('ignore')
        
        stock_data = yf.Ticker(ticker)
        hist = stock_data.history(period='3mo')
        
        if len(hist) > 0:
            info = stock_data.info
            result = (hist, info, data_source, stock_data)
            set_cache(f"stock_{ticker}", result)
            return result
    except Exception:
        pass  # Silently fail and try Tradier
    
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
    """Check 3-1 pattern"""
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

# ===== SCANNER FUNCTIONS =====
def scan_stock_squeeze(stock):
    """Scan for squeeze"""
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
        # Silently skip problematic tickers
        return None

def scan_stock_pattern(ticker):
    """Scan for pattern"""
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

def scan_stock_volume(ticker, min_multiple):
    """Scan for volume"""
    try:
        hist, info, source, _ = get_stock_data_hybrid(ticker)
        
        if hist is None or len(hist) < 2:
            return None
        
        current_volume = hist['Volume'].iloc[-1]
        avg_volume = hist['Volume'].iloc[:-1].mean()
        
        if avg_volume == 0:
            return None
        
        volume_multiple = current_volume / avg_volume
        
        if volume_multiple >= min_multiple:
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
    
    return """<h1>🍋 Lemon Squeeze v3.3 - MEGA</h1>
    <p>Backend running! Maximum stock coverage!</p>"""

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
        
        print(f"\n🚀 MEGA SCAN: {len(stocks)} stocks with {MAX_WORKERS} threads...")
        start_time = time.time()
        
        results = []
        
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = [executor.submit(scan_stock_squeeze, stock) for stock in stocks]
            
            for future in as_completed(futures):
                result = future.result()
                if result:
                    if (result['shortInterest'] >= min_short and 
                        result['dailyChange'] >= min_gain and 
                        result['volumeRatio'] >= min_vol_ratio and
                        result['riskScore'] >= min_risk):
                        results.append(result)
        
        results.sort(key=lambda x: x['riskScore'], reverse=True)
        
        elapsed = time.time() - start_time
        print(f"\n⚡ DONE in {elapsed:.1f}s! Found {len(results)} candidates\n")
        
        return jsonify({
            'success': True,
            'results': results,
            'count': len(results),
            'scan_time': round(elapsed, 1),
            'stocks_scanned': len(stocks)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/daily-plays', methods=['POST'])
def daily_plays():
    """MEGA Daily plays - 100 stocks!"""
    try:
        tickers = DAILY_PLAYS_MEGA  # 100 stocks!
        
        print(f"\n🎯 MEGA Daily: {len(tickers)} stocks...")
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
            'scan_time': round(elapsed, 1),
            'stocks_scanned': len(tickers)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/hourly-plays', methods=['POST'])
def hourly_plays():
    """Hourly plays - Top 30"""
    try:
        tickers = TECH_STOCKS[:30]
        
        print(f"\n⏰ Hourly: {len(tickers)} stocks...")
        
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
    """Weekly plays - Top 40"""
    try:
        tickers = (TECH_STOCKS[:20] + FINANCE_STOCKS[:20])
        
        print(f"\n📅 Weekly: {len(tickers)} stocks...")
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
    """Crypto scanner"""
    try:
        crypto_tickers = ['BTC-USD', 'ETH-USD', 'XRP-USD', 'SOL-USD', 'DOGE-USD', 'ADA-USD', 'MATIC-USD', 'DOT-USD']
        results = []
        
        print(f"\n💰 Crypto...")
        
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
    """MEGA Volume - 270 stocks!"""
    try:
        data = request.json
        min_volume_multiple = data.get('min_volume_multiple', 2.0)
        
        tickers = VOLEMON_MEGA  # 270 stocks!
        
        print(f"\n🔊 MEGA Volemon: {len(tickers)} stocks ({min_volume_multiple}x)...")
        start_time = time.time()
        
        results = []
        
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = [executor.submit(scan_stock_volume, ticker, min_volume_multiple) for ticker in tickers]
            
            for future in as_completed(futures):
                result = future.result()
                if result:
                    results.append(result)
        
        results.sort(key=lambda x: x['volume_multiple'], reverse=True)
        
        elapsed = time.time() - start_time
        print(f"⚡ DONE in {elapsed:.1f}s! Found {len(results)} stocks\n")
        
        return jsonify({
            'success': True,
            'results': results[:100],  # Top 100
            'count': len(results),
            'scan_time': round(elapsed, 1),
            'stocks_scanned': len(tickers)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/usuals-scan', methods=['POST'])
def usuals_scan():
    """Usuals scanner"""
    try:
        data = request.json
        tickers = data.get('tickers', (TECH_STOCKS[:15] + FINANCE_STOCKS[:10] + AUTO_EV_STOCKS[:5]))
        
        print(f"\n⭐ Usuals: {len(tickers)} stocks...")
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

@app.route('/api/stock-lists', methods=['GET'])
def get_stock_lists():
    """Get all stock lists"""
    return jsonify({
        'success': True,
        'lists': {
            'tech': TECH_STOCKS,
            'finance': FINANCE_STOCKS,
            'auto_ev': AUTO_EV_STOCKS,
            'energy': ENERGY_STOCKS,
            'healthcare': HEALTHCARE_STOCKS,
            'consumer': CONSUMER_STOCKS,
            'industrial': INDUSTRIAL_STOCKS,
            'crypto': CRYPTO_STOCKS,
            'meme': MEME_STOCKS,
            'small_cap': SMALL_CAP_STOCKS,
            'etf': ETF_STOCKS
        },
        'counts': {
            'tech': len(TECH_STOCKS),
            'finance': len(FINANCE_STOCKS),
            'auto_ev': len(AUTO_EV_STOCKS),
            'energy': len(ENERGY_STOCKS),
            'healthcare': len(HEALTHCARE_STOCKS),
            'consumer': len(CONSUMER_STOCKS),
            'industrial': len(INDUSTRIAL_STOCKS),
            'crypto': len(CRYPTO_STOCKS),
            'meme': len(MEME_STOCKS),
            'small_cap': len(SMALL_CAP_STOCKS),
            'daily_plays_mega': len(DAILY_PLAYS_MEGA),
            'volemon_mega': len(VOLEMON_MEGA)
        }
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    
    print("\n" + "="*80)
    print("🔥 LEMON SQUEEZE v3.3 - MEGA EDITION 🔥")
    print("="*80)
    print("\n📊 MEGA STOCK COVERAGE:")
    print(f"  • Tech: {len(TECH_STOCKS)} stocks")
    print(f"  • Finance: {len(FINANCE_STOCKS)} stocks")
    print(f"  • Auto/EV: {len(AUTO_EV_STOCKS)} stocks")
    print(f"  • Energy: {len(ENERGY_STOCKS)} stocks")
    print(f"  • Healthcare: {len(HEALTHCARE_STOCKS)} stocks")
    print(f"  • Consumer: {len(CONSUMER_STOCKS)} stocks")
    print(f"  • Industrial: {len(INDUSTRIAL_STOCKS)} stocks")
    print(f"  • Crypto Related: {len(CRYPTO_STOCKS)} stocks")
    print(f"  • Meme/High Short: {len(MEME_STOCKS)} stocks")
    print(f"  • Small Cap: {len(SMALL_CAP_STOCKS)} stocks")
    print("\n🎯 SCANNER COVERAGE:")
    print(f"  • Daily Plays: {len(DAILY_PLAYS_MEGA)} stocks (100!)")
    print(f"  • Volemon: {len(VOLEMON_MEGA)} stocks (270!)")
    print(f"  • Short Squeeze: All from CSV")
    print("\n⚡ PERFORMANCE:")
    print(f"  • {MAX_WORKERS} concurrent threads")
    print(f"  • 5-minute caching")
    print(f"  • Batch API calls")
    print("\n📱 Open: http://localhost:8080")
    print("🛑 Press Ctrl+C to stop")
    print("\n" + "="*80 + "\n")
    
    app.run(debug=False, host='0.0.0.0', port=port)
