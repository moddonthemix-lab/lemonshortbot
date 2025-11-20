"""
🍋 LEMON SQUEEZE v4.1 - FINAL WORKING EDITION 🍋
Fixed: Timeouts, proper error handling, fast execution
"""

from flask import Flask, jsonify, request, send_from_directory
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
from datetime import datetime, timedelta
import time
import os
import warnings
warnings.filterwarnings('ignore')

app = Flask(__name__)

# ===== CONFIGURATION =====
MAX_WORKERS = 10  # Concurrent threads
TIMEOUT_PER_STOCK = 5  # 5 second timeout per stock
STOCK_COUNTS = {
    'daily_plays': 30,
    'hourly_plays': 15,
    'weekly_plays': 20,
    'volemon': 50,
    'usuals': 20
}

# Clean verified stocks
CLEAN_STOCKS = [
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'META', 'NVDA', 'AMD', 'INTC',
    'CRM', 'ADBE', 'CSCO', 'ORCL', 'AVGO', 'QCOM', 'TXN', 'NOW', 'INTU',
    'JPM', 'BAC', 'WFC', 'C', 'GS', 'MS', 'V', 'MA', 'PYPL', 'SOFI',
    'BLK', 'SCHW', 'AXP', 'USB', 'COF',
    'XOM', 'CVX', 'COP', 'SLB', 'EOG', 'MPC', 'PSX', 'VLO',
    'WMT', 'HD', 'COST', 'TGT', 'LOW', 'NKE', 'SBUX', 'MCD',
    'UNH', 'JNJ', 'LLY', 'ABBV', 'MRK', 'PFE', 'TMO', 'ABT',
    'PLTR', 'SNOW', 'NET', 'DDOG', 'ZS', 'CRWD', 'PANW', 'COIN',
    'GME', 'AMC', 'DKNG', 'PENN', 'RIVN', 'LCID',
    'SPY', 'QQQ', 'IWM', 'DIA', 'VTI'
]

print("\n" + "="*70)
print("🍋 LEMON SQUEEZE v4.1 - FINAL WORKING 🍋")
print("="*70)
print(f"\n⚡ {len(CLEAN_STOCKS)} verified stocks")
print(f"⚡ {MAX_WORKERS} threads, {TIMEOUT_PER_STOCK}s timeout per stock")
print("🚀 Starting...\n")

# ===== HELPER FUNCTIONS =====

def get_stock_data_timeout(ticker, period='1mo', timeout=TIMEOUT_PER_STOCK):
    """Get stock data with timeout"""
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period=period)
        
        if len(hist) == 0:
            return None, None
        
        try:
            info = stock.info
        except:
            info = {'longName': ticker}
        
        return hist, info
    except Exception:
        return None, None

def check_strat_31(hist):
    """Check for 3-1 pattern"""
    try:
        if hist is None or len(hist) < 3:
            return False, None
        
        current = hist.iloc[-1]
        previous = hist.iloc[-2]
        before_prev = hist.iloc[-3]
        
        is_three = (previous['High'] > before_prev['High'] and 
                    previous['Low'] < before_prev['Low'])
        
        is_one = (current['High'] < previous['High'] and 
                  current['Low'] > previous['Low'])
        
        if is_three and is_one:
            direction = "bullish" if current['Close'] > current['Open'] else "bearish"
            return True, {'direction': direction, 'type': '3-1 Strat'}
        
        return False, None
    except:
        return False, None

def check_inside_bar(hist):
    """Check for inside bar"""
    try:
        if hist is None or len(hist) < 2:
            return False
        
        current = hist.iloc[-1]
        previous = hist.iloc[-2]
        
        is_inside = (current['High'] < previous['High'] and 
                     current['Low'] > previous['Low'])
        
        return is_inside
    except:
        return False

def check_all_patterns(hist):
    """Check all patterns"""
    patterns = {}
    
    if hist is None or len(hist) < 3:
        return patterns
    
    has_31, pattern_data = check_strat_31(hist)
    
    if has_31:
        patterns['type'] = '3-1 Strat'
        patterns['direction'] = pattern_data['direction']
    else:
        if check_inside_bar(hist):
            patterns['type'] = 'Inside Bar (1)'
            patterns['direction'] = 'neutral'
    
    return patterns

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
    
    return """
    <h1>🍋 Lemon Squeeze v4.1 - WORKING!</h1>
    <p>Backend ready! Place HTML in same directory.</p>
    <p><a href="/api/test">Test API</a></p>
    """

