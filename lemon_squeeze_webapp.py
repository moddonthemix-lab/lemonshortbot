"""
🍋 LEMON SQUEEZE WEB APP v2.1 - OPTIMIZED FOR RATE LIMITS 🍋
Fixed: Proper rate limiting, reduced stock counts
"""

from flask import Flask, jsonify, request, send_from_directory
import yfinance as yf
from datetime import datetime
import time
import os
import json

app = Flask(__name__)

# ===== OPTIMIZED STOCK COUNTS =====
# Reduced to avoid Yahoo rate limiting
STOCK_LIMITS = {
    'daily_plays': 25,      # Was 40+, now 25
    'hourly_plays': 20,     # Was 40+, now 20
    'weekly_plays': 20,     # Was 40+, now 20
    'volemon': 30,          # Was 40+, now 30
    'usuals': 14            # Keep as is
}

# Core popular stocks (reduced list)
CORE_STOCKS = [
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'META', 'NVDA', 'AMD',
    'SPY', 'QQQ', 'IWM', 'DIA',
    'NFLX', 'DIS', 'PYPL', 'UBER',
    'JPM', 'BAC', 'GS', 'C',
    'XOM', 'CVX',
    'WMT', 'TGT', 'COST'
]

print("\n" + "="*70)
print("🍋 LEMON SQUEEZE v2.1 - OPTIMIZED 🍋")
print("="*70)
print(f"\n⚡ Reduced stock counts to avoid rate limits")
print(f"⚡ Single 0.6s delay per stock (tested safe limit)")
print("🚀 Starting...\n")

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

def check_strat_31(hist):
    """Check for 3-1 pattern"""
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
            'direction': direction
        }
        return True, pattern_data
    
    return False, None

@app.route('/')
def index():
    """Serve HTML"""
    html_files = [
        'lemon_squeeze_with_volemon__4_.html',
        'lemon_squeeze_webapp.html',
        'index.html'
    ]
    
    for html_file in html_files:
        if os.path.exists(html_file):
            return send_from_directory('.', html_file)
    
    return "<h1>🍋 Lemon Squeeze v2.1 - Backend Ready</h1>"

