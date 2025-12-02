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
import requests
from collections import deque

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)

# ===== TRADIER API (OPTIONAL FALLBACK) =====
TRADIER_API_KEY = os.environ.get('TRADIER_API_KEY', '')
USE_TRADIER_FIRST = os.environ.get('USE_TRADIER_FIRST', 'false').lower() == 'true'
TRADIER_BASE_URL = 'https://api.tradier.com/v1'
tradier_call_times = deque()

def can_call_tradier():
    """Rate limiter: 120 calls per minute with warnings"""
    if not TRADIER_API_KEY:
        return False
    now = time.time()
    # Clean up old calls (older than 60 seconds)
    while tradier_call_times and tradier_call_times[0] < now - 60:
        tradier_call_times.popleft()

    calls_in_last_minute = len(tradier_call_times)

    # Warn if approaching limit
    if calls_in_last_minute >= 100:
        print(f"⚠️  Tradier rate limit warning: {calls_in_last_minute}/120 calls used in last minute")

    # Hard limit at 120 calls per minute
    if calls_in_last_minute >= 120:
        print(f"🛑 Tradier rate limit reached! Waiting...")
        return False

    return True

def get_tradier_quote(ticker):
    """Get data from Tradier API with rate limiting"""
    if not can_call_tradier():
        # If at limit, wait a bit and try once more
        time.sleep(2)
        if not can_call_tradier():
            return None

    try:
        response = requests.get(
            f'{TRADIER_BASE_URL}/markets/quotes',
            params={'symbols': ticker},
            headers={'Authorization': f'Bearer {TRADIER_API_KEY}', 'Accept': 'application/json'},
            timeout=5
        )
        tradier_call_times.append(time.time())

        if response.status_code == 200:
            data = response.json()
            if 'quotes' in data and 'quote' in data['quotes']:
                quote = data['quotes']['quote']
                if isinstance(quote, dict) and quote.get('last'):
                    return quote
        elif response.status_code == 429:
            print(f"⚠️  Tradier rate limit hit for {ticker}")
    except Exception as e:
        print(f"⚠️  Tradier error for {ticker}: {str(e)[:50]}")

    return None

def safe_yf_ticker(ticker, period='3mo', interval='1d', max_retries=3):
    """Get stock data with retries and better error handling

    If USE_TRADIER_FIRST=true, tries Tradier first, then Yahoo as fallback
    Otherwise, tries Yahoo first with Tradier as fallback
    """
    import pandas as pd

    def get_tradier_data():
        """Helper to fetch and format Tradier data"""
        quote = get_tradier_quote(ticker)
        if quote:
            hist = pd.DataFrame({
                'Close': [float(quote.get('prevclose', 0) or 0), float(quote.get('last', 0) or 0)],
                'Volume': [int(quote.get('average_volume', 0) or 0)] * 2,
                'High': [float(quote.get('last', 0) or 0)] * 2,
                'Low': [float(quote.get('last', 0) or 0) * 0.99] * 2
            })
            info = {
                'symbol': ticker,
                'shortName': ticker,
                'marketCap': quote.get('market_cap', 0),
                'floatShares': 0,  # Tradier doesn't provide this
                'sharesOutstanding': 0,
                'fiftyTwoWeekHigh': float(quote.get('week_52_high', 0) or 0),
                'fiftyTwoWeekLow': float(quote.get('week_52_low', 0) or 0)
            }
            class Wrapper:
                def __init__(self, i):
                    self.info = i
            return Wrapper(info), hist, info
        return None, None, None

    # MODE 1: Tradier First (if Yahoo Finance is broken)
    if USE_TRADIER_FIRST and TRADIER_API_KEY:
        print(f"🔄 {ticker}: Trying Tradier first...")
        stock_data, hist, info = get_tradier_data()
        if stock_data:
            print(f"✅ {ticker}: Tradier SUCCESS")
            return stock_data, hist, info
        else:
            print(f"⚠️  {ticker}: Tradier failed, trying Yahoo...")

    # MODE 2: Yahoo First (default behavior)
    for attempt in range(max_retries):
        try:
            # Progressive delay: 0.5s, 1.5s, 3.5s
            wait_time = 0.5 * (2 ** attempt)
            time.sleep(wait_time)

            # Create ticker object
            stock = yf.Ticker(ticker)

            # Try to get historical data
            hist = stock.history(period=period, interval=interval)

            # Check if we got valid data
            if hist is not None and len(hist) >= 2:
                try:
                    # Try to get info, but don't fail if it doesn't work
                    info = stock.info if hasattr(stock, 'info') else {}
                except:
                    info = {'symbol': ticker, 'shortName': ticker}

                print(f"✅ {ticker}: Yahoo (attempt {attempt + 1})")
                return stock, hist, info

            # Empty or invalid data
            if attempt < max_retries - 1:
                print(f"⚠️  {ticker}: Empty data, retry {attempt + 1}/{max_retries}")
                continue

        except Exception as e:
            error_msg = str(e)
            if attempt < max_retries - 1:
                print(f"⚠️  {ticker}: Error on attempt {attempt + 1}/{max_retries}: {error_msg[:100]}")
                continue
            else:
                print(f"❌ {ticker}: All Yahoo retries failed - {error_msg[:100]}")

    # All retries exhausted - try Tradier as fallback (if not already tried)
    if TRADIER_API_KEY and not USE_TRADIER_FIRST:
        print(f"🔄 {ticker}: Trying Tradier fallback...")
        stock_data, hist, info = get_tradier_data()
        if stock_data:
            print(f"✅ {ticker}: Tradier fallback SUCCESS")
            return stock_data, hist, info

    return None, None, None

