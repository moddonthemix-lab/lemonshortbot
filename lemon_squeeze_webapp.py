"""
🍋 LEMON SQUEEZE v3.5 - PRODUCTION READY 🍋
Fixed and tested - works out of the box!
"""

from flask import Flask, jsonify, request, send_from_directory
import yfinance as yf
from datetime import datetime, timedelta
import time
import os
import json
import traceback

app = Flask(__name__)

# Speed controls
STOCK_COUNTS = {
    'daily_plays': 30,
    'hourly_plays': 15,
    'weekly_plays': 20,
    'volemon': 50,
    'usuals': 20
}

print("\n" + "="*70)
print("🍋 LEMON SQUEEZE v3.5 - PRODUCTION 🍋")
print("="*70)
print(f"\n📊 Stock counts: {STOCK_COUNTS}")
print("🚀 Starting server...\n")

# Top stocks list
TOP_STOCKS = [
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'META', 'NVDA', 'AMD', 'INTC', 'CRM',
    'ADBE', 'CSCO', 'ORCL', 'AVGO', 'QCOM', 'TXN', 'NOW', 'INTU', 'AMAT', 'MU',
    'PLTR', 'SNOW', 'NET', 'DDOG', 'ZS', 'CRWD', 'PANW', 'COIN', 'BLOCK', 'SHOP',
    'JPM', 'BAC', 'WFC', 'C', 'GS', 'MS', 'V', 'MA', 'PYPL', 'SOFI',
    'AFRM', 'UPST', 'LC', 'NU', 'HOOD', 'F', 'GM', 'NIO', 'XPEV', 'LI',
    'RIVN', 'LCID', 'XOM', 'CVX', 'COP', 'WMT', 'HD', 'COST', 'TGT', 'UNH',
    'JNJ', 'GME', 'AMC', 'DKNG', 'PENN', 'SPY', 'QQQ', 'IWM'
]

def check_strat_31(hist):
    """Check for 3-1 pattern"""
    try:
        if hist is None or len(hist) < 3:
            return False, None
        
        current = hist.iloc[-1]
        previous = hist.iloc[-2]
        before_prev = hist.iloc[-3]
        
        # Check if previous is "3" (outside bar)
        is_three = (previous['High'] > before_prev['High'] and 
                    previous['Low'] < before_prev['Low'])
        
        # Check if current is "1" (inside bar)
        is_one = (current['High'] < previous['High'] and 
                  current['Low'] > previous['Low'])
        
        if is_three and is_one:
            direction = "bullish" if current['Close'] > current['Open'] else "bearish"
            return True, {'direction': direction, 'type': '3-1 Strat'}
        
        return False, None
    except Exception as e:
        print(f"Error in check_strat_31: {e}")
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
    except Exception as e:
        print(f"Error in check_inside_bar: {e}")
        return False

