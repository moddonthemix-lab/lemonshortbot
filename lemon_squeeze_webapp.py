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
                    # Clean ticker - remove $ and whitespace
                    ticker = ticker.strip().replace('$', '')
                    try:
                        short_interest = float(short_pct)
                        if short_interest >= 25.0 and ticker:  # Make sure ticker isn't empty
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
    3 = Outside bar (higher high + lower low than previous)
    1 = Inside bar (lower high + higher low than previous)
    """
    if len(hist) < 3:
        return False, None
    
    # Get last 3 candles
    current = hist.iloc[-1]
    previous = hist.iloc[-2]
    before_prev = hist.iloc[-3]
    
    # Check if previous candle is a "3" (outside bar)
    is_three = (previous['High'] > before_prev['High'] and 
                previous['Low'] < before_prev['Low'])
    
    # Check if current candle is a "1" (inside bar)
    is_one = (current['High'] < previous['High'] and 
              current['Low'] > previous['Low'])
    
    # Is bullish or bearish?
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
    return send_from_directory('.', 'lemon_squeeze_webapp.html')

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
                
                time.sleep(0.1)
                
            except Exception as e:
                continue
        
        results.sort(key=lambda x: x['riskScore'], reverse=True)
        save_scan_to_history(results, min_short, min_gain, min_vol_ratio, min_risk)
        
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
    """API endpoint to scan for 3-1 Strat patterns - NO FILTERS"""
    try:
        # Get popular stocks list (you can customize this)
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
        
        # Add high short stocks to the list
        high_short_stocks = load_stock_data()
        for stock in high_short_stocks:
            if stock['ticker'] not in popular_tickers:
                popular_tickers.append(stock['ticker'])
        
        results = []
        processed = 0
        total = len(popular_tickers)
        
        print(f"\n🎯 Starting Daily Plays scan for {total} stocks...")
        
        for ticker in popular_tickers:
            processed += 1
            try:
                stock_data = yf.Ticker(ticker)
                hist = stock_data.history(period='1mo')
                info = stock_data.info
                
                if len(hist) >= 3:
                    has_pattern, pattern_data = check_strat_31(hist)
                    
                    if has_pattern:
                        current_volume = hist['Volume'].iloc[-1]
                        
                        # Calculate daily change
                        current_price = hist['Close'].iloc[-1]
                        previous_close = hist['Close'].iloc[-2]
                        daily_change = ((current_price - previous_close) / previous_close) * 100
                        
                        # Get company name
                        company_name = info.get('longName', ticker)
                        market_cap = info.get('marketCap', 0)
                        avg_volume = hist['Volume'].mean()
                        
                        results.append({
                            'ticker': ticker,
                            'company': company_name,
                            'currentPrice': float(current_price),
                            'dailyChange': float(daily_change),
                            'volume': int(current_volume),
                            'avgVolume': int(avg_volume),
                            'marketCap': int(market_cap),
                            'pattern': pattern_data
                        })
                        
                        print(f"✅ Found {pattern_data['direction']} pattern: {ticker} ({processed}/{total})")
                
                if processed % 10 == 0:
                    print(f"📊 Progress: {processed}/{total} stocks scanned, {len(results)} patterns found")
                
                time.sleep(0.05)  # Faster for more stocks
                
            except Exception as e:
                print(f"❌ Error on {ticker}: {e}")
                continue
        
        # Sort by volume (most active first)
        results.sort(key=lambda x: x['volume'], reverse=True)
        
        print(f"\n✅ Scan complete! Found {len(results)} total patterns")
        
        return jsonify({
            'success': True,
            'results': results,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        print(f"💥 Error in daily_plays: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/hourly-plays', methods=['POST'])
def hourly_plays():
    """API endpoint to scan for 3-1 Strat patterns on HOURLY timeframe"""
    try:
        # Get popular stocks list
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
        
        # Add high short stocks to the list
        high_short_stocks = load_stock_data()
        for stock in high_short_stocks:
            if stock['ticker'] not in popular_tickers:
                popular_tickers.append(stock['ticker'])
        
        results = []
        processed = 0
        total = len(popular_tickers)
        
        print(f"\n⏰ Starting Hourly Plays scan for {total} stocks...")
        
        for ticker in popular_tickers:
            processed += 1
            try:
                stock_data = yf.Ticker(ticker)
                # Get last 60 days with hourly intervals
                hist = stock_data.history(period='60d', interval='1h')
                
                # Remove any rows with NaN values
                hist = hist.dropna()
                
                info = stock_data.info
                
                if len(hist) >= 3:
                    has_pattern, pattern_data = check_strat_31(hist)
                    
                    if has_pattern:
                        current_volume = hist['Volume'].iloc[-1]
                        
                        # Calculate hourly change
                        current_price = hist['Close'].iloc[-1]
                        previous_close = hist['Close'].iloc[-2]
                        hourly_change = ((current_price - previous_close) / previous_close) * 100
                        
                        # Get company name
                        company_name = info.get('longName', ticker)
                        market_cap = info.get('marketCap', 0)
                        avg_volume = hist['Volume'].mean()
                        
                        results.append({
                            'ticker': ticker,
                            'company': company_name,
                            'currentPrice': float(current_price),
                            'hourlyChange': float(hourly_change),
                            'volume': int(current_volume),
                            'avgVolume': int(avg_volume),
                            'marketCap': int(market_cap),
                            'pattern': pattern_data,
                            'timeframe': 'hourly'
                        })
                        
                        print(f"✅ Found {pattern_data['direction']} hourly pattern: {ticker} ({processed}/{total})")
                
                if processed % 10 == 0:
                    print(f"📊 Progress: {processed}/{total} stocks scanned, {len(results)} patterns found")
                
                time.sleep(0.05)
                
            except Exception as e:
                print(f"❌ Error on {ticker}: {e}")
                continue
        
        # Sort by volume (most active first)
        results.sort(key=lambda x: x['volume'], reverse=True)
        
        print(f"\n✅ Hourly scan complete! Found {len(results)} total patterns")
        
        return jsonify({
            'success': True,
            'results': results,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        print(f"💥 Error in hourly_plays: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/crypto-plays', methods=['POST'])
def crypto_plays():
    """API endpoint to scan for 3-1 Strat patterns on CRYPTO (all timeframes)"""
    try:
        # Crypto tickers on yfinance
        crypto_tickers = {
            'BTC-USD': 'Bitcoin',
            'ETH-USD': 'Ethereum',
            'XRP-USD': 'Ripple',
            'SOL-USD': 'Solana',
            'DOGE-USD': 'Dogecoin',
            'HYPE-USD': 'Hyperliquid'
        }
        
        # Timeframes to check
        timeframes = [
            {'period': '60d', 'interval': '1h', 'name': 'Hourly'},
            {'period': '3mo', 'interval': '1d', 'name': 'Daily'},
            {'period': '6mo', 'interval': '1wk', 'name': 'Weekly'}
        ]
        
        results = []
        processed = 0
        total = len(crypto_tickers) * len(timeframes)
        
        print(f"\n₿ Starting Crypto scan for {len(crypto_tickers)} cryptos across {len(timeframes)} timeframes...")
        
        for ticker, name in crypto_tickers.items():
            for tf in timeframes:
                processed += 1
                try:
                    stock_data = yf.Ticker(ticker)
                    hist = stock_data.history(period=tf['period'], interval=tf['interval'])
                    
                    # Remove any rows with NaN values
                    hist = hist.dropna()
                    
                    if len(hist) >= 3:
                        has_pattern, pattern_data = check_strat_31(hist)
                        
                        if has_pattern:
                            current_volume = hist['Volume'].iloc[-1]
                            
                            # Calculate change
                            current_price = hist['Close'].iloc[-1]
                            previous_close = hist['Close'].iloc[-2]
                            change = ((current_price - previous_close) / previous_close) * 100
                            
                            avg_volume = hist['Volume'].mean()
                            
                            # Get market cap if available
                            info = stock_data.info
                            market_cap = info.get('marketCap', 0)
                            
                            results.append({
                                'ticker': ticker.replace('-USD', ''),
                                'fullTicker': ticker,
                                'company': name,
                                'currentPrice': float(current_price),
                                'change': float(change),
                                'volume': int(current_volume),
                                'avgVolume': int(avg_volume),
                                'marketCap': int(market_cap),
                                'pattern': pattern_data,
                                'timeframe': tf['name']
                            })
                            
                            print(f"✅ Found {pattern_data['direction']} {tf['name']} pattern: {ticker} ({processed}/{total})")
                    
                    if processed % 5 == 0:
                        print(f"📊 Progress: {processed}/{total} scans complete, {len(results)} patterns found")
                    
                    time.sleep(0.1)
                    
                except Exception as e:
                    print(f"❌ Error on {ticker} {tf['name']}: {e}")
                    continue
        
        # Sort by timeframe importance (Weekly > Daily > Hourly) then by volume
        timeframe_order = {'Weekly': 0, 'Daily': 1, 'Hourly': 2}
        results.sort(key=lambda x: (timeframe_order.get(x['timeframe'], 3), -x['volume']))
        
        print(f"\n✅ Crypto scan complete! Found {len(results)} total patterns")
        
        return jsonify({
            'success': True,
            'results': results,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        print(f"💥 Error in crypto_plays: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/weekly-plays', methods=['POST'])
def weekly_plays():
    """API endpoint to scan for 3-1 Strat patterns on WEEKLY timeframe"""
    try:
        # Get popular stocks list
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
        
        # Add high short stocks to the list
        high_short_stocks = load_stock_data()
        for stock in high_short_stocks:
            if stock['ticker'] not in popular_tickers:
                popular_tickers.append(stock['ticker'])
        
        results = []
        processed = 0
        total = len(popular_tickers)
        
        print(f"\n📊 Starting Weekly Plays scan for {total} stocks...")
        
        for ticker in popular_tickers:
            processed += 1
            try:
                stock_data = yf.Ticker(ticker)
                # Get 6 months of data for weekly analysis
                hist = stock_data.history(period='6mo')
                
                # Resample to weekly data (week ending Friday)
                weekly = hist.resample('W-FRI').agg({
                    'Open': 'first',
                    'High': 'max',
                    'Low': 'min',
                    'Close': 'last',
                    'Volume': 'sum'
                })
                
                # Remove any rows with NaN values
                weekly = weekly.dropna()
                
                info = stock_data.info
                
                if len(weekly) >= 3:
                    has_pattern, pattern_data = check_strat_31(weekly)
                    
                    if has_pattern:
                        current_volume = weekly['Volume'].iloc[-1]
                        
                        # Calculate weekly change
                        current_price = weekly['Close'].iloc[-1]
                        previous_close = weekly['Close'].iloc[-2]
                        weekly_change = ((current_price - previous_close) / previous_close) * 100
                        
                        # Get company name
                        company_name = info.get('longName', ticker)
                        market_cap = info.get('marketCap', 0)
                        avg_volume = weekly['Volume'].mean()
                        
                        results.append({
                            'ticker': ticker,
                            'company': company_name,
                            'currentPrice': float(current_price),
                            'weeklyChange': float(weekly_change),
                            'volume': int(current_volume),
                            'avgVolume': int(avg_volume),
                            'marketCap': int(market_cap),
                            'pattern': pattern_data,
                            'timeframe': 'weekly'
                        })
                        
                        print(f"✅ Found {pattern_data['direction']} weekly pattern: {ticker} ({processed}/{total})")
                
                if processed % 10 == 0:
                    print(f"📊 Progress: {processed}/{total} stocks scanned, {len(results)} patterns found")
                
                time.sleep(0.05)
                
            except Exception as e:
                print(f"❌ Error on {ticker}: {e}")
                continue
        
        # Sort by volume (most active first)
        results.sort(key=lambda x: x['volume'], reverse=True)
        
        print(f"\n✅ Weekly scan complete! Found {len(results)} total patterns")
        
        return jsonify({
            'success': True,
            'results': results,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        print(f"💥 Error in weekly_plays: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/track-pattern', methods=['POST'])
def track_pattern():
    """Track a pattern for historical win rate"""
    try:
        data = request.json
        ticker = data.get('ticker')
        timeframe = data.get('timeframe')
        direction = data.get('direction')
        entry_price = data.get('entryPrice')
        pattern_date = data.get('patternDate')
        
        # Load existing historical data
        history_file = 'pattern_history.json'
        history = []
        if os.path.exists(history_file):
            with open(history_file, 'r') as f:
                history = json.load(f)
        
        # Add new pattern
        history.append({
            'ticker': ticker,
            'timeframe': timeframe,
            'direction': direction,
            'entryPrice': entry_price,
            'patternDate': pattern_date,
            'recordedAt': datetime.now().isoformat(),
            'outcome': 'pending'
        })
        
        # Save
        with open(history_file, 'w') as f:
            json.dump(history, f, indent=2)
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/history', methods=['GET'])
def get_history():
    """Get scan history"""
    try:
        if os.path.exists('scan_history.json'):
            with open('scan_history.json', 'r') as f:
                history = json.load(f)
                return jsonify({
                    'success': True,
                    'history': history
                })
        return jsonify({
            'success': True,
            'history': []
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

def save_scan_to_history(results, min_short, min_gain, min_vol_ratio, min_risk):
    """Save scan to history"""
    try:
        history = []
        if os.path.exists('scan_history.json'):
            with open('scan_history.json', 'r') as f:
                history = json.load(f)
        
        scan_data = {
            'timestamp': datetime.now().isoformat(),
            'criteria': {
                'min_short': min_short,
                'min_gain': min_gain,
                'min_vol_ratio': min_vol_ratio,
                'min_risk': min_risk
            },
            'results_count': len(results),
            'tickers': [r['ticker'] for r in results],
            'top_risk_scores': [{'ticker': r['ticker'], 'score': r['riskScore']} for r in results[:10]],
            'avg_risk_score': sum(r['riskScore'] for r in results) / len(results) if results else 0
        }
        
        history.append(scan_data)
        
        if len(history) > 50:
            history = history[-50:]
        
        with open('scan_history.json', 'w') as f:
            json.dump(history, f, indent=2)
            
    except Exception as e:
        print(f"Error saving history: {e}")

@app.route('/api/volemon-scan', methods=['POST'])
def volemon_scan():
    """
    🔊 VOLEMON - Volume Monster Scanner
    Scans for stocks with 2x or more their average volume
    """
    try:
        data = request.json
        min_volume_multiple = data.get('min_volume_multiple', 2.0)
        
        # Get stock universe - same as daily plays
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
        
        # Add high short stocks
        high_short_stocks = load_stock_data()
        for stock in high_short_stocks:
            if stock['ticker'] not in popular_tickers:
                popular_tickers.append(stock['ticker'])
        
        results = []
        processed = 0
        total = len(popular_tickers)
        
        print(f"\n🔊 Starting Volemon scan for {total} stocks...")
        print(f"   Looking for {min_volume_multiple}x+ volume...")
        
        for ticker in popular_tickers:
            processed += 1
            try:
                stock_data = yf.Ticker(ticker)
                hist = stock_data.history(period='5d')  # Last 5 days
                info = stock_data.info
                
                if len(hist) < 2:
                    continue
                
                # Get current volume and average volume (excluding today)
                current_volume = hist['Volume'].iloc[-1]
                avg_volume = hist['Volume'].iloc[:-1].mean()
                
                if avg_volume == 0 or current_volume == 0:
                    continue
                
                volume_multiple = current_volume / avg_volume
                
                # Filter for stocks with 2x+ volume
                if volume_multiple >= min_volume_multiple:
                    current_price = hist['Close'].iloc[-1]
                    prev_price = hist['Close'].iloc[-2]
                    change_pct = ((current_price - prev_price) / prev_price) * 100
                    
                    company_name = info.get('longName', ticker)
                    market_cap = info.get('marketCap', 0)
                    
                    results.append({
                        'ticker': ticker,
                        'company': company_name,
                        'price': float(current_price),
                        'change': float(change_pct),
                        'volume': int(current_volume),
                        'avg_volume': int(avg_volume),
                        'volume_multiple': float(volume_multiple),
                        'market_cap': int(market_cap)
                    })
                    
                    print(f"   ✅ {ticker}: {volume_multiple:.1f}x volume!")
                
                # Progress indicator
                if processed % 10 == 0:
                    print(f"   Progress: {processed}/{total} stocks scanned...")
                    
            except Exception as e:
                print(f"   ❌ Error scanning {ticker}: {e}")
                continue
        
        # Sort by volume multiple (highest first)
        results.sort(key=lambda x: x['volume_multiple'], reverse=True)
        
        # Limit to top 50
        results = results[:50]
        
        print(f"\n🔊 Volemon scan complete!")
        print(f"   Found {len(results)} stocks with {min_volume_multiple}x+ volume")
        print(f"   Scanned {processed} stocks total\n")
        
        return jsonify({
            'success': True,
            'results': results,
            'count': len(results),
            'scanned': processed
        })
        
    except Exception as e:
        print(f"❌ Volemon scan error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/usuals-scan', methods=['POST'])
def usuals_scan():
    """
    ⭐ USUALS - Your Watchlist Scanner
    Scans specific tickers for volume, patterns (all timeframes), and news
    """
    try:
        data = request.json
        tickers = data.get('tickers', ['SOFI', 'INTC', 'SPY', 'TSLA', 'COIN', 'CDE', 'PLTR', 'AAPL', 'BAC', 'NVDA'])
        
        results = []
        processed = 0
        total = len(tickers)
        
        print(f"\n⭐ Starting Usuals scan for {total} stocks...")
        
        for ticker in tickers:
            processed += 1
            try:
                stock_data = yf.Ticker(ticker)
                info = stock_data.info
                
                # Get data for different timeframes
                hist_5d = stock_data.history(period='5d', interval='1h')  # For hourly
                hist_1mo = stock_data.history(period='1mo')  # For daily
                hist_3mo = stock_data.history(period='3mo')  # For weekly
                hist_60d = stock_data.history(period='60d', interval='1h')  # For 4-hour
                
                if len(hist_1mo) < 3:
                    continue
                
                # Current price and change
                current_price = hist_1mo['Close'].iloc[-1]
                prev_price = hist_1mo['Close'].iloc[-2]
                change_pct = ((current_price - prev_price) / prev_price) * 100
                
                # Volume analysis
                current_volume = hist_1mo['Volume'].iloc[-1]
                avg_volume = hist_1mo['Volume'].iloc[:-1].mean()
                volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1
                
                company_name = info.get('longName', ticker)
                
                # Check patterns on all timeframes
                patterns = {}
                
                # Daily pattern
                if len(hist_1mo) >= 3:
                    has_pattern, pattern_data = check_strat_31(hist_1mo)
                    if has_pattern:
                        patterns['daily'] = {
                            'type': '3-1 Strat',
                            'direction': pattern_data['direction']
                        }
                    else:
                        # Check for "1" (inside bar)
                        current = hist_1mo.iloc[-1]
                        previous = hist_1mo.iloc[-2]
                        is_one = (current['High'] < previous['High'] and current['Low'] > previous['Low'])
                        if is_one:
                            patterns['daily'] = {
                                'type': 'Inside Bar (1)',
                                'direction': 'neutral'
                            }
                        else:
                            patterns['daily'] = None
                else:
                    patterns['daily'] = None
                
                # Weekly pattern (use weekly data)
                hist_weekly = stock_data.history(period='6mo', interval='1wk')
                if len(hist_weekly) >= 3:
                    has_pattern, pattern_data = check_strat_31(hist_weekly)
                    if has_pattern:
                        patterns['weekly'] = {
                            'type': '3-1 Strat',
                            'direction': pattern_data['direction']
                        }
                    else:
                        # Check for "1"
                        current = hist_weekly.iloc[-1]
                        previous = hist_weekly.iloc[-2]
                        is_one = (current['High'] < previous['High'] and current['Low'] > previous['Low'])
                        if is_one:
                            patterns['weekly'] = {
                                'type': 'Inside Bar (1)',
                                'direction': 'neutral'
                            }
                        else:
                            patterns['weekly'] = None
                else:
                    patterns['weekly'] = None
                
                # Hourly pattern
                if len(hist_5d) >= 3:
                    has_pattern, pattern_data = check_strat_31(hist_5d)
                    if has_pattern:
                        patterns['hourly'] = {
                            'type': '3-1 Strat',
                            'direction': pattern_data['direction']
                        }
                    else:
                        # Check for "1"
                        current = hist_5d.iloc[-1]
                        previous = hist_5d.iloc[-2]
                        is_one = (current['High'] < previous['High'] and current['Low'] > previous['Low'])
                        if is_one:
                            patterns['hourly'] = {
                                'type': 'Inside Bar (1)',
                                'direction': 'neutral'
                            }
                        else:
                            patterns['hourly'] = None
                else:
                    patterns['hourly'] = None
                
                # 4-hour pattern (resample hourly to 4H)
                if len(hist_60d) >= 12:  # Need at least 12 hours for 3 4H candles
                    try:
                        # Resample to 4H
                        hist_4h = hist_60d.resample('4H').agg({
                            'Open': 'first',
                            'High': 'max',
                            'Low': 'min',
                            'Close': 'last',
                            'Volume': 'sum'
                        }).dropna()
                        
                        if len(hist_4h) >= 3:
                            has_pattern, pattern_data = check_strat_31(hist_4h)
                            if has_pattern:
                                patterns['four_hour'] = {
                                    'type': '3-1 Strat',
                                    'direction': pattern_data['direction']
                                }
                            else:
                                # Check for "1"
                                current = hist_4h.iloc[-1]
                                previous = hist_4h.iloc[-2]
                                is_one = (current['High'] < previous['High'] and current['Low'] > previous['Low'])
                                if is_one:
                                    patterns['four_hour'] = {
                                        'type': 'Inside Bar (1)',
                                        'direction': 'neutral'
                                    }
                                else:
                                    patterns['four_hour'] = None
                        else:
                            patterns['four_hour'] = None
                    except:
                        patterns['four_hour'] = None
                else:
                    patterns['four_hour'] = None
                
                # Get news (top 2)
                news_list = []
                try:
                    news_data = stock_data.news
                    if news_data and len(news_data) > 0:
                        for item in news_data[:2]:  # Top 2 only
                            # Filter out nonsense/promotional news
                            title = item.get('title', '')
                            # Skip if title has promotional keywords
                            skip_keywords = ['buy now', 'subscribe', 'join', 'free trial', 'webinar', 'advertisement']
                            if not any(keyword in title.lower() for keyword in skip_keywords):
                                news_list.append({
                                    'title': title[:100],  # Limit length
                                    'url': item.get('link', '#'),
                                    'source': item.get('publisher', 'Unknown'),
                                    'time': 'Recent'
                                })
                except:
                    pass
                
                results.append({
                    'ticker': ticker,
                    'company': company_name,
                    'price': float(current_price),
                    'change': float(change_pct),
                    'volume': int(current_volume),
                    'avg_volume': int(avg_volume),
                    'volume_ratio': float(volume_ratio),
                    'patterns': patterns,
                    'news': news_list
                })
                
                print(f"   ✅ {ticker}: Price ${current_price:.2f} | Vol {volume_ratio:.1f}x | Patterns: {sum(1 for p in patterns.values() if p)}")
                
            except Exception as e:
                print(f"   ❌ Error scanning {ticker}: {e}")
                continue
        
        print(f"\n⭐ Usuals scan complete!")
        print(f"   Scanned {processed}/{total} stocks\n")
        
        return jsonify({
            'success': True,
            'results': results,
            'count': len(results)
        })
        
    except Exception as e:
        print(f"❌ Usuals scan error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

if __name__ == '__main__':
    import os
    import ssl
    
    port = int(os.environ.get('PORT', 8080))
    
    print("\n" + "="*60)
    print("🍋 LEMON SQUEEZE WEB APP v2.0 🍋")
    print("="*60)
    print("\n✅ Server starting...")
    
    # Check if SSL certificates exist
    cert_file = 'cert.pem'
    key_file = 'key.pem'
    
    if os.path.exists(cert_file) and os.path.exists(key_file):
        print("🔒 HTTPS enabled!")
        print("📱 Open your browser and go to: https://localhost:8080")
        print("   (You may need to click 'Advanced' and accept the self-signed certificate)")
        
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert_file, key_file)
    else:
        print("⚠️  Running without HTTPS (certificates not found)")
        print("📱 Open your browser and go to: http://localhost:8080")
        print("\n💡 To enable HTTPS, run:")
        print("   openssl req -x509 -newkey rsa:4096 -nodes -out cert.pem -keyout key.pem -days 365")
        context = None
    
    print("\n📊 Features:")
    print("  - Short Squeeze Scanner")
    print("  - Hourly Plays (3-1 Strat)")
    print("  - Daily Plays (3-1 Strat)")
    print("  - Weekly Plays (3-1 Strat)")
    print("  - Crypto Scanner (BTC, ETH, XRP, SOL, DOGE, HYPE)")
    print("  - 🔊 Volemon (Auto Volume Scanner - 2x+ Volume)")
    print("  - ⭐ Usuals (Watchlist Scanner - 15min auto)")
    print("\n🛑 Press Ctrl+C to stop the server")
    print("\n" + "="*60 + "\n")
    
    if context:
        app.run(debug=False, host='0.0.0.0', port=port, ssl_context=context)
    else:
        app.run(debug=False, host='0.0.0.0', port=port)