@app.route('/api/daily-plays', methods=['POST'])
def daily_plays():
    """Daily plays - OPTIMIZED"""
    try:
        print(f"\n🎯 Daily Plays scan...")
        
        # Use reduced stock list
        tickers = CORE_STOCKS[:STOCK_LIMITS['daily_plays']]
        print(f"Scanning {len(tickers)} stocks...")
        
        results = []
        
        for i, ticker in enumerate(tickers, 1):
            try:
                time.sleep(0.6)  # Single delay - 0.6s is safe
                
                stock_data = yf.Ticker(ticker)
                hist = stock_data.history(period='1mo')
                
                if len(hist) >= 3:
                    has_pattern, pattern_data = check_strat_31(hist)
                    
                    if has_pattern:
                        info = stock_data.info
                        current_price = hist['Close'].iloc[-1]
                        prev_price = hist['Close'].iloc[-2]
                        change = ((current_price - prev_price) / prev_price) * 100
                        
                        results.append({
                            'ticker': ticker,
                            'company': info.get('longName', ticker),
                            'currentPrice': float(current_price),
                            'dailyChange': float(change),
                            'volume': int(hist['Volume'].iloc[-1]),
                            'avgVolume': int(hist['Volume'].mean()),
                            'marketCap': info.get('marketCap', 0),
                            'pattern': pattern_data
                        })
                        
                        print(f"  ✅ {ticker}: {pattern_data['direction']}")
                
                if i % 5 == 0:
                    print(f"  Progress: {i}/{len(tickers)}")
                    
            except Exception as e:
                print(f"  ⚠️  {ticker}: {e}")
                continue
        
        print(f"✅ Done! Found {len(results)} patterns\n")
        
        return jsonify({
            'success': True,
            'results': results,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/hourly-plays', methods=['POST'])
def hourly_plays():
    """Hourly plays - OPTIMIZED"""
    try:
        print(f"\n⏰ Hourly scan...")
        
        tickers = CORE_STOCKS[:STOCK_LIMITS['hourly_plays']]
        results = []
        
        for ticker in tickers:
            try:
                time.sleep(0.6)
                
                stock_data = yf.Ticker(ticker)
                hist = stock_data.history(period='5d', interval='1h').dropna()
                
                if len(hist) >= 3:
                    has_pattern, pattern_data = check_strat_31(hist)
                    
                    if has_pattern:
                        info = stock_data.info
                        results.append({
                            'ticker': ticker,
                            'company': info.get('longName', ticker),
                            'currentPrice': float(hist['Close'].iloc[-1]),
                            'volume': int(hist['Volume'].iloc[-1]),
                            'pattern': pattern_data,
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
    """Weekly plays - OPTIMIZED"""
    try:
        print(f"\n📅 Weekly scan...")
        
        tickers = CORE_STOCKS[:STOCK_LIMITS['weekly_plays']]
        results = []
        
        for ticker in tickers:
            try:
                time.sleep(0.6)
                
                stock_data = yf.Ticker(ticker)
                hist = stock_data.history(period='6mo', interval='1wk')
                
                if len(hist) >= 3:
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
            except:
                continue
        
        print(f"✅ Found {len(results)} patterns\n")
        
        return jsonify({'success': True, 'results': results})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/volemon-scan', methods=['POST'])
def volemon_scan():
    """Volemon - OPTIMIZED"""
    try:
        data = request.json or {}
        min_vol = float(data.get('min_volume_multiple', 2.0))
        
        print(f"\n🔊 Volemon scan ({min_vol}x volume)...")
        
        tickers = CORE_STOCKS[:STOCK_LIMITS['volemon']]
        results = []
        
        for ticker in tickers:
            try:
                time.sleep(0.6)
                
                stock_data = yf.Ticker(ticker)
                hist = stock_data.history(period='5d')
                
                if len(hist) >= 2:
                    current_vol = hist['Volume'].iloc[-1]
                    avg_vol = hist['Volume'].iloc[:-1].mean()
                    
                    if avg_vol > 0:
                        vol_multiple = current_vol / avg_vol
                        
                        if vol_multiple >= min_vol:
                            info = stock_data.info
                            current_price = hist['Close'].iloc[-1]
                            prev_price = hist['Close'].iloc[-2]
                            change = ((current_price - prev_price) / prev_price) * 100
                            
                            results.append({
                                'ticker': ticker,
                                'company': info.get('longName', ticker),
                                'price': float(current_price),
                                'change': float(change),
                                'volume': int(current_vol),
                                'avg_volume': int(avg_vol),
                                'volume_multiple': float(vol_multiple),
                                'market_cap': info.get('marketCap', 0)
                            })
            except:
                continue
        
        results.sort(key=lambda x: x['volume_multiple'], reverse=True)
        
        print(f"✅ Found {len(results)} spikes\n")
        
        return jsonify({'success': True, 'results': results[:50]})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/usuals-scan', methods=['POST'])
def usuals_scan():
    """Usuals - OPTIMIZED"""
    try:
        data = request.json or {}
        tickers = data.get('tickers', ['SOFI', 'INTC', 'SPY', 'TSLA', 'COIN', 'CDE', 'PLTR', 'AAPL', 'BAC', 'NVDA', 'GOOGL', 'META', 'MSFT', 'UNH'])
        
        print(f"\n⭐ Usuals scan ({len(tickers)} stocks)...")
        
        results = []
        
        for ticker in tickers:
            try:
                time.sleep(0.6)  # Safe delay
                
                stock_data = yf.Ticker(ticker)
                hist = stock_data.history(period='1mo')
                
                if len(hist) >= 3:
                    info = stock_data.info
                    current_price = hist['Close'].iloc[-1]
                    prev_price = hist['Close'].iloc[-2]
                    change = ((current_price - prev_price) / prev_price) * 100
                    
                    current_vol = hist['Volume'].iloc[-1]
                    avg_vol = hist['Volume'].iloc[:-1].mean()
                    vol_ratio = current_vol / avg_vol if avg_vol > 0 else 1
                    
                    # Check patterns
                    patterns = {}
                    has_pattern, pattern_data = check_strat_31(hist)
                    
                    if has_pattern:
                        patterns['daily'] = {
                            'type': '3-1 Strat',
                            'direction': pattern_data['direction']
                        }
                    else:
                        # Check inside bar
                        current = hist.iloc[-1]
                        previous = hist.iloc[-2]
                        is_inside = (current['High'] < previous['High'] and 
                                   current['Low'] > previous['Low'])
                        if is_inside:
                            patterns['daily'] = {
                                'type': 'Inside Bar (1)',
                                'direction': 'neutral'
                            }
                    
                    results.append({
                        'ticker': ticker,
                        'company': info.get('longName', ticker),
                        'price': float(current_price),
                        'change': float(change),
                        'volume': int(current_vol),
                        'avg_volume': int(avg_vol),
                        'volume_ratio': float(vol_ratio),
                        'patterns': patterns
                    })
                    
                    print(f"  ✅ {ticker}")
                    
            except Exception as e:
                print(f"  ⚠️  {ticker}: {e}")
                continue
        
        print(f"✅ Done! {len(results)} stocks\n")
        
        return jsonify({'success': True, 'results': results})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/crypto-plays', methods=['POST'])
def crypto_plays():
    """Crypto scanner"""
    try:
        crypto_tickers = ['BTC-USD', 'ETH-USD', 'XRP-USD', 'SOL-USD', 'DOGE-USD']
        results = []
        
        for ticker in crypto_tickers:
            try:
                time.sleep(0.6)
                
                stock_data = yf.Ticker(ticker)
                hist = stock_data.history(period='1mo')
                
                if len(hist) >= 2:
                    current_price = hist['Close'].iloc[-1]
                    prev_price = hist['Close'].iloc[-2]
                    change = ((current_price - prev_price) / prev_price) * 100
                    
                    results.append({
                        'ticker': ticker.replace('-USD', ''),
                        'price': float(current_price),
                        'change': float(change),
                        'volume': int(hist['Volume'].iloc[-1])
                    })
            except:
                continue
        
        return jsonify({'success': True, 'results': results})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/scan', methods=['POST'])
def scan():
    """Short squeeze scanner"""
    try:
        data = request.json or {}
        min_short = float(data.get('minShort', 25))
        min_gain = float(data.get('minGain', 15))
        
        stocks = load_stock_data()[:20]  # Limit to 20
        results = []
        
        for stock in stocks:
            try:
                time.sleep(0.6)
                
                ticker = stock['ticker']
                stock_data = yf.Ticker(ticker)
                hist = stock_data.history(period='3mo')
                
                if len(hist) >= 2:
                    current_price = hist['Close'].iloc[-1]
                    prev_price = hist['Close'].iloc[-2]
                    change = ((current_price - prev_price) / prev_price) * 100
                    
                    if stock['short_interest'] >= min_short and change >= min_gain:
                        results.append({
                            'ticker': ticker,
                            'company': stock['company'],
                            'shortInterest': stock['short_interest'],
                            'currentPrice': float(current_price),
                            'dailyChange': float(change)
                        })
            except:
                continue
        
        return jsonify({'success': True, 'results': results})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    
    print("✅ Ready on port 8080!")
    print("📱 http://localhost:8080\n")
    
    app.run(debug=True, host='0.0.0.0', port=port)
