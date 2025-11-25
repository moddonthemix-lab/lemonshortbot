"""
🍋 LEMON SQUEEZE WEB APP v3.0 - OPTIMIZED & REDUCED 🍋
Changes:
- Short Squeeze: Top 30 only (from CSV)
- Daily Plays: Keep full list (47 stocks)
- Weekly/Hourly Plays: Daily list + Volemon list combined
- Volemon: Keep full list (33 stocks)
- Usuals: Keep full list (14 stocks)
- Crypto: Keep full list (5 cryptos)

Total API calls reduced from 493-1,393 to ~200 per complete scan!
"""

from flask import Flask, render_template, jsonify, request, send_from_directory, session
import yfinance as yf
from datetime import datetime
import time
import os
import json
import hashlib
import secrets

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)  # Generate secret key for sessions

# Simple user storage (in-memory - for production use a database)
users = {}
user_favorites = {}

# Load high short interest stocks
def load_stock_data():
    """Load stocks from CSV - LIMITED TO TOP 30"""
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
    
    # LIMIT TO TOP 30 HIGHEST SHORT INTEREST
    stocks.sort(key=lambda x: x['short_interest'], reverse=True)
    return stocks[:30]

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

# COMBINED STOCK LIST FOR WEEKLY/HOURLY PLAYS
def get_combined_weekly_hourly_list():
    """
    Combine Daily Plays + Volemon lists for Weekly/Hourly scans
    Remove duplicates
    """
    daily_plays = [
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
    
    volemon = [
        'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'META', 'NVDA', 'AMD',
        'SPY', 'QQQ', 'IWM', 'DIA',
        'NFLX', 'DIS', 'BABA', 'PYPL', 'SQ', 'ROKU', 'SNAP', 'UBER',
        'F', 'GM', 'NIO', 'LCID', 'RIVN',
        'JPM', 'BAC', 'GS', 'MS', 'C',
        'XOM', 'CVX', 'COP', 'SLB',
    ]
    
    # Combine and remove duplicates
    combined = list(set(daily_plays + volemon))
    return sorted(combined)

@app.route('/')
def index():
    """Serve the main page"""
    html_files = [
        'lemon_squeeze_complete_with_chat.html',
        'lemon_squeeze_with_volemon__4_.html',
        'lemon_squeeze_webapp.html',
        'lemon_squeeze.html',
        'index.html'
    ]
    
    for html_file in html_files:
        if os.path.exists(html_file):
            return send_from_directory('.', html_file)
    
    return "<h1>🍋 Lemon Squeeze - Optimized Backend!</h1>"

# ===== AUTHENTICATION ENDPOINTS =====

def hash_password(password):
    """Simple password hashing"""
    return hashlib.sha256(password.encode()).hexdigest()

@app.route('/api/auth/signup', methods=['POST'])
def signup():
    """User signup endpoint"""
    try:
        data = request.json
        name = data.get('name', '').strip()
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        
        if not name or not email or not password:
            return jsonify({'success': False, 'error': 'All fields are required'}), 400
        
        if email in users:
            return jsonify({'success': False, 'error': 'Email already registered'}), 400
        
        if len(password) < 6:
            return jsonify({'success': False, 'error': 'Password must be at least 6 characters'}), 400
        
        # Create user
        users[email] = {
            'name': name,
            'email': email,
            'password': hash_password(password),
            'created_at': datetime.now().isoformat()
        }
        
        # Initialize favorites
        user_favorites[email] = []
        
        # Create session
        session['user_email'] = email
        
        return jsonify({
            'success': True,
            'user': {
                'name': name,
                'email': email
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/auth/signin', methods=['POST'])
def signin():
    """User signin endpoint"""
    try:
        data = request.json
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        
        if not email or not password:
            return jsonify({'success': False, 'error': 'Email and password required'}), 400
        
        if email not in users:
            return jsonify({'success': False, 'error': 'Invalid email or password'}), 401
        
        if users[email]['password'] != hash_password(password):
            return jsonify({'success': False, 'error': 'Invalid email or password'}), 401
        
        # Create session
        session['user_email'] = email
        
        return jsonify({
            'success': True,
            'user': {
                'name': users[email]['name'],
                'email': email
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/auth/me', methods=['GET'])
def get_current_user():
    """Get current logged-in user"""
    try:
        user_email = session.get('user_email')
        
        if not user_email or user_email not in users:
            return jsonify({'success': False, 'error': 'Not authenticated'}), 401
        
        return jsonify({
            'success': True,
            'user': {
                'name': users[user_email]['name'],
                'email': user_email
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/auth/signout', methods=['POST'])
def signout():
    """User signout endpoint"""
    try:
        session.pop('user_email', None)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/favorites', methods=['GET'])
def get_favorites():
    """Get user's favorites"""
    try:
        user_email = session.get('user_email')
        
        if not user_email:
            return jsonify({'success': False, 'error': 'Not authenticated'}), 401
        
        favorites = user_favorites.get(user_email, [])
        
        return jsonify({
            'success': True,
            'favorites': favorites
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/favorites', methods=['POST'])
def add_favorite():
    """Add a favorite stock"""
    try:
        user_email = session.get('user_email')
        
        if not user_email:
            return jsonify({'success': False, 'error': 'Not authenticated'}), 401
        
        data = request.json
        ticker = data.get('ticker', '').strip().upper()
        company = data.get('company', '').strip()
        timeframe = data.get('timeframe', '').strip()
        
        if not ticker:
            return jsonify({'success': False, 'error': 'Ticker required'}), 400
        
        if user_email not in user_favorites:
            user_favorites[user_email] = []
        
        # Check if already favorited
        for fav in user_favorites[user_email]:
            if fav['ticker'] == ticker and fav['timeframe'] == timeframe:
                return jsonify({'success': False, 'error': 'Already in favorites'}), 400
        
        # Add favorite
        favorite = {
            'ticker': ticker,
            'company': company,
            'timeframe': timeframe,
            'added_at': datetime.now().isoformat()
        }
        
        user_favorites[user_email].append(favorite)
        
        return jsonify({
            'success': True,
            'favorite': favorite
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/favorites/<ticker>/<timeframe>', methods=['DELETE'])
def remove_favorite(ticker, timeframe):
    """Remove a favorite stock"""
    try:
        user_email = session.get('user_email')
        
        if not user_email:
            return jsonify({'success': False, 'error': 'Not authenticated'}), 401
        
        if user_email not in user_favorites:
            return jsonify({'success': False, 'error': 'No favorites found'}), 404
        
        # Remove favorite
        user_favorites[user_email] = [
            fav for fav in user_favorites[user_email]
            if not (fav['ticker'] == ticker.upper() and fav['timeframe'] == timeframe)
        ]
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ===== END AUTHENTICATION ENDPOINTS =====

@app.route('/api/scan', methods=['POST'])
def scan():
    """API endpoint to scan for squeeze candidates - TOP 30 ONLY"""
    try:
        data = request.json
        min_short = float(data.get('minShort', 25))
        min_gain = float(data.get('minGain', 15))
        min_vol_ratio = float(data.get('minVolRatio', 1.5))
        min_risk = float(data.get('minRisk', 60))
        
        stocks = load_stock_data()  # Already limited to top 30
        results = []
        
        print(f"\n🔍 Short Squeeze Scan - Top {len(stocks)} stocks...")
        
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
        
        print(f"✅ Found {len(results)} squeeze candidates\n")
        
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
    """Daily plays scanner - KEEP FULL LIST (47 stocks)"""
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
        
        print(f"\n🎯 Daily Plays scan - {total} stocks...")
        
        for i, ticker in enumerate(popular_tickers, 1):
            try:
                time.sleep(0.7)
                
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
                            'pattern': pattern_data,
                            'timeframe': 'daily'
                        })
                        
                        print(f"✅ {ticker}: {pattern_data['direction']} ({i}/{total})")
                
            except Exception as e:
                print(f"❌ {ticker}: {e}")
                continue
        
        print(f"✅ Found {len(results)} daily patterns\n")
        
        return jsonify({
            'success': True,
            'results': results,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/weekly-plays', methods=['POST'])
def weekly_plays():
    """Weekly plays scanner - COMBINED DAILY + VOLEMON LIST"""
    try:
        combined_tickers = get_combined_weekly_hourly_list()
        results = []
        
        print(f"\n📅 Weekly Plays scan - {len(combined_tickers)} stocks...")
        
        for ticker in combined_tickers:
            try:
                time.sleep(0.7)
                
                stock_data = yf.Ticker(ticker)
                hist = stock_data.history(period='3mo')
                
                if len(hist) >= 3:
                    # Resample to weekly
                    weekly = hist.resample('W').agg({
                        'Open': 'first',
                        'High': 'max',
                        'Low': 'min',
                        'Close': 'last',
                        'Volume': 'sum'
                    })
                    
                    has_pattern, pattern_data = check_strat_31(weekly)
                    
                    if has_pattern:
                        current_price = hist['Close'].iloc[-1]
                        results.append({
                            'ticker': ticker,
                            'company': ticker,
                            'currentPrice': float(current_price),
                            'volume': int(hist['Volume'].iloc[-1]),
                            'pattern': pattern_data,
                            'timeframe': 'weekly'
                        })
                        print(f"✅ {ticker}")
            except:
                continue
        
        print(f"✅ Found {len(results)} weekly patterns\n")
        
        return jsonify({'success': True, 'results': results})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/hourly-plays', methods=['POST'])
def hourly_plays():
    """Hourly plays scanner - COMBINED DAILY + VOLEMON LIST"""
    try:
        combined_tickers = get_combined_weekly_hourly_list()
        results = []
        
        print(f"\n⏰ Hourly Plays scan - {len(combined_tickers)} stocks...")
        
        for ticker in combined_tickers:
            try:
                time.sleep(0.7)
                
                stock_data = yf.Ticker(ticker)
                hist = stock_data.history(period='5d', interval='1h')
                
                if len(hist) >= 3:
                    has_pattern, pattern_data = check_strat_31(hist)
                    
                    if has_pattern:
                        current_price = hist['Close'].iloc[-1]
                        results.append({
                            'ticker': ticker,
                            'company': ticker,
                            'currentPrice': float(current_price),
                            'volume': int(hist['Volume'].iloc[-1]),
                            'pattern': pattern_data,
                            'timeframe': 'hourly'
                        })
                        print(f"✅ {ticker}")
            except:
                continue
        
        print(f"✅ Found {len(results)} hourly patterns\n")
        
        return jsonify({'success': True, 'results': results})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/crypto-plays', methods=['POST'])
def crypto_plays():
    """Crypto scanner - KEEP FULL LIST (5 cryptos)"""
    try:
        crypto_tickers = {
            'BTC-USD': 'Bitcoin',
            'ETH-USD': 'Ethereum',
            'XRP-USD': 'Ripple',
            'SOL-USD': 'Solana',
            'DOGE-USD': 'Dogecoin'
        }
        
        results = []
        
        print(f"\n₿ Crypto scan - {len(crypto_tickers)} cryptos...")
        
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
                        print(f"✅ {name}")
            except:
                continue
        
        print(f"✅ Found {len(results)} crypto patterns\n")
        
        return jsonify({'success': True, 'results': results})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/volemon-scan', methods=['POST'])
def volemon_scan():
    """Volemon volume scanner - KEEP FULL LIST (33 stocks)"""
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
        
        print(f"\n🔊 Volemon scan - {len(popular_tickers)} stocks...")
        
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
    """Usuals watchlist scanner - KEEP FULL LIST (14 stocks default)"""
    try:
        data = request.json or {}
        tickers = data.get('tickers', ['SOFI', 'INTC', 'SPY', 'TSLA', 'COIN', 'CDE', 'PLTR', 'AAPL', 'BAC', 'NVDA', 'GOOGL', 'META', 'MSFT', 'UNH'])
        
        results = []
        
        print(f"\n⭐ Usuals scan - {len(tickers)} stocks...")
        
        for ticker in tickers:
            try:
                time.sleep(0.7)
                
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
    print("🍋 LEMON SQUEEZE WEB APP v3.0 - OPTIMIZED 🍋")
    print("="*60)
    print("\n📊 Stock Counts:")
    print("  - Short Squeeze: Top 30 (highest short interest)")
    print("  - Daily Plays: 47 stocks")
    print("  - Weekly/Hourly: 47 stocks (combined list)")
    print("  - Volemon: 33 stocks")
    print("  - Usuals: 14 stocks (default)")
    print("  - Crypto: 5 cryptos")
    print("\n✅ Total API calls reduced by ~67%!")
    print("📱 http://localhost:8080")
    print("\n🛑 Press Ctrl+C to stop")
    print("\n" + "="*60 + "\n")
    
    app.run(debug=True, host='0.0.0.0', port=port)