# Simple user storage (in-memory - for production use a database)
users = {}
user_favorites = {}
user_journal = {}  # {email: [journal_entries]}
chat_messages = []  # Global chat messages

# Scan results cache for #lemonplays bot
scan_cache = {
    'squeeze': {'results': [], 'timestamp': None, 'timeframe': '3mo'},
    'daily': {'results': [], 'timestamp': None, 'timeframe': '1d'},
    'weekly': {'results': [], 'timestamp': None, 'timeframe': '5d'},
    'hourly': {'results': [], 'timestamp': None, 'timeframe': '1d'},
    'volemon': {'results': [], 'timestamp': None, 'timeframe': '5d'},
    'usuals': {'results': [], 'timestamp': None, 'timeframe': '5d'},
    'crypto': {'results': [], 'timestamp': None, 'timeframe': '7d'}
}

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
            # Allow guest mode - return success with no user
            return jsonify({'success': True, 'user': None})
        
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

@app.route('/api/auth/delete', methods=['DELETE'])
def delete_account():
    """Delete user account and all associated data"""
    try:
        user_email = session.get('user_email')

        if not user_email:
            return jsonify({'success': False, 'error': 'Not authenticated'}), 401

        # Delete user data
        if user_email in users:
            del users[user_email]

        if user_email in user_favorites:
            del user_favorites[user_email]

        if user_email in user_journal:
            del user_journal[user_email]

        # Delete user's chat messages
        global chat_messages
        chat_messages = [msg for msg in chat_messages if msg['email'] != user_email]

        # Clear session
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

# ===== TRADING JOURNAL ENDPOINTS =====