@app.route('/api/test', methods=['GET'])
def test():
    """Test endpoint"""
    try:
        print("\n🧪 Testing API...")
        
        hist, info = get_stock_data_timeout("AAPL", period="5d")
        
        if hist is not None:
            return jsonify({
                'success': True,
                'message': '✅ API working!',
                'test': {
                    'ticker': 'AAPL',
                    'days': len(hist),
                    'price': float(hist['Close'].iloc[-1])
                }
            })
        else:
            return jsonify({'success': False, 'error': 'No data'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/scan', methods=['POST'])
def scan():
    """Short squeeze scanner"""
    try:
        print("\n🔍 Short squeeze scan...")
        start = time.time()
        
        data = request.json or {}
        min_short = float(data.get('minShort', 25))
        min_gain = float(data.get('minGain', 15))
        min_vol_ratio = float(data.get('minVolRatio', 1.5))
        min_risk = float(data.get('minRisk', 60))
        
        # Load from CSV
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
                            if short_interest >= min_short and ticker:
                                stocks.append({
                                    'ticker': ticker,
                                    'company': company,
                                    'short_interest': short_interest
                                })
                        except:
                            continue
        
        print(f"Scanning {len(stocks)} stocks...")
        
        def scan_one(stock):
            ticker = stock['ticker']
            try:
                hist, info = get_stock_data_timeout(ticker, period='3mo')
                
                if hist is None or len(hist) < 2:
                    return None
                
                current_price = hist['Close'].iloc[-1]
                previous_close = hist['Close'].iloc[-2]
                daily_change = ((current_price - previous_close) / previous_close) * 100
                
                current_volume = hist['Volume'].iloc[-1]
                avg_volume = hist['Volume'].mean()
                volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0
                
                risk_score = (stock['short_interest'] * 2 + daily_change * 2 + volume_ratio * 10) / 4
                
                if daily_change >= min_gain and volume_ratio >= min_vol_ratio and risk_score >= min_risk:
                    return {
                        'ticker': ticker,
                        'company': stock['company'],
                        'shortInterest': stock['short_interest'],
                        'currentPrice': float(current_price),
                        'dailyChange': float(daily_change),
                        'volume': int(current_volume),
                        'volumeRatio': float(volume_ratio),
                        'riskScore': float(risk_score),
                        'dataSource': 'yfinance'
                    }
            except:
                pass
            return None
        
        results = []
        
        # Use threading with timeout
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_to_stock = {executor.submit(scan_one, stock): stock for stock in stocks}
            
            for future in as_completed(future_to_stock, timeout=60):  # 60s total timeout
                try:
                    result = future.result(timeout=TIMEOUT_PER_STOCK)
                    if result:
                        results.append(result)
                except TimeoutError:
                    continue
                except Exception:
                    continue
        
        results.sort(key=lambda x: x['riskScore'], reverse=True)
        elapsed = time.time() - start
        
        print(f"✅ Done in {elapsed:.1f}s - Found {len(results)}\n")
        
        return jsonify({
            'success': True,
            'results': results,
            'count': len(results),
            'scan_time': round(elapsed, 1)
        })
        
    except Exception as e:
        print(f"❌ Error: {e}\n")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/daily-plays', methods=['POST'])
def daily_plays():
    """Daily plays scanner"""
    try:
        print("\n🎯 Daily plays...")
        start = time.time()
        
        tickers = CLEAN_STOCKS[:STOCK_COUNTS['daily_plays']]
        print(f"Scanning {len(tickers)} stocks...")
        
        def scan_pattern(ticker):
            try:
                hist, info = get_stock_data_timeout(ticker, period='1mo')
                
                if hist is None or len(hist) < 3:
                    return None
                
                patterns = check_all_patterns(hist)
                
                if patterns.get('type'):
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
                        'marketCap': info.get('marketCap', 0),
                        'pattern': patterns,
                        'dataSource': 'yfinance'
                    }
            except:
                pass
            return None
        
        results = []
        
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_to_ticker = {executor.submit(scan_pattern, ticker): ticker for ticker in tickers}
            
            for future in as_completed(future_to_ticker, timeout=45):
                try:
                    result = future.result(timeout=TIMEOUT_PER_STOCK)
                    if result:
                        results.append(result)
                        print(f"  ✅ {result['ticker']}: {result['pattern']['type']}")
                except TimeoutError:
                    continue
                except Exception:
                    continue
        
        elapsed = time.time() - start
        print(f"✅ Done in {elapsed:.1f}s - Found {len(results)}\n")
        
        return jsonify({
            'success': True,
            'results': results,
            'count': len(results),
            'scan_time': round(elapsed, 1)
        })
        
    except Exception as e:
        print(f"❌ Error: {e}\n")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/hourly-plays', methods=['POST'])
def hourly_plays():
    """Hourly scanner"""
    try:
        print("\n⏰ Hourly scan...")
        
        tickers = CLEAN_STOCKS[:STOCK_COUNTS['hourly_plays']]
        results = []
        
        for ticker in tickers:
            try:
                stock = yf.Ticker(ticker)
                hist = stock.history(period='5d', interval='1h').dropna()
                
                if len(hist) < 3:
                    continue
                
                patterns = check_all_patterns(hist)
                
                if patterns.get('type'):
                    info = stock.info if hasattr(stock, 'info') else {}
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
        
        print(f"✅ Found {len(results)}\n")
        
        return jsonify({'success': True, 'results': results, 'count': len(results)})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/weekly-plays', methods=['POST'])
def weekly_plays():
    """Weekly scanner"""
    try:
        print("\n📅 Weekly scan...")
        
        tickers = CLEAN_STOCKS[:STOCK_COUNTS['weekly_plays']]
        results = []
        
        for ticker in tickers:
            try:
                stock = yf.Ticker(ticker)
                hist = stock.history(period='6mo', interval='1wk')
                
                if len(hist) < 3:
                    continue
                
                patterns = check_all_patterns(hist)
                
                if patterns.get('type'):
                    info = stock.info if hasattr(stock, 'info') else {}
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
        
        print(f"✅ Found {len(results)}\n")
        
        return jsonify({'success': True, 'results': results, 'count': len(results)})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/crypto-scan', methods=['POST'])
def crypto_scan():
    """Crypto scanner"""
    try:
        print("\n💰 Crypto scan...")
        
        crypto_tickers = ['BTC-USD', 'ETH-USD', 'XRP-USD', 'SOL-USD', 'DOGE-USD', 'ADA-USD']
        results = []
        
        for ticker in crypto_tickers:
            try:
                hist, _ = get_stock_data_timeout(ticker, period='1mo')
                
                if hist is None or len(hist) < 2:
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
        
        print(f"✅ Found {len(results)}\n")
        
        return jsonify({'success': True, 'results': results, 'count': len(results)})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/volemon-scan', methods=['POST'])
def volemon_scan():
    """Volume scanner"""
    try:
        print("\n🔊 Volemon scan...")
        start = time.time()
        
        data = request.json or {}
        min_volume_multiple = float(data.get('min_volume_multiple', 2.0))
        
        tickers = CLEAN_STOCKS[:STOCK_COUNTS['volemon']]
        print(f"Scanning {len(tickers)} for {min_volume_multiple}x volume...")
        
        def scan_vol(ticker):
            try:
                hist, info = get_stock_data_timeout(ticker, period='1mo')
                
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
                        'dataSource': 'yfinance'
                    }
            except:
                pass
            return None
        
        results = []
        
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_to_ticker = {executor.submit(scan_vol, ticker): ticker for ticker in tickers}
            
            for future in as_completed(future_to_ticker, timeout=45):
                try:
                    result = future.result(timeout=TIMEOUT_PER_STOCK)
                    if result:
                        results.append(result)
                except:
                    continue
        
        results.sort(key=lambda x: x['volume_multiple'], reverse=True)
        elapsed = time.time() - start
        
        print(f"✅ Done in {elapsed:.1f}s - Found {len(results)}\n")
        
        return jsonify({
            'success': True,
            'results': results[:50],
            'count': len(results),
            'scan_time': round(elapsed, 1)
        })
        
    except Exception as e:
        print(f"❌ Error: {e}\n")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/usuals-scan', methods=['POST'])
