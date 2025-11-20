"""
🍋 LEMON SQUEEZE v4.0 - ULTIMATE HYBRID 🍋
Best of both worlds:
- yfinance PRIMARY (pattern detection, historical)
- Tradier BACKUP (properly implemented, real-time quotes)
"""

from flask import Flask, jsonify, request, send_from_directory
import yfinance as yf
import requests
from datetime import datetime, timedelta
import time
import os
import warnings
warnings.filterwarnings('ignore')

app = Flask(__name__)

# ===== CONFIGURATION =====
TRADIER_API_KEY = "Yuvcbpb7jfPIKyyUf8FDNATV48Hc"
TRADIER_SANDBOX = False  # Set to True if using sandbox

# Use production or sandbox
if TRADIER_SANDBOX:
    TRADIER_BASE_URL = "https://sandbox.tradier.com/v1"
else:
    TRADIER_BASE_URL = "https://api.tradier.com/v1"

TRADIER_HEADERS = {
    "Authorization": f"Bearer {TRADIER_API_KEY}",
    "Accept": "application/json"
}

# Stock counts
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
print("🍋 LEMON SQUEEZE v4.0 - ULTIMATE HYBRID 🍋")
print("="*70)
print(f"\n📊 {len(CLEAN_STOCKS)} verified stocks")
print("✅ yfinance PRIMARY (pattern detection)")
print("🔄 Tradier BACKUP (real-time quotes)")
print("🚀 Starting...\n")

# ===== TRADIER API (PROPERLY IMPLEMENTED) =====

def get_tradier_quotes(symbols):
    """
    Get real-time quotes from Tradier API (properly implemented)
    Docs: https://docs.tradier.com/reference/brokerage-api-markets-get-quotes
    """
    try:
        # Tradier accepts comma-separated symbols
        if isinstance(symbols, list):
            symbols_str = ','.join(symbols)
        else:
            symbols_str = symbols
        
        url = f"{TRADIER_BASE_URL}/markets/quotes"
        params = {
            'symbols': symbols_str,
            'greeks': 'false'  # We don't need options greeks
        }
        
        response = requests.get(
            url, 
            params=params,
            headers=TRADIER_HEADERS,
            timeout=10
        )
        
        # Check status
        if response.status_code != 200:
            print(f"  Tradier API error: {response.status_code}")
            return None
        
        data = response.json()
        
        # Tradier returns quotes in 'quotes' > 'quote'
        if 'quotes' not in data or 'quote' not in data['quotes']:
            return None
        
        quotes = data['quotes']['quote']
        
        # Handle single vs multiple quotes
        if isinstance(quotes, dict):
            # Single quote
            return {quotes['symbol']: quotes}
        elif isinstance(quotes, list):
            # Multiple quotes
            return {q['symbol']: q for q in quotes}
        
        return None
        
    except Exception as e:
        print(f"  Tradier error: {e}")
        return None

def get_tradier_realtime_price(ticker):
    """Get real-time price for a single ticker from Tradier"""
    quotes = get_tradier_quotes([ticker])
    
    if quotes and ticker in quotes:
        quote = quotes[ticker]
        return {
            'price': quote.get('last', 0),
            'change': quote.get('change', 0),
            'change_percentage': quote.get('change_percentage', 0),
            'volume': quote.get('volume', 0),
            'high': quote.get('high', 0),
            'low': quote.get('low', 0),
            'open': quote.get('open', 0),
            'close': quote.get('close', 0),
            'source': 'tradier'
        }
    
    return None

# ===== YFINANCE (PRIMARY) =====

def get_stock_data(ticker, period='1mo'):
    """Get stock data - yfinance PRIMARY"""
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period=period)
        
        if len(hist) == 0:
            return None, None, 'failed'
        
        try:
            info = stock.info
        except:
            info = {'longName': ticker}
        
        return hist, info, 'yfinance'
    except Exception as e:
        return None, None, 'failed'