@app.route('/api/journal/entries', methods=['GET'])
def get_journal_entries():
    """Get user's journal entries"""
    try:
        user_email = session.get('user_email')

        if not user_email:
            return jsonify({'success': False, 'error': 'Not authenticated'}), 401

        entries = user_journal.get(user_email, [])

        # Sort by date (newest first)
        entries.sort(key=lambda x: x.get('createdAt', ''), reverse=True)

        return jsonify({
            'success': True,
            'entries': entries
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/journal/entry', methods=['POST'])
def add_journal_entry():
    """Add a journal entry"""
    try:
        user_email = session.get('user_email')

        if not user_email:
            return jsonify({'success': False, 'error': 'Not authenticated'}), 401

        data = request.json

        # Validate required fields
        required = ['ticker', 'date', 'type', 'entryPrice', 'positionSize', 'outcome']
        for field in required:
            if field not in data:
                return jsonify({'success': False, 'error': f'Missing field: {field}'}), 400

        # Create entry
        entry = {
            'id': hashlib.md5(f"{user_email}{data['ticker']}{data['createdAt']}".encode()).hexdigest()[:12],
            'ticker': data['ticker'].upper(),
            'date': data['date'],
            'type': data['type'],
            'entryPrice': float(data['entryPrice']),
            'exitPrice': float(data['exitPrice']) if data.get('exitPrice') else None,
            'positionSize': int(data['positionSize']),
            'outcome': data['outcome'],
            'notes': data.get('notes', ''),
            'createdAt': data.get('createdAt', datetime.now().isoformat())
        }

        # Initialize user's journal if not exists
        if user_email not in user_journal:
            user_journal[user_email] = []

        user_journal[user_email].append(entry)

        return jsonify({
            'success': True,
            'entry': entry
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/journal/entry/<entry_id>', methods=['PUT'])
def update_journal_entry(entry_id):
    """Update a journal entry"""
    try:
        user_email = session.get('user_email')

        if not user_email:
            return jsonify({'success': False, 'error': 'Not authenticated'}), 401

        if user_email not in user_journal:
            return jsonify({'success': False, 'error': 'No journal entries found'}), 404

        data = request.json

        # Find and update entry
        for entry in user_journal[user_email]:
            if entry['id'] == entry_id:
                # Update fields
                if 'exitPrice' in data:
                    entry['exitPrice'] = float(data['exitPrice']) if data['exitPrice'] else None
                if 'outcome' in data:
                    entry['outcome'] = data['outcome']
                if 'notes' in data:
                    entry['notes'] = data['notes']

                return jsonify({
                    'success': True,
                    'entry': entry
                })

        return jsonify({'success': False, 'error': 'Entry not found'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/journal/entry/<entry_id>', methods=['DELETE'])
def delete_journal_entry(entry_id):
    """Delete a journal entry"""
    try:
        user_email = session.get('user_email')

        if not user_email:
            return jsonify({'success': False, 'error': 'Not authenticated'}), 401

        if user_email not in user_journal:
            return jsonify({'success': False, 'error': 'No journal entries found'}), 404

        # Remove entry
        user_journal[user_email] = [
            entry for entry in user_journal[user_email]
            if entry['id'] != entry_id
        ]

        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ===== CHAT ENDPOINTS =====

def generate_lemonplays_report():
    """Generate bot response for #lemonplays command"""
    report_lines = ["📊 **Latest LemonPlays Scan Results**\n"]

    # Check if any scans have been run
    has_results = any(cache['timestamp'] is not None for cache in scan_cache.values())

    if not has_results:
        return "No scans have been run yet. Run a scan to see patterns!"

    # Short Squeeze Scanner
    if scan_cache['squeeze']['results']:
        count = len(scan_cache['squeeze']['results'])
        timeframe = scan_cache['squeeze']['timeframe']
        timestamp = scan_cache['squeeze']['timestamp']
        age = format_time_ago(timestamp)
        top_tickers = [r['ticker'] for r in scan_cache['squeeze']['results'][:3]]
        report_lines.append(f"🎯 **Short Squeeze** ({timeframe}): {count} candidates {age}")
        if top_tickers:
            report_lines.append(f"   Top: {', '.join(top_tickers)}")

    # Daily Plays
    if scan_cache['daily']['results']:
        count = len(scan_cache['daily']['results'])
        timeframe = scan_cache['daily']['timeframe']
        age = format_time_ago(scan_cache['daily']['timestamp'])
        report_lines.append(f"\n📅 **Daily Plays** ({timeframe}): {count} patterns {age}")
        for r in scan_cache['daily']['results'][:10]:  # Show top 10
            ticker = r['ticker']
            direction = r.get('pattern', {}).get('direction', 'unknown')
            pattern_type = r.get('pattern', {}).get('type', 'Pattern')
            report_lines.append(f"   {ticker}: {direction.title()} {pattern_type}")

    # Weekly Plays
    if scan_cache['weekly']['results']:
        count = len(scan_cache['weekly']['results'])
        timeframe = scan_cache['weekly']['timeframe']
        age = format_time_ago(scan_cache['weekly']['timestamp'])
        report_lines.append(f"\n📆 **Weekly Plays** ({timeframe}): {count} patterns {age}")

    # Hourly Plays
    if scan_cache['hourly']['results']:
        count = len(scan_cache['hourly']['results'])
        timeframe = scan_cache['hourly']['timeframe']
        age = format_time_ago(scan_cache['hourly']['timestamp'])
        report_lines.append(f"\n⏰ **Hourly Plays** ({timeframe}): {count} patterns {age}")

    # Volemon
    if scan_cache['volemon']['results']:
        count = len(scan_cache['volemon']['results'])
        timeframe = scan_cache['volemon']['timeframe']
        age = format_time_ago(scan_cache['volemon']['timestamp'])
        top_vol = scan_cache['volemon']['results'][:3]
        report_lines.append(f"\n🔊 **Volemon** ({timeframe}): {count} high volume stocks {age}")
        for stock in top_vol:
            ticker = stock['ticker']
            vol_mult = stock['volume_multiple']
            report_lines.append(f"   {ticker}: {vol_mult:.1f}x volume")

    # Usuals
    if scan_cache['usuals']['results']:
        count = len(scan_cache['usuals']['results'])
        timeframe = scan_cache['usuals']['timeframe']
        age = format_time_ago(scan_cache['usuals']['timestamp'])
        report_lines.append(f"\n⭐ **Usuals** ({timeframe}): {count} stocks scanned {age}")

    # Crypto
    if scan_cache['crypto']['results']:
        count = len(scan_cache['crypto']['results'])
        timeframe = scan_cache['crypto']['timeframe']
        age = format_time_ago(scan_cache['crypto']['timestamp'])
        tickers = [r['ticker'] for r in scan_cache['crypto']['results']]
        report_lines.append(f"\n₿ **Crypto** ({timeframe}): {count} patterns {age}")
        if tickers:
            report_lines.append(f"   {', '.join(tickers)}")

    return '\n'.join(report_lines)

def format_time_ago(timestamp):
    """Format timestamp as 'X mins/hours ago'"""
    if timestamp is None:
        return "never"

    now = datetime.now()
    delta = now - timestamp

    if delta.total_seconds() < 60:
        return "just now"
    elif delta.total_seconds() < 3600:
        mins = int(delta.total_seconds() / 60)
        return f"{mins}m ago"
    elif delta.total_seconds() < 86400:
        hours = int(delta.total_seconds() / 3600)
        return f"{hours}h ago"
    else:
        days = int(delta.total_seconds() / 86400)
        return f"{days}d ago"

@app.route('/api/chat/messages', methods=['GET'])
def get_chat_messages():
    """Get all chat messages (last 100)"""
    try:
        user_email = session.get('user_email')

        if not user_email:
            return jsonify({'success': False, 'error': 'Not authenticated'}), 401

        # Return last 100 messages
        messages = chat_messages[-100:] if len(chat_messages) > 100 else chat_messages

        return jsonify({
            'success': True,
            'messages': messages
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/chat/message', methods=['POST'])
def send_chat_message():
    """Send a chat message"""
    try:
        user_email = session.get('user_email')

        if not user_email:
            return jsonify({'success': False, 'error': 'Not authenticated'}), 401

        if user_email not in users:
            return jsonify({'success': False, 'error': 'User not found'}), 404

        data = request.json
        message = data.get('message', '').strip()

        if not message:
            return jsonify({'success': False, 'error': 'Message cannot be empty'}), 400

        if len(message) > 500:
            return jsonify({'success': False, 'error': 'Message too long (max 500 characters)'}), 400

        # Create message
        msg = {
            'id': hashlib.md5(f"{user_email}{time.time()}".encode()).hexdigest()[:12],
            'email': user_email,
            'name': users[user_email]['name'],
            'message': message,
            'timestamp': datetime.now().isoformat()
        }

        chat_messages.append(msg)

        # Keep only last 500 messages in memory
        if len(chat_messages) > 500:
            chat_messages.pop(0)

        # Check for #lemonplays bot command
        if '#lemonplays' in message.lower():
            bot_response = generate_lemonplays_report()
            bot_msg = {
                'id': hashlib.md5(f"bot{time.time()}".encode()).hexdigest()[:12],
                'email': 'bot@lemonshort.com',
                'name': '🍋 LemonBot',
                'message': bot_response,
                'timestamp': datetime.now().isoformat()
            }
            chat_messages.append(bot_msg)

        return jsonify({
            'success': True,
            'message': msg
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/chat/message/<message_id>', methods=['DELETE'])
def delete_chat_message(message_id):
    """Delete a chat message (only by the sender)"""
    try:
        user_email = session.get('user_email')

        if not user_email:
            return jsonify({'success': False, 'error': 'Not authenticated'}), 401

        # Find the message
        global chat_messages
        message = next((msg for msg in chat_messages if msg['id'] == message_id), None)

        if not message:
            return jsonify({'success': False, 'error': 'Message not found'}), 404

        # Check if user owns the message
        if message['email'] != user_email:
            return jsonify({'success': False, 'error': 'Not authorized to delete this message'}), 403

        # Delete the message
        chat_messages = [msg for msg in chat_messages if msg['id'] != message_id]

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
                stock_data, hist, info = safe_yf_ticker(ticker)

                if stock_data and hist is not None and len(hist) >= 2:
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

        # Cache results for #lemonplays bot
        timestamp = datetime.now()
        scan_cache['squeeze']['results'] = results
        scan_cache['squeeze']['timestamp'] = timestamp

        return jsonify({
            'success': True,
            'results': results,
            'timestamp': timestamp.isoformat()
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
                stock_data, hist, info = safe_yf_ticker(ticker)

                if stock_data and hist is not None and len(hist) >= 3:
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

        # Cache results for #lemonplays bot
        timestamp = datetime.now()
        scan_cache['daily']['results'] = results
        scan_cache['daily']['timestamp'] = timestamp

        return jsonify({
            'success': True,
            'results': results,
            'timestamp': timestamp.isoformat()
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
                stock_data, hist, info = safe_yf_ticker(ticker)

                if stock_data and hist is not None and len(hist) >= 3:
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

        # Cache results for #lemonplays bot
        scan_cache['weekly']['results'] = results
        scan_cache['weekly']['timestamp'] = datetime.now()

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
                stock_data, hist, info = safe_yf_ticker(ticker, period='5d', interval='1h')

                if stock_data and hist is not None and len(hist) >= 3:
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

        # Cache results for #lemonplays bot
        scan_cache['hourly']['results'] = results
        scan_cache['hourly']['timestamp'] = datetime.now()

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
                stock_data, hist, info = safe_yf_ticker(ticker, period='1mo')

                if stock_data and hist is not None and len(hist) >= 3:
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

        # Cache results for #lemonplays bot
        scan_cache['crypto']['results'] = results
        scan_cache['crypto']['timestamp'] = datetime.now()

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
                stock_data, hist, info = safe_yf_ticker(ticker, period='5d')

                if stock_data and hist is not None and len(hist) >= 2:
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

        # Cache results for #lemonplays bot
        scan_cache['volemon']['results'] = results[:50]
        scan_cache['volemon']['timestamp'] = datetime.now()

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
                stock_data, hist, info = safe_yf_ticker(ticker)
                
                if stock_data and hist is not None and len(hist) >= 3:
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

                    # Fetch news (top 3 articles)
                    news_articles = []
                    try:
                        if hasattr(stock_data, 'news') and stock_data.news:
                            for article in stock_data.news[:3]:
                                # Debug: print article keys to see what's available
                                if not news_articles:  # Only print once
                                    print(f"📰 {ticker} news fields: {article.keys()}")

                                # Try different possible field names
                                title = (article.get('title') or
                                        article.get('headline') or
                                        article.get('summary') or
                                        'No title')

                                link = (article.get('link') or
                                       article.get('url') or
                                       article.get('guid') or
                                       '')

                                publisher = (article.get('publisher') or
                                           article.get('source') or
                                           article.get('providerName') or
                                           'Unknown')

                                published = (article.get('providerPublishTime') or
                                           article.get('publishedAt') or
                                           article.get('timestamp') or
                                           0)

                                news_articles.append({
                                    'title': title,
                                    'link': link,
                                    'publisher': publisher,
                                    'published': published
                                })
                    except Exception as news_error:
                        print(f"⚠️  {ticker} news error: {news_error}")

                    results.append({
                        'ticker': ticker,
                        'company': info.get('longName', ticker),
                        'price': float(current_price),
                        'change': float(change),
                        'volume': int(current_volume),
                        'avg_volume': int(avg_volume),
                        'volume_ratio': float(volume_ratio),
                        'patterns': patterns,
                        'news': news_articles
                    })
                    
                    print(f"✅ {ticker}")
                    
            except Exception as e:
                print(f"⚠️  {ticker}: {e}")
                continue
        
        print(f"✅ Done! {len(results)} stocks\n")

        # Cache results for #lemonplays bot
        scan_cache['usuals']['results'] = results
        scan_cache['usuals']['timestamp'] = datetime.now()

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

    # Tradier API status
    print("\n📡 Data Sources:")
    if TRADIER_API_KEY:
        if USE_TRADIER_FIRST:
            print("  ✅ Tradier API: ACTIVE (PRIMARY)")
            print("  ⚠️  Yahoo Finance: Fallback only")
            print("  ⚡ Rate Limit: 120 calls/minute")
        else:
            print("  ✅ Yahoo Finance: PRIMARY")
            print("  ✅ Tradier API: Available as fallback")
            print("  ⚡ Rate Limit: 120 calls/minute")
    else:
        print("  ✅ Yahoo Finance: Only source")
        print("  ℹ️  Set TRADIER_API_KEY for backup data source")
        print("  📖 See TRADIER_SETUP.md for instructions")

    print("\n📱 http://localhost:8080")
    print("\n🛑 Press Ctrl+C to stop")
    print("\n" + "="*60 + "\n")

    app.run(debug=True, host='0.0.0.0', port=port)