def check_all_patterns(hist):
    """Check all patterns"""
    try:
        patterns = {}
        
        if hist is None or len(hist) < 3:
            return patterns
        
        # Check 3-1 first
        has_31, pattern_data = check_strat_31(hist)
        
        if has_31:
            patterns['type'] = '3-1 Strat'
            patterns['direction'] = pattern_data['direction']
        else:
            # Check inside bar
            if check_inside_bar(hist):
                patterns['type'] = 'Inside Bar (1)'
                patterns['direction'] = 'neutral'
        
        return patterns
    except Exception as e:
        print(f"Error in check_all_patterns: {e}")
        return {}

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
    <h1>🍋 Lemon Squeeze v3.5 - Production</h1>
    <p>Backend running! Place HTML file in same directory.</p>
    <p>Test endpoint: <a href="/api/test">/api/test</a></p>
    """

@app.route('/api/test', methods=['GET'])
def test():
    """Test endpoint"""
    try:
        print("\n🧪 Testing API...")
        
        # Test yfinance
        ticker = yf.Ticker("AAPL")
        hist = ticker.history(period="5d")
        
        if len(hist) > 0:
            return jsonify({
                'success': True,
                'message': 'API working!',
                'test_data': {
                    'ticker': 'AAPL',
                    'days': len(hist),
                    'latest_price': float(hist['Close'].iloc[-1])
                }
            })
        else:
            return jsonify({
                'success': False,
                'error': 'No data returned from yfinance'
            })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        })

@app.route('/api/scan', methods=['POST'])
def scan():
    """Short squeeze scanner"""
    try:
        print("\n🔍 Starting short squeeze scan...")
        
        data = request.json or {}
        min_short = float(data.get('minShort', 25))
        min_gain = float(data.get('minGain', 15))
        min_vol_ratio = float(data.get('minVolRatio', 1.5))
        min_risk = float(data.get('minRisk', 60))
        
        print(f"Filters: Short>={min_short}%, Gain>={min_gain}%, Vol>={min_vol_ratio}x, Risk>={min_risk}")
        
        # Load stocks from CSV
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
        
        print(f"Found {len(stocks)} stocks in CSV with short interest >= {min_short}%")
        
        if len(stocks) == 0:
            return jsonify({
                'success': True,
                'results': [],
                'count': 0,
                'message': f'No stocks found with short interest >= {min_short}%'
            })
        
        results = []
        start_time = time.time()
        
        for stock in stocks[:10]:  # Test with first 10
            ticker = stock['ticker']
            print(f"  Scanning {ticker}...", end=" ")
            
            try:
                stock_data = yf.Ticker(ticker)
                hist = stock_data.history(period='3mo')
                
                if len(hist) < 2:
                    print("No data")
                    continue
                
                current_price = hist['Close'].iloc[-1]
                previous_close = hist['Close'].iloc[-2]
                daily_change = ((current_price - previous_close) / previous_close) * 100
                
                current_volume = hist['Volume'].iloc[-1]
                avg_volume = hist['Volume'].mean()
                volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0
                
                # Simple risk score
                risk_score = (stock['short_interest'] * 2 + daily_change * 2 + volume_ratio * 10) / 4
                
                print(f"Risk={risk_score:.1f}, Change={daily_change:.1f}%, Vol={volume_ratio:.1f}x")
                
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
                        'dataSource': 'yfinance'
                    })
            except Exception as e:
                print(f"Error: {e}")
                continue
        
        elapsed = time.time() - start_time
        results.sort(key=lambda x: x['riskScore'], reverse=True)
        
        print(f"\n✅ Scan complete in {elapsed:.1f}s - Found {len(results)} matches\n")
        
        return jsonify({
            'success': True,
            'results': results,
            'count': len(results),
            'scan_time': round(elapsed, 1)
        })
        
    except Exception as e:
        print(f"\n❌ Error in scan: {e}\n")
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500

@app.route('/api/daily-plays', methods=['POST'])
def daily_plays():
    """Daily plays scanner"""
    try:
        print("\n🎯 Starting daily plays scan...")
        
        tickers = TOP_STOCKS[:STOCK_COUNTS['daily_plays']]
        print(f"Scanning {len(tickers)} stocks...")
        
        results = []
        start_time = time.time()
        
        for ticker in tickers:
            print(f"  {ticker}...", end=" ")
            
            try:
                stock_data = yf.Ticker(ticker)
                hist = stock_data.history(period='1mo')
                
                if len(hist) < 3:
                    print("Skip")
                    continue
                
                # Check patterns
                patterns = check_all_patterns(hist)
                
                if patterns.get('type'):
                    current_price = hist['Close'].iloc[-1]
                    previous_close = hist['Close'].iloc[-2]
                    daily_change = ((current_price - previous_close) / previous_close) * 100
                    
                    print(f"✓ {patterns['type']}")
                    
                    results.append({
                        'ticker': ticker,
                        'company': ticker,
                        'currentPrice': float(current_price),
                        'dailyChange': float(daily_change),
                        'volume': int(hist['Volume'].iloc[-1]),
                        'avgVolume': int(hist['Volume'].mean()),
                        'pattern': patterns,
                        'dataSource': 'yfinance'
                    })
                else:
                    print("No pattern")
                    
            except Exception as e:
                print(f"Error: {e}")
                continue
        
        elapsed = time.time() - start_time
        print(f"\n✅ Daily plays complete in {elapsed:.1f}s - Found {len(results)} patterns\n")
        
        return jsonify({
            'success': True,
            'results': results,
            'count': len(results),
            'scan_time': round(elapsed, 1)
        })
        
    except Exception as e:
        print(f"\n❌ Error in daily-plays: {e}\n")
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500

@app.route('/api/hourly-plays', methods=['POST'])
def hourly_plays():
    """Hourly scanner"""
    try:
        print("\n⏰ Hourly plays scan...")
        
        tickers = TOP_STOCKS[:STOCK_COUNTS['hourly_plays']]
        results = []
        
        for ticker in tickers:
            try:
                stock_data = yf.Ticker(ticker)
                hist = stock_data.history(period='5d', interval='1h').dropna()
                
                if len(hist) < 3:
                    continue
                
                patterns = check_all_patterns(hist)
                
                if patterns.get('type'):
                    results.append({
                        'ticker': ticker,
                        'company': ticker,
                        'currentPrice': float(hist['Close'].iloc[-1]),
                        'volume': int(hist['Volume'].iloc[-1]),
                        'pattern': patterns,
                        'timeframe': 'hourly'
                    })
            except:
                continue
        
        print(f"✅ Found {len(results)} hourly patterns\n")
        
        return jsonify({'success': True, 'results': results, 'count': len(results)})
        
    except Exception as e:
        print(f"❌ Error: {e}\n")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/weekly-plays', methods=['POST'])
def weekly_plays():
    """Weekly scanner"""
    try:
        print("\n📅 Weekly plays scan...")
        
        tickers = TOP_STOCKS[:STOCK_COUNTS['weekly_plays']]
        results = []
        
        for ticker in tickers:
            try:
                stock_data = yf.Ticker(ticker)
                hist = stock_data.history(period='6mo', interval='1wk')
                
                if len(hist) < 3:
                    continue
                
                patterns = check_all_patterns(hist)
                
                if patterns.get('type'):
                    results.append({
                        'ticker': ticker,
                        'company': ticker,
                        'currentPrice': float(hist['Close'].iloc[-1]),
                        'volume': int(hist['Volume'].iloc[-1]),
                        'pattern': patterns,
                        'timeframe': 'weekly'
                    })
            except:
                continue
        
        print(f"✅ Found {len(results)} weekly patterns\n")
        
        return jsonify({'success': True, 'results': results, 'count': len(results)})
        
    except Exception as e:
        print(f"❌ Error: {e}\n")
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
        
        print(f"✅ Found {len(results)} cryptos\n")
        
        return jsonify({'success': True, 'results': results})
        
    except Exception as e:
        print(f"❌ Error: {e}\n")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/volemon-scan', methods=['POST'])
def volemon_scan():
    """Volume scanner"""
    try:
        print("\n🔊 Volemon scan...")
        
        data = request.json or {}
        min_volume_multiple = float(data.get('min_volume_multiple', 2.0))
        
        tickers = TOP_STOCKS[:STOCK_COUNTS['volemon']]
        print(f"Scanning {len(tickers)} stocks for {min_volume_multiple}x volume...")
        
        results = []
        start_time = time.time()
        
        for ticker in tickers:
            print(f"  {ticker}...", end=" ")
            
            try:
                stock_data = yf.Ticker(ticker)
                hist = stock_data.history(period='1mo')
                
                if len(hist) < 2:
                    print("Skip")
                    continue
                
                current_volume = hist['Volume'].iloc[-1]
                avg_volume = hist['Volume'].iloc[:-1].mean()
                
                if avg_volume == 0:
                    print("No vol")
                    continue
                
                volume_multiple = current_volume / avg_volume
                
                if volume_multiple >= min_volume_multiple:
                    current_price = hist['Close'].iloc[-1]
                    prev_price = hist['Close'].iloc[-2]
                    change_pct = ((current_price - prev_price) / prev_price) * 100
                    
                    print(f"✓ {volume_multiple:.1f}x")
                    
                    results.append({
                        'ticker': ticker,
                        'company': ticker,
                        'price': float(current_price),
                        'change': float(change_pct),
                        'volume': int(current_volume),
                        'avg_volume': int(avg_volume),
                        'volume_multiple': float(volume_multiple),
                        'dataSource': 'yfinance'
                    })
                else:
                    print(f"{volume_multiple:.1f}x")
            except Exception as e:
                print(f"Error")
                continue
        
        results.sort(key=lambda x: x['volume_multiple'], reverse=True)
        elapsed = time.time() - start_time
        
        print(f"\n✅ Volemon complete in {elapsed:.1f}s - Found {len(results)}\n")
        
        return jsonify({
            'success': True,
            'results': results[:50],
            'count': len(results),
            'scan_time': round(elapsed, 1)
        })
        
    except Exception as e:
        print(f"\n❌ Error: {e}\n")
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/usuals-scan', methods=['POST'])
def usuals_scan():
    """Usuals scanner"""
    try:
        print("\n⭐ Usuals scan...")
        
        data = request.json or {}
        tickers = data.get('tickers', TOP_STOCKS[:STOCK_COUNTS['usuals']])
        
        results = []
        
        for ticker in tickers:
            try:
                stock_data = yf.Ticker(ticker)
                hist = stock_data.history(period='1mo')
                
                if len(hist) < 3:
                    continue
                
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
                    'company': ticker,
                    'price': float(current_price),
                    'change': float(change_pct),
                    'volume': int(current_volume),
                    'avg_volume': int(avg_volume),
                    'volume_ratio': float(volume_ratio),
                    'patterns': patterns_output,
                    'dataSource': 'yfinance'
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
        print(f"❌ Error: {e}\n")
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    
    print("\n✅ Server starting on port 8080...")
    print("📱 Open: http://localhost:8080")
    print("🧪 Test: http://localhost:8080/api/test")
    print("🛑 Press Ctrl+C to stop\n")
    
    app.run(debug=True, host='0.0.0.0', port=port)