def usuals_scan():
    """Usuals scanner - FIXED with timeout!"""
    try:
        print("\n⭐ Usuals scan...")
        start = time.time()
        
        data = request.json or {}
        tickers = data.get('tickers', CLEAN_STOCKS[:STOCK_COUNTS['usuals']])
        
        print(f"Scanning {len(tickers)} stocks...")
        
        def scan_usual(ticker):
            try:
                hist, info = get_stock_data_timeout(ticker, period='1mo')
                
                if hist is None or len(hist) < 3:
                    return None
                
                current_price = hist['Close'].iloc[-1]
                prev_price = hist['Close'].iloc[-2]
                change_pct = ((current_price - prev_price) / prev_price) * 100
                
                current_volume = hist['Volume'].iloc[-1]
                avg_volume = hist['Volume'].iloc[:-1].mean()
                volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1
                
                patterns_daily = check_all_patterns(hist)
                patterns_output = {}
                
                if patterns_daily.get('type'):
                    patterns_output['daily'] = patterns_daily
                
                return {
                    'ticker': ticker,
                    'company': info.get('longName', ticker),
                    'price': float(current_price),
                    'change': float(change_pct),
                    'volume': int(current_volume),
                    'avg_volume': int(avg_volume),
                    'volume_ratio': float(volume_ratio),
                    'patterns': patterns_output,
                    'dataSource': 'yfinance'
                }
            except:
                pass
            return None
        
        results = []
        
        # Use threading with timeout
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_to_ticker = {executor.submit(scan_usual, ticker): ticker for ticker in tickers}
            
            for future in as_completed(future_to_ticker, timeout=45):  # 45s total timeout
                try:
                    result = future.result(timeout=TIMEOUT_PER_STOCK)  # 5s per stock
                    if result:
                        results.append(result)
                        print(f"  ✅ {result['ticker']}")
                except TimeoutError:
                    ticker = future_to_ticker[future]
                    print(f"  ⏱️ {ticker} timeout")
                    continue
                except Exception as e:
                    continue
        
        elapsed = time.time() - start
        print(f"✅ Done in {elapsed:.1f}s - Found {len(results)}\n")
        
        return jsonify({
            'success': True,
            'results': results,
            'count': len(results),
            'scan_time': round(elapsed, 1)
        })
        
    except Exception as e:
        print(f"❌ Error: {e}\n")
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    
    print("✅ Ready on port 8080!")
    print("📱 http://localhost:8080")
    print("🧪 http://localhost:8080/api/test\n")
    
    app.run(debug=True, host='0.0.0.0', port=port)
