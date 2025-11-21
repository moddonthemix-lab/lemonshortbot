"""
🍋 LEMON SQUEEZE WEB APP v2.1 - VOLEMON EDITION 🍋
Flask-based web interface with:
- Short Squeeze Scanner
- Daily/Weekly/Hourly Plays (3-1 Strat Pattern Scanner)
- Crypto Scanner
- 🔊 Volemon (Auto Volume Scanner)
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
    """
    Check if stock has a 3-1 pattern (The Strat)
    """
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
        'lemon_squeeze_webapp.html',
        'lemon_squeeze.html',
        'index.html'
    ]
    
    for html_file in html_files:
        if os.path.exists(html_file):
            return send_from_directory('.', html_file)
    
    return "<h1>🍋 Lemon Squeeze - Backend Ready!</h1>"

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
        
        for stock in stocks:
            ticker = stock['ticker']
            
            try:
                time.sleep(0.7)  # Rate limiting
                
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
                            'riskScore': float(risk_score)
                        })
                
            except Exception as e:
                print(f"Error on {ticker}: {e}")
                continue
        
        results.sort(key=lambda x: x['riskScore'], reverse=True)
        
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

@app.route('/api/daily-plays', methods=['POST'])
def daily_plays():
    """Daily plays scanner"""
    try:
        popular_tickers = [
            'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'META', 'NVDA', 'AMD',
            'SPY', 'QQQ', 'IWM', 'DIA',
            'NFLX', 'DIS', 'BABA', 'PYPL', 'SQ', 'ROKU', 'SNAP', 'UBER',
            'F', 'GM', 'NIO', 'LCID', 'RIVN',
            'BA', 'GE', 'CAT', 'DE',
            'JPM', 'BAC', 'GS', 'MS', 'C',
            'XOM', 'CVX', 'COP', 'SLB',
            'PFE', 'JNJ', 'MRNA', 'BNTX',
            'WMT', 'TGT', 'COST', 'HD', 'LOW',
        ]
        
        results = []
        total = len(popular_tickers)
        
        print(f"\n🎯 Starting Daily Plays scan for {total} stocks...")
        
        for i, ticker in enumerate(popular_tickers, 1):
            try:
                time.sleep(0.7)  # Rate limiting - 0.7s is safe
                
                stock_data = yf.Ticker(ticker)
                hist = stock_data.history(period='1mo')
                info = stock_data.info
                
                if len(hist) >= 3:
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
                            'marketCap': info.get('marketCap', 0),
                            'pattern': pattern_data
                        })
                        
                        print(f"✅ {ticker}: {pattern_data['direction']} ({i}/{total})")
                
                if i % 10 == 0:
                    print(f"📊 Progress: {i}/{total}")
                
            except Exception as e:
                print(f"❌ {ticker}: {e}")
                continue
        
        results.sort(key=lambda x: x['volume'], reverse=True)
        
        print(f"\n✅ Found {len(results)} patterns\n")
        
        return jsonify({
            'success': True,
            'results': results,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/hourly-plays', methods=['POST'])
def hourly_plays():
    """Hourly plays scanner"""
    try:
        popular_tickers = [
            'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'META', 'NVDA', 'AMD',
            'SPY', 'QQQ', 'IWM', 'DIA',
            'NFLX', 'DIS', 'BABA', 'PYPL', 'SQ', 'ROKU', 'SNAP', 'UBER',
        ]
        
        results = []
        
        print(f"\n⏰ Starting Hourly scan...")
        
        for ticker in popular_tickers:
            try:
                time.sleep(0.7)
                
                stock_data = yf.Ticker(ticker)
                hist = stock_data.history(period='5d', interval='1h').dropna()
                info = stock_data.info
                
                if len(hist) >= 3:
                    has_pattern, pattern_data = check_strat_31(hist)
                    
                    if has_pattern:
                        results.append({
                            'ticker': ticker,
                            'company': info.get('longName', ticker),
                            'currentPrice': float(hist['Close'].iloc[-1]),
                            'volume': int(hist['Volume'].iloc[-1]),
                            'pattern': pattern_data,
                            'timeframe': 'hourly'
                        })
                        print(f"✅ {ticker}")
            except:
                continue
        
        print(f"✅ Found {len(results)}\n")
        
        return jsonify({'success': True, 'results': results})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/weekly-plays', methods=['POST'])
def weekly_plays():
    """Weekly plays scanner"""
    try:
        popular_tickers = [
            'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'META', 'NVDA', 'AMD',
            'SPY', 'QQQ', 'IWM', 'DIA',
            'NFLX', 'DIS', 'BABA', 'PYPL', 'SQ', 'ROKU', 'SNAP', 'UBER',
        ]
        
        results = []
        
        print(f"\n📊 Starting Weekly scan...")
        
        for ticker in popular_tickers:
            try:
                time.sleep(0.7)
                
                stock_data = yf.Ticker(ticker)
                hist = stock_data.history(period='6mo', interval='1wk')
                info = stock_data.info
                
                if len(hist) >= 3:
                    has_pattern, pattern_data = check_strat_31(hist)
                    
                    if has_pattern:
                        results.append({
                            'ticker': ticker,
                            'company': info.get('longName', ticker),
                            'currentPrice': float(hist['Close'].iloc[-1]),
                            'volume': int(hist['Volume'].iloc[-1]),
                            'pattern': pattern_data,
                            'timeframe': 'weekly'
                        })
                        print(f"✅ {ticker}")
            except:
                continue
        
        print(f"✅ Found {len(results)}\n")
        
        return jsonify({'success': True, 'results': results})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/find-a-play', methods=['POST'])
def find_a_play():
    """
    🎯 FIND A PLAY - Multi-Timeframe Scanner
    Scans 47 stocks across Daily, Weekly, and Hourly timeframes
    Shows pattern alignment strength (1-3 stars)
    """
    try:
        tickers = get_find_a_play_tickers()
        results = []
        total = len(tickers)
        
        print(f"\n🎯 Find A Play - Multi-Timeframe scan ({total} stocks)...")
        
        for i, ticker in enumerate(tickers, 1):
            try:
                time.sleep(0.7)
                
                stock_data = yf.Ticker(ticker)
                info = stock_data.info
                
                # Get daily data (1 month)
                daily_hist = stock_data.history(period='1mo')
                
                if len(daily_hist) < 3:
                    continue
                
                # Current price and volume info
                current_price = daily_hist['Close'].iloc[-1]
                previous_close = daily_hist['Close'].iloc[-2]
                daily_change = ((current_price - previous_close) / previous_close) * 100
                current_volume = daily_hist['Volume'].iloc[-1]
                avg_volume = daily_hist['Volume'].mean()
                
                # Check Daily timeframe
                has_daily, daily_pattern = check_strat_31(daily_hist)
                
                # Check Weekly timeframe (resample daily to weekly)
                weekly_hist = daily_hist.resample('W').agg({
                    'Open': 'first',
                    'High': 'max',
                    'Low': 'min',
                    'Close': 'last',
                    'Volume': 'sum'
                })
                has_weekly, weekly_pattern = check_strat_31(weekly_hist)
                
                # Check Hourly timeframe (last 5 days)
                hourly_hist = stock_data.history(period='5d', interval='1h')
                has_hourly, hourly_pattern = False, None
                if len(hourly_hist) >= 3:
                    has_hourly, hourly_pattern = check_strat_31(hourly_hist)
                
                # Calculate strength score (0-3)
                strength = sum([has_daily, has_weekly, has_hourly])
                
                # Only include if at least one pattern found
                if strength > 0:
                    result = {
                        'ticker': ticker,
                        'company': info.get('longName', ticker),
                        'currentPrice': float(current_price),
                        'dailyChange': float(daily_change),
                        'volume': int(current_volume),
                        'avgVolume': int(avg_volume),
                        'marketCap': info.get('marketCap', 0),
                        'strength': strength,
                        'patterns': {
                            'daily': daily_pattern if has_daily else None,
                            'weekly': weekly_pattern if has_weekly else None,
                            'hourly': hourly_pattern if has_hourly else None
                        }
                    }
                    results.append(result)
                    
                    # Print progress
                    stars = '⭐' * strength
                    print(f"{stars} {ticker} ({i}/{total})")
                
            except Exception as e:
                print(f"❌ {ticker}: {e}")
                continue
        
        # Sort by strength first, then by daily change
        results.sort(key=lambda x: (x['strength'], x['dailyChange']), reverse=True)
        
        print(f"\n✅ Found {len(results)} plays with patterns!")
        print(f"   3-Star plays: {sum(1 for r in results if r['strength'] == 3)}")
        print(f"   2-Star plays: {sum(1 for r in results if r['strength'] == 2)}")
        print(f"   1-Star plays: {sum(1 for r in results if r['strength'] == 1)}\n")
        
        return jsonify({
            'success': True,
            'results': results,
            'timestamp': datetime.now().isoformat(),
            'stats': {
                'total_scanned': total,
                'patterns_found': len(results),
                'three_star': sum(1 for r in results if r['strength'] == 3),
                'two_star': sum(1 for r in results if r['strength'] == 2),
                'one_star': sum(1 for r in results if r['strength'] == 1)
            }
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

def get_find_a_play_tickers():
    """
    Stock list for Find A Play scanner
    Combined Daily + Volemon lists (47 stocks total)
    """
    return [
        'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'META', 'NVDA', 'AMD',
        'SPY', 'QQQ', 'IWM', 'DIA',
        'NFLX', 'DIS', 'BABA', 'PYPL', 'SQ', 'ROKU', 'SNAP', 'UBER',
        'F', 'GM', 'NIO', 'LCID', 'RIVN',
        'BA', 'GE', 'CAT', 'DE',
        'JPM', 'BAC', 'GS', 'MS', 'C',
        'XOM', 'CVX', 'COP', 'SLB',
        'PFE', 'JNJ', 'MRNA', 'BNTX',
        'WMT', 'TGT', 'COST', 'HD', 'LOW',
    ]

@app.route('/api/crypto-plays', methods=['POST'])
def crypto_plays():
    """Crypto scanner"""
    try:
        crypto_tickers = {
            'BTC-USD': 'Bitcoin',
            'ETH-USD': 'Ethereum',
            'XRP-USD': 'Ripple',
            'SOL-USD': 'Solana',
            'DOGE-USD': 'Dogecoin'
        }
        
        results = []
        
        print(f"\n₿ Starting Crypto scan...")
        
        for ticker, name in crypto_tickers.items():
            try:
                time.sleep(0.7)
                
                stock_data = yf.Ticker(ticker)
                hist = stock_data.history(period='1mo')
                
                if len(hist) >= 3:
                    has_pattern, pattern_data = check_strat_31(hist)
                    
                    if has_pattern:
                        current_price = hist['Close'].iloc[-1]
                        prev_price = hist['Close'].iloc[-2]
                        change = ((current_price - prev_price) / prev_price) * 100
                        
                        results.append({
                            'ticker': ticker.replace('-USD', ''),
                            'company': name,
                            'currentPrice': float(current_price),
                            'change': float(change),
                            'volume': int(hist['Volume'].iloc[-1]),
                            'pattern': pattern_data,
                            'timeframe': 'daily'
                        })
            except:
                continue
        
        print(f"✅ Found {len(results)}\n")
        
        return jsonify({'success': True, 'results': results})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/volemon-scan', methods=['POST'])
def volemon_scan():
    """Volemon volume scanner"""
    try:
        data = request.json or {}
        min_volume_multiple = float(data.get('min_volume_multiple', 2.0))
        
        popular_tickers = [
            'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'META', 'NVDA', 'AMD',
            'SPY', 'QQQ', 'IWM', 'DIA',
            'NFLX', 'DIS', 'BABA', 'PYPL', 'SQ', 'ROKU', 'SNAP', 'UBER',
            'F', 'GM', 'NIO', 'LCID', 'RIVN',
            'JPM', 'BAC', 'GS', 'MS', 'C',
            'XOM', 'CVX', 'COP', 'SLB',
        ]
        
        results = []
        
        print(f"\n🔊 Volemon scan ({min_volume_multiple}x volume)...")
        
        for ticker in popular_tickers:
            try:
                time.sleep(0.7)
                
                stock_data = yf.Ticker(ticker)
                hist = stock_data.history(period='5d')
                info = stock_data.info
                
                if len(hist) >= 2:
                    current_volume = hist['Volume'].iloc[-1]
                    avg_volume = hist['Volume'].iloc[:-1].mean()
                    
                    if avg_volume > 0:
                        volume_multiple = current_volume / avg_volume
                        
                        if volume_multiple >= min_volume_multiple:
                            current_price = hist['Close'].iloc[-1]
                            prev_price = hist['Close'].iloc[-2]
                            change = ((current_price - prev_price) / prev_price) * 100
                            
                            results.append({
                                'ticker': ticker,
                                'company': info.get('longName', ticker),
                                'price': float(current_price),
                                'change': float(change),
                                'volume': int(current_volume),
                                'avg_volume': int(avg_volume),
                                'volume_multiple': float(volume_multiple),
                                'market_cap': info.get('marketCap', 0)
                            })
                            
                            print(f"✅ {ticker}: {volume_multiple:.1f}x")
            except:
                continue
        
        results.sort(key=lambda x: x['volume_multiple'], reverse=True)
        
        print(f"✅ Found {len(results)}\n")
        
        return jsonify({'success': True, 'results': results[:50]})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/usuals-scan', methods=['POST'])
def usuals_scan():
    """Usuals watchlist scanner"""
    try:
        data = request.json or {}
        tickers = data.get('tickers', ['SOFI', 'INTC', 'SPY', 'TSLA', 'COIN', 'CDE', 'PLTR', 'AAPL', 'BAC', 'NVDA', 'GOOGL', 'META', 'MSFT', 'UNH'])
        
        results = []
        
        print(f"\n⭐ Usuals scan ({len(tickers)} stocks)...")
        
        for ticker in tickers:
            try:
                time.sleep(0.7)  # Safe rate limiting
                
                stock_data = yf.Ticker(ticker)
                hist = stock_data.history(period='1mo')
                info = stock_data.info
                
                if len(hist) >= 3:
                    current_price = hist['Close'].iloc[-1]
                    prev_price = hist['Close'].iloc[-2]
                    change = ((current_price - prev_price) / prev_price) * 100
                    
                    current_volume = hist['Volume'].iloc[-1]
                    avg_volume = hist['Volume'].iloc[:-1].mean()
                    volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1
                    
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
                        'volume': int(current_volume),
                        'avg_volume': int(avg_volume),
                        'volume_ratio': float(volume_ratio),
                        'patterns': patterns
                    })
                    
                    print(f"✅ {ticker}")
                    
            except Exception as e:
                print(f"⚠️  {ticker}: {e}")
                continue
        
        print(f"✅ Done! {len(results)} stocks\n")
        
        return jsonify({'success': True, 'results': results})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    
    print("\n" + "="*60)
    print("🍋 LEMON SQUEEZE WEB APP v2.1 🍋")
    print("="*60)
    print("\n✅ Server starting...")
    print("📱 http://localhost:8080")
    print("\n📊 All Features:")
    print("  - Short Squeeze Scanner")
    print("  - Daily/Hourly/Weekly Plays")
    print("  - Crypto Scanner")
    print("  - Volemon (Volume Scanner)")
    print("  - Usuals (Watchlist)")
    print("\n🛑 Press Ctrl+C to stop")
    print("\n" + "="*60 + "\n")
    
    app.run(debug=True, host='0.0.0.0', port=port)