# ===== PATTERN DETECTION =====

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
    <h1>🍋 Lemon Squeeze v4.0 - Ultimate Hybrid</h1>
    <p>yfinance PRIMARY + Tradier BACKUP</p>
    <p><a href="/api/test">Test yfinance</a> | <a href="/api/test-tradier">Test Tradier</a></p>
    """

@app.route('/api/test', methods=['GET'])
def test():
    """Test yfinance"""
    try:
        hist, info, source = get_stock_data("AAPL", period="5d")
        
        if hist is not None:
            return jsonify({
                'success': True,
                'message': '✅ yfinance working!',
                'test': {
                    'ticker': 'AAPL',
                    'days': len(hist),
                    'price': float(hist['Close'].iloc[-1]),
                    'source': source
                }
            })
        else:
            return jsonify({'success': False, 'error': 'No data'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/test-tradier', methods=['GET'])
def test_tradier():
    """Test Tradier API"""
    try:
        print("\n🧪 Testing Tradier API...")
        
        # Test single quote
        quote = get_tradier_realtime_price('AAPL')
        
        if quote:
            return jsonify({
                'success': True,
                'message': '✅ Tradier API working!',
                'test': {
                    'ticker': 'AAPL',
                    'price': quote['price'],
                    'change': quote['change'],
                    'volume': quote['volume'],
                    'source': 'tradier'
                }
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Tradier returned no data',
                'note': 'Check API key and account status'
            })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'note': 'Make sure API key is correct'
        })

@app.route('/api/scan', methods=['POST'])
def scan():
    """Short squeeze scanner"""
    try:
        print("\n🔍 Short squeeze scan...")
        
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
        
        print(f"Scanning {len(stocks)} high short stocks...")
        
        results = []
        
        for stock in stocks:
            ticker = stock['ticker']
            
            # Try yfinance first
            hist, info, source = get_stock_data(ticker, period='3mo')
            
            if hist is None or len(hist) < 2:
                # Try Tradier as backup for current price
                tradier_quote = get_tradier_realtime_price(ticker)
                if tradier_quote:
                    # Use Tradier data
                    results.append({
                        'ticker': ticker,
                        'company': stock['company'],
                        'shortInterest': stock['short_interest'],
                        'currentPrice': tradier_quote['price'],
                        'dailyChange': tradier_quote['change_percentage'],
                        'volume': tradier_quote['volume'],
                        'volumeRatio': 1.0,
                        'riskScore': stock['short_interest'] * 2,
                        'dataSource': 'tradier'
                    })
                continue
            
            try:
                current_price = hist['Close'].iloc[-1]
                previous_close = hist['Close'].iloc[-2]
                daily_change = ((current_price - previous_close) / previous_close) * 100
                
                current_volume = hist['Volume'].iloc[-1]
                avg_volume = hist['Volume'].mean()
                volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0
                
                risk_score = (stock['short_interest'] * 2 + daily_change * 2 + volume_ratio * 10) / 4
                
                if daily_change >= min_gain and volume_ratio >= min_vol_ratio and risk_score >= min_risk:
                    results.append({
                        'ticker': ticker,
                        'company': stock['company'],
                        'shortInterest': stock['short_interest'],
                        'currentPrice': float(current_price),
                        'dailyChange': float(daily_change),
                        'volume': int(current_volume),
                        'volumeRatio': float(volume_ratio),
                        'riskScore': float(risk_score),
                        'dataSource': source
                    })
            except:
                continue
        
        results.sort(key=lambda x: x['riskScore'], reverse=True)
        
        print(f"✅ Found {len(results)} matches\n")
        
        return jsonify({
            'success': True,
            'results': results,
            'count': len(results)
        })
        
    except Exception as e:
        print(f"❌ Error: {e}\n")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/daily-plays', methods=['POST'])
def daily_plays():
    """Daily plays scanner"""
    try:
        print("\n🎯 Daily plays scan...")
        
        tickers = CLEAN_STOCKS[:STOCK_COUNTS['daily_plays']]
        print(f"Scanning {len(tickers)} stocks...")
        
        results = []
        
        for ticker in tickers:
            hist, info, source = get_stock_data(ticker, period='1mo')
            
            if hist is None or len(hist) < 3:
                continue
            
            patterns = check_all_patterns(hist)
            
            if patterns.get('type'):
                try:
                    current_price = hist['Close'].iloc[-1]
                    previous_close = hist['Close'].iloc[-2]
                    daily_change = ((current_price - previous_close) / previous_close) * 100
                    
                    print(f"  ✅ {ticker}: {patterns['type']}")
                    
                    results.append({
                        'ticker': ticker,
                        'company': info.get('longName', ticker),
                        'currentPrice': float(current_price),
                        'dailyChange': float(daily_change),
                        'volume': int(hist['Volume'].iloc[-1]),
                        'avgVolume': int(hist['Volume'].mean()),
                        'marketCap': info.get('marketCap', 0),
                        'pattern': patterns,
                        'dataSource': source
                    })
                except:
                    continue
        
        print(f"✅ Found {len(results)} patterns\n")
        
        return jsonify({
            'success': True,
            'results': results,
            'count': len(results)
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
        
        print(f"✅ Found {len(results)} patterns\n")
        
        return jsonify({'success': True, 'results': results})
        
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
        
        print(f"✅ Found {len(results)} patterns\n")
        
        return jsonify({'success': True, 'results': results})
        
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
            hist, _, source = get_stock_data(ticker, period='1mo')
            
            if hist is None or len(hist) < 2:
                continue
            
            try:
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
        
        print(f"✅ Found {len(results)} cryptos\n")
        
        return jsonify({'success': True, 'results': results})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/volemon-scan', methods=['POST'])
def volemon_scan():
    """Volume scanner"""
    try:
        print("\n🔊 Volemon scan...")
        
        data = request.json or {}
        min_volume_multiple = float(data.get('min_volume_multiple', 2.0))
        
        tickers = CLEAN_STOCKS[:STOCK_COUNTS['volemon']]
        print(f"Scanning {len(tickers)} for {min_volume_multiple}x volume...")
        
        results = []
        
        for ticker in tickers:
            hist, info, source = get_stock_data(ticker, period='1mo')
            
            if hist is None or len(hist) < 2:
                continue
            
            try:
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
                        'dataSource': source
                    })
            except:
                continue
        
        results.sort(key=lambda x: x['volume_multiple'], reverse=True)
        
        print(f"✅ Found {len(results)} spikes\n")
        
        return jsonify({
            'success': True,
            'results': results[:50],
            'count': len(results)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/usuals-scan', methods=['POST'])
def usuals_scan():
    """Usuals scanner"""
    try:
        print("\n⭐ Usuals scan...")
        
        data = request.json or {}
        tickers = data.get('tickers', CLEAN_STOCKS[:STOCK_COUNTS['usuals']])
        
        results = []
        
        for ticker in tickers:
            hist, info, source = get_stock_data(ticker, period='1mo')
            
            if hist is None or len(hist) < 3:
                continue
            
            try:
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
                
                results.append({
                    'ticker': ticker,
                    'company': info.get('longName', ticker),
                    'price': float(current_price),
                    'change': float(change_pct),
                    'volume': int(current_volume),
                    'avg_volume': int(avg_volume),
                    'volume_ratio': float(volume_ratio),
                    'patterns': patterns_output,
                    'dataSource': source
                })
            except:
                continue
        
        print(f"✅ Found {len(results)} usuals\n")
        
        return jsonify({
            'success': True,
            'results': results,
            'count': len(results)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    
    print("✅ Ready on port 8080")
    print("📱 http://localhost:8080")
    print("🧪 Test yfinance: http://localhost:8080/api/test")
    print("🧪 Test Tradier: http://localhost:8080/api/test-tradier\n")
    
    app.run(debug=True, host='0.0.0.0', port=port)
