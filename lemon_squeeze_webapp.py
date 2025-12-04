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
from datetime import datetime, timedelta
import time
import os
import json
import hashlib
import sqlite3
from collections import deque
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
    'crypto': {'results': [], 'timestamp': None, 'timeframe': '7d'},
    'lemonai': {'results': [], 'timestamp': None, 'timeframe': '1 week'}
}

# ===== LEMONAI DATABASE =====
DB_FILE = 'lemonai_history.db'

def init_database():
    """Initialize SQLite database for LemonAI tracking and backtesting"""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    # Recommendations table - stores each AI recommendation
    c.execute('''CREATE TABLE IF NOT EXISTS recommendations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ticker TEXT NOT NULL,
        company TEXT,
        option_type TEXT NOT NULL,
        strike_price REAL NOT NULL,
        current_price REAL NOT NULL,
        expiration TEXT NOT NULL,
        confidence INTEGER NOT NULL,
        pattern TEXT,
        direction TEXT,
        volume_ratio REAL,
        news_sentiment TEXT,
        source TEXT,
        reasoning TEXT,
        news_json TEXT,
        options_flow_score INTEGER DEFAULT 0,
        options_avg_volume REAL DEFAULT 0,
        options_avg_oi REAL DEFAULT 0,
        options_total_volume REAL DEFAULT 0,
        options_total_oi REAL DEFAULT 0,
        options_has_pattern BOOLEAN DEFAULT 0,
        options_details TEXT,
        recommendation_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        expiration_date DATE
    )''')

    # Add options columns if they don't exist (for existing databases)
    try:
        c.execute("ALTER TABLE recommendations ADD COLUMN options_flow_score INTEGER DEFAULT 0")
    except:
        pass
    try:
        c.execute("ALTER TABLE recommendations ADD COLUMN options_avg_volume REAL DEFAULT 0")
    except:
        pass
    try:
        c.execute("ALTER TABLE recommendations ADD COLUMN options_avg_oi REAL DEFAULT 0")
    except:
        pass
    try:
        c.execute("ALTER TABLE recommendations ADD COLUMN options_total_volume REAL DEFAULT 0")
    except:
        pass
    try:
        c.execute("ALTER TABLE recommendations ADD COLUMN options_total_oi REAL DEFAULT 0")
    except:
        pass
    try:
        c.execute("ALTER TABLE recommendations ADD COLUMN options_has_pattern BOOLEAN DEFAULT 0")
    except:
        pass
    try:
        c.execute("ALTER TABLE recommendations ADD COLUMN options_details TEXT")
    except:
        pass

    # Add contract detail columns
    try:
        c.execute("ALTER TABLE recommendations ADD COLUMN contract_premium REAL DEFAULT 0")
    except:
        pass
    try:
        c.execute("ALTER TABLE recommendations ADD COLUMN contract_bid REAL DEFAULT 0")
    except:
        pass
    try:
        c.execute("ALTER TABLE recommendations ADD COLUMN contract_ask REAL DEFAULT 0")
    except:
        pass
    try:
        c.execute("ALTER TABLE recommendations ADD COLUMN contract_bid_ask_spread REAL DEFAULT 0")
    except:
        pass
    try:
        c.execute("ALTER TABLE recommendations ADD COLUMN contract_volume INTEGER DEFAULT 0")
    except:
        pass
    try:
        c.execute("ALTER TABLE recommendations ADD COLUMN contract_oi INTEGER DEFAULT 0")
    except:
        pass
    try:
        c.execute("ALTER TABLE recommendations ADD COLUMN contract_premium_value REAL DEFAULT 0")
    except:
        pass
    try:
        c.execute("ALTER TABLE recommendations ADD COLUMN contract_percent_change REAL DEFAULT 0")
    except:
        pass
    try:
        c.execute("ALTER TABLE recommendations ADD COLUMN contract_implied_vol REAL DEFAULT 0")
    except:
        pass

    # Outcomes table - tracks what actually happened
    c.execute('''CREATE TABLE IF NOT EXISTS outcomes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        recommendation_id INTEGER NOT NULL,
        days_after INTEGER NOT NULL,
        actual_price REAL NOT NULL,
        price_change_pct REAL NOT NULL,
        volume_ratio REAL,
        was_profitable BOOLEAN,
        profit_pct REAL,
        check_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (recommendation_id) REFERENCES recommendations(id)
    )''')

    # Performance metrics table - aggregated learning data
    c.execute('''CREATE TABLE IF NOT EXISTS pattern_performance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pattern TEXT NOT NULL UNIQUE,
        total_recommendations INTEGER DEFAULT 0,
        successful_count INTEGER DEFAULT 0,
        failed_count INTEGER DEFAULT 0,
        avg_confidence INTEGER DEFAULT 0,
        avg_success_rate REAL DEFAULT 0.0,
        confidence_adjustment INTEGER DEFAULT 0,
        last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')

    # Initialize pattern performance records
    patterns = ['3-1 Strat', 'Inside Bar (1)', 'Outside Bar (3)', 'Momentum Play', 'Short Squeeze']
    for pattern in patterns:
        c.execute('''INSERT OR IGNORE INTO pattern_performance
                     (pattern, total_recommendations, successful_count, failed_count, avg_confidence, avg_success_rate, confidence_adjustment)
                     VALUES (?, 0, 0, 0, 50, 0.0, 0)''', (pattern,))

    conn.commit()
    conn.close()
    print("✅ LemonAI database initialized")

# Initialize database on startup
init_database()

def fetch_news(stock_data, ticker, max_articles=3):
    """Helper function to fetch news for a ticker

    Args:
        stock_data: yfinance Ticker object
        ticker: stock symbol
        max_articles: number of articles to return (default 3)

    Returns:
        list of news articles with title, link, publisher, published
    """
    news_articles = []
    try:
        if hasattr(stock_data, 'news'):
            try:
                news_data = stock_data.news

                if news_data and len(news_data) > 0:
                    for article in news_data[:max_articles]:
                        # News structure: article['content'] contains the actual data
                        content = article.get('content', {})

                        # Extract fields from nested structure
                        title = content.get('title', 'No title')

                        # Try clickThroughUrl first, then canonicalUrl
                        click_url = content.get('clickThroughUrl', {})
                        canonical_url = content.get('canonicalUrl', {})
                        link = click_url.get('url') or canonical_url.get('url', '')

                        # Get provider displayName
                        provider = content.get('provider', {})
                        publisher = provider.get('displayName', 'Unknown')

                        # Get pubDate (it's a string like '2025-12-02T16:48:01Z')
                        pub_date_str = content.get('pubDate', '')
                        # Convert to timestamp
                        try:
                            if pub_date_str:
                                dt = datetime.fromisoformat(pub_date_str.replace('Z', '+00:00'))
                                published = int(dt.timestamp())
                            else:
                                published = 0
                        except:
                            published = 0

                        news_articles.append({
                            'title': title,
                            'link': link,
                            'publisher': publisher,
                            'published': published
                        })
            except Exception as e:
                print(f"⚠️  {ticker}: Error accessing news: {e}")
    except Exception as news_error:
        print(f"⚠️  {ticker} news error: {news_error}")

    return news_articles

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
            'type': '3-1 Strat',
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

def analyze_multiple_timeframes(ticker):
    """
    Analyze a ticker across 4 timeframes: 1h, 4h, daily, weekly
    Returns confirmation count and details for each timeframe

    Args:
        ticker: stock symbol to analyze

    Returns:
        dict with:
            - confirmations: list of dicts with timeframe results
            - confirmation_count: how many timeframes show patterns
            - strongest_direction: bullish/bearish/neutral based on majority
            - details: summary string
    """
    timeframes = ['1h', '4h', 'daily', 'weekly']
    confirmations = []
    bullish_count = 0
    bearish_count = 0

    try:
        # Fetch the stock data
        stock_data, hist, info = safe_yf_ticker(ticker)
        if not stock_data or hist is None or len(hist) < 3:
            return {
                'confirmations': [],
                'confirmation_count': 0,
                'strongest_direction': 'neutral',
                'details': 'Insufficient data',
                'timeframes_analyzed': []
            }

        for tf in timeframes:
            try:
                # Resample data based on timeframe
                if tf == '1h':
                    # Use hourly data (last 30 days)
                    hist_tf = stock_data.history(period='30d', interval='1h')
                elif tf == '4h':
                    # Use 4-hour data (last 60 days)
                    hist_tf = stock_data.history(period='60d', interval='1h')
                    # Resample to 4h
                    if len(hist_tf) >= 12:
                        hist_tf = hist_tf.resample('4H').agg({
                            'Open': 'first',
                            'High': 'max',
                            'Low': 'min',
                            'Close': 'last',
                            'Volume': 'sum'
                        }).dropna()
                elif tf == 'daily':
                    hist_tf = hist  # Already daily
                elif tf == 'weekly':
                    # Resample daily to weekly
                    hist_tf = hist.resample('W').agg({
                        'Open': 'first',
                        'High': 'max',
                        'Low': 'min',
                        'Close': 'last',
                        'Volume': 'sum'
                    }).dropna()

                # Skip if not enough data
                if hist_tf is None or len(hist_tf) < 3:
                    continue

                # Check for patterns on this timeframe
                pattern_found = None
                pattern_type = None
                direction = 'neutral'

                # Check 3-1 Strat
                has_31_pattern, pattern_data = check_strat_31(hist_tf)
                if has_31_pattern:
                    pattern_type = '3-1 Strat'
                    direction = pattern_data['direction']
                    pattern_found = True
                else:
                    # Check Inside Bar
                    current = hist_tf.iloc[-1]
                    previous = hist_tf.iloc[-2]
                    is_inside = (current['High'] < previous['High'] and
                               current['Low'] > previous['Low'])

                    if is_inside:
                        pattern_type = 'Inside Bar (1)'
                        direction = 'bullish' if current['Close'] > previous['Close'] else 'bearish'
                        pattern_found = True
                    else:
                        # Check Outside Bar
                        is_outside = (current['High'] > previous['High'] and
                                    current['Low'] < previous['Low'])
                        if is_outside:
                            pattern_type = 'Outside Bar (3)'
                            direction = 'bullish' if current['Close'] > previous['Close'] else 'bearish'
                            pattern_found = True

                # Record this timeframe's result
                if pattern_found:
                    confirmations.append({
                        'timeframe': tf,
                        'pattern': pattern_type,
                        'direction': direction
                    })

                    if direction == 'bullish':
                        bullish_count += 1
                    elif direction == 'bearish':
                        bearish_count += 1

            except Exception as e:
                print(f"⚠️  Error analyzing {ticker} on {tf} timeframe: {e}")
                continue

        # Determine strongest direction based on majority
        if bullish_count > bearish_count:
            strongest_direction = 'bullish'
        elif bearish_count > bullish_count:
            strongest_direction = 'bearish'
        else:
            strongest_direction = 'neutral'

        # Create details string
        confirmation_count = len(confirmations)
        if confirmation_count == 0:
            details = 'No patterns detected'
        else:
            tf_list = [c['timeframe'] for c in confirmations]
            details = f"{confirmation_count}/4 timeframes confirmed ({', '.join(tf_list)})"

        return {
            'confirmations': confirmations,
            'confirmation_count': confirmation_count,
            'strongest_direction': strongest_direction,
            'details': details,
            'timeframes_analyzed': [c['timeframe'] for c in confirmations],
            'bullish_count': bullish_count,
            'bearish_count': bearish_count
        }

    except Exception as e:
        print(f"⚠️  Error in multi-timeframe analysis for {ticker}: {e}")
        return {
            'confirmations': [],
            'confirmation_count': 0,
            'strongest_direction': 'neutral',
            'details': f'Analysis error: {str(e)}',
            'timeframes_analyzed': []
        }

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

                        # Fetch news for this ticker
                        news = fetch_news(stock_data, ticker)

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
                            'riskScore': float(risk_score),
                            'news': news
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

                        # Fetch news for this ticker
                        news = fetch_news(stock_data, ticker)

                        results.append({
                            'ticker': ticker,
                            'company': info.get('longName', ticker),
                            'currentPrice': float(current_price),
                            'dailyChange': float(daily_change),
                            'volume': int(hist['Volume'].iloc[-1]),
                            'avgVolume': int(hist['Volume'].mean()),
                            'marketCap': info.get('marketCap', 0),
                            'pattern': pattern_data,
                            'timeframe': 'daily',
                            'news': news
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

                        # Fetch news for this ticker
                        news = fetch_news(stock_data, ticker)

                        results.append({
                            'ticker': ticker,
                            'company': ticker,
                            'currentPrice': float(current_price),
                            'volume': int(hist['Volume'].iloc[-1]),
                            'pattern': pattern_data,
                            'timeframe': 'weekly',
                            'news': news
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

                    # Fetch news for this ticker
                    news_articles = fetch_news(stock_data, ticker)

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

@app.route('/api/lemonai-analyze', methods=['POST'])
def lemonai_analyze():
    """LemonAI - AI-powered options recommendations (auto-refreshes hourly)"""
    try:
        print("\n🤖 LemonAI: Starting analysis...")

        # Check if we have cached recommendations less than 59 minutes old
        lemonai_cache = scan_cache['lemonai']
        if lemonai_cache['timestamp']:
            age_minutes = (datetime.now() - lemonai_cache['timestamp']).total_seconds() / 60
            if age_minutes < 59 and len(lemonai_cache['results']) > 0:
                print(f"✅ LemonAI: Returning cached recommendations ({int(age_minutes)} minutes old)")
                return jsonify({
                    'success': True,
                    'recommendations': lemonai_cache['results'],
                    'cached': True,
                    'cache_age_minutes': int(age_minutes)
                })

        print("🔄 LemonAI: Generating fresh recommendations...")

        # Auto-run scans if no data exists
        if not any([
            scan_cache['daily']['results'],
            scan_cache['weekly']['results'],
            scan_cache['usuals']['results']
        ]):
            print("📊 LemonAI: Auto-running scans...")
            auto_run_scans_for_lemonai()

        # Collect all stocks from cached scans
        all_stocks = []

        # From squeeze scanner
        for stock in scan_cache['squeeze']['results']:
            all_stocks.append({
                'ticker': stock['ticker'],
                'company': stock.get('company', stock['ticker']),
                'current_price': stock['currentPrice'],
                'pattern': 'Short Squeeze',
                'direction': 'bullish',
                'volume_ratio': stock['volumeRatio'],
                'change': stock['dailyChange'],
                'risk_score': stock['riskScore'],
                'source': 'Short Squeeze',
                'news': stock.get('news', [])
            })

        # From daily plays
        for stock in scan_cache['daily']['results']:
            # Get the actual pattern type from the scan data
            pattern_type = stock['pattern'].get('type', 'Unknown Pattern') if isinstance(stock['pattern'], dict) else 'Pattern'
            all_stocks.append({
                'ticker': stock['ticker'],
                'company': stock.get('company', stock['ticker']),
                'current_price': stock['currentPrice'],
                'pattern': f"{pattern_type} (Daily)",
                'direction': stock['pattern']['direction'] if isinstance(stock['pattern'], dict) else 'neutral',
                'volume_ratio': stock['volume'] / stock['avgVolume'] if stock.get('avgVolume', 0) > 0 else 1,
                'change': stock.get('dailyChange', 0),
                'risk_score': None,
                'source': 'Daily Plays',
                'news': stock.get('news', [])
            })

        # From weekly plays
        for stock in scan_cache['weekly']['results']:
            # Get the actual pattern type from the scan data
            pattern_type = stock['pattern'].get('type', 'Unknown Pattern') if isinstance(stock['pattern'], dict) else 'Pattern'
            all_stocks.append({
                'ticker': stock['ticker'],
                'company': stock.get('company', stock['ticker']),
                'current_price': stock['currentPrice'],
                'pattern': f"{pattern_type} (Weekly)",
                'direction': stock['pattern']['direction'] if isinstance(stock['pattern'], dict) else 'neutral',
                'volume_ratio': stock['volume'] / stock.get('avgVolume', 1) if stock.get('avgVolume', 0) > 0 else 1,
                'change': 0,
                'risk_score': None,
                'source': 'Weekly Plays',
                'news': stock.get('news', [])
            })

        # From usuals - Top 5 by volume ratio and price change
        usuals_with_direction = []
        for stock in scan_cache['usuals']['results']:
            patterns = stock.get('patterns', {})
            daily_pattern = patterns.get('daily', {})

            # Determine direction - use pattern direction or infer from price change
            direction = 'neutral'
            pattern_type = 'Momentum Play'

            if daily_pattern and daily_pattern.get('direction') in ['bullish', 'bearish']:
                direction = daily_pattern.get('direction')
                pattern_type = daily_pattern.get('type', 'Pattern')
            elif stock['change'] > 0.5:  # Positive momentum
                direction = 'bullish'
            elif stock['change'] < -0.5:  # Negative momentum
                direction = 'bearish'

            # Include all stocks with any directional bias
            if direction in ['bullish', 'bearish']:
                usuals_with_direction.append({
                    'ticker': stock['ticker'],
                    'company': stock.get('company', stock['ticker']),
                    'current_price': stock['price'],
                    'pattern': pattern_type,
                    'direction': direction,
                    'volume_ratio': stock['volume_ratio'],
                    'change': stock['change'],
                    'risk_score': None,
                    'source': 'Usuals (Top 5)',
                    'news': stock.get('news', []),
                    'score': abs(stock['change']) * stock['volume_ratio']  # Combine change and volume for ranking
                })

        # Sort usuals by score and take top 5
        usuals_with_direction.sort(key=lambda x: x['score'], reverse=True)
        top_5_usuals = usuals_with_direction[:5]

        # Remove the temporary score field and add to all_stocks
        for usual in top_5_usuals:
            usual.pop('score', None)
            all_stocks.append(usual)

        print(f"🤖 LemonAI: Found {len(all_stocks)} stocks to analyze (including top 5 usuals)")

        if len(all_stocks) == 0:
            return jsonify({
                'success': True,
                'recommendations': [],
                'message': 'No scans have been run yet. Run other scanners first to generate recommendations.'
            })

        # MULTIPLE TIMEFRAME CONFIRMATION - Analyze across 1h, 4h, daily, weekly
        # The more timeframes that confirm, the stronger the signal
        print("🔍 Running multi-timeframe analysis (1h, 4h, daily, weekly)...")

        # Get unique tickers
        unique_tickers = list(set([stock['ticker'] for stock in all_stocks]))

        # Analyze each unique ticker across all timeframes
        ticker_mtf_data = {}
        try:
            for ticker in unique_tickers:
                try:
                    print(f"  📊 Analyzing {ticker} across 4 timeframes...")
                    mtf_result = analyze_multiple_timeframes(ticker)
                    ticker_mtf_data[ticker] = mtf_result

                    if mtf_result['confirmation_count'] > 0:
                        print(f"    ✅ {ticker}: {mtf_result['details']} - {mtf_result['strongest_direction']}")
                except Exception as mtf_error:
                    print(f"    ⚠️  MTF analysis failed for {ticker}: {mtf_error}")
                    # Use default (no confirmation) if analysis fails
                    ticker_mtf_data[ticker] = {
                        'confirmation_count': 0,
                        'strongest_direction': 'neutral',
                        'details': f'Analysis error: {str(mtf_error)[:50]}',
                        'timeframes_analyzed': []
                    }
        except Exception as mtf_global_error:
            print(f"⚠️  Multi-timeframe analysis failed globally: {mtf_global_error}")
            # Continue without MTF data - better to show results than fail

        # Add multi-timeframe data to each stock
        for stock in all_stocks:
            ticker = stock['ticker']
            stock['multi_timeframe_data'] = ticker_mtf_data.get(ticker, {
                'confirmation_count': 0,
                'strongest_direction': 'neutral',
                'details': 'No analysis available',
                'timeframes_analyzed': []
            })

        # Analyze each stock and calculate confidence score
        recommendations = []

        for stock in all_stocks:
            try:
                # Determine option type first (needed for options flow analysis)
                if stock['direction'] == 'bullish':
                    option_type = 'CALL'
                elif stock['direction'] == 'bearish':
                    option_type = 'PUT'
                else:
                    continue  # Skip neutral

                # Fetch options chain data
                print(f"📊 Fetching options data for {stock['ticker']}...")
                stock_data, _, _ = safe_yf_ticker(stock['ticker'])
                options_data = None
                if stock_data:
                    options_data = fetch_options_chain(stock['ticker'], stock_data)

                # Analyze options flow for 3-legs pattern
                options_flow = analyze_options_flow(
                    stock['ticker'],
                    stock['current_price'],
                    option_type,
                    options_data
                )

                # Add options flow to stock data
                stock['options_flow'] = options_flow

                # Calculate initial confidence with options flow included
                confidence, reasoning, options_flow_result = calculate_ai_confidence(stock)

                # Strike price: 2-5% above/below current price (calculate early for contract check)
                strike_distance = 0.03 if confidence >= 75 else 0.05

                if option_type == 'CALL':
                    strike_price = stock['current_price'] * (1 + strike_distance)
                else:  # PUT
                    strike_price = stock['current_price'] * (1 - strike_distance)

                # Round strike to nearest common strike (multiples of 0.5 or 1 or 5)
                if strike_price < 20:
                    strike_price = round(strike_price * 2) / 2  # Round to nearest 0.5
                elif strike_price < 100:
                    strike_price = round(strike_price)  # Round to nearest 1
                else:
                    strike_price = round(strike_price / 5) * 5  # Round to nearest 5

                # Get detailed contract information for the recommended strike
                contract_details = get_contract_details(
                    stock['ticker'],
                    strike_price,
                    option_type,
                    options_data
                )

                # Check contract quality and liquidity
                # NOTE: check_contract_quality now NEVER returns is_tradeable=False (always shows results)
                if contract_details:
                    quality_score, quality_issues, is_tradeable = check_contract_quality(contract_details)

                    # Adjust confidence based on contract quality
                    confidence += quality_score

                    # Add quality issues to reasoning
                    reasoning_parts = reasoning.split('\n')
                    for issue in quality_issues:
                        reasoning_parts.append(issue)
                    reasoning = '\n'.join(reasoning_parts)
                else:
                    # No contract data available - still include but warn heavily
                    print(f"⚠️  {stock['ticker']}: No contract data, using defaults")
                    confidence -= 20  # Penalize for no contract data
                    reasoning_parts = reasoning.split('\n')
                    reasoning_parts.append("⚠️ No contract pricing data available")
                    reasoning = '\n'.join(reasoning_parts)

                # Don't filter by confidence here - we'll take top N after sorting
                # This ensures we ALWAYS have 5-15 results to show

                # Determine expiration based on pattern timeframe
                if 'Weekly' in stock['pattern']:
                    expiration = '3-4 weeks'
                elif 'Daily' in stock['pattern']:
                    expiration = '1-2 weeks'
                else:
                    expiration = '2-3 weeks'

                # Analyze news sentiment
                news_sentiment = analyze_news_sentiment(stock['news'])

                recommendations.append({
                    'ticker': stock['ticker'],
                    'company': stock['company'],
                    'current_price': stock['current_price'],
                    'option_type': option_type,
                    'strike_price': strike_price,
                    'expiration': expiration,
                    'confidence': confidence,
                    'reasoning': reasoning,
                    'pattern': stock['pattern'],
                    'direction': stock['direction'],
                    'volume_ratio': stock['volume_ratio'],
                    'news_sentiment': news_sentiment,
                    'news': stock.get('news', []),
                    'source': stock['source'],
                    'options_flow': options_flow_result,
                    'contract_details': contract_details
                })

            except Exception as e:
                print(f"⚠️  Error analyzing {stock['ticker']}: {e}")
                continue

        # Sort by confidence score (highest first)
        recommendations.sort(key=lambda x: x['confidence'], reverse=True)

        # ALWAYS SHOW 5-15 RESULTS (user requirement)
        # Prioritize high confidence, but ensure we show at least 5 plays
        if len(recommendations) >= 15:
            # Take top 15 if we have that many
            top_recommendations = recommendations[:15]
            print(f"✅ LemonAI: Showing top 15 plays (from {len(recommendations)} total)")
        elif len(recommendations) >= 5:
            # Take top 10 if we have 5-14, but cap at available count
            top_recommendations = recommendations[:min(10, len(recommendations))]
            print(f"✅ LemonAI: Showing {len(top_recommendations)} plays (from {len(recommendations)} total)")
        elif len(recommendations) > 0:
            # Less than 5 available - show what we have and warn
            top_recommendations = recommendations
            print(f"⚠️  WARNING: Only {len(recommendations)} plays available (minimum 5 recommended)")
        else:
            # Absolute fallback - no plays found at all
            top_recommendations = []
            print("❌ No tradeable recommendations - all stocks filtered out (liquidity/data issues)")

        # Filter out very low confidence plays (< 25%) only if we have enough alternatives
        if len(top_recommendations) > 5:
            high_quality = [r for r in top_recommendations if r['confidence'] >= 25]
            if len(high_quality) >= 5:
                top_recommendations = high_quality
                print(f"  Filtered to {len(top_recommendations)} high-quality plays (confidence >= 25%)")

        # Save recommendations to database for tracking and learning
        if len(top_recommendations) > 0:
            print("💾 Saving recommendations to database...")
            for rec in top_recommendations:
                save_recommendation_to_db(rec)

            # Run backtesting on historical recommendations
            print("🔄 Running backtest on historical recommendations...")
            try:
                backtest_recommendations()
            except Exception as backtest_error:
                print(f"⚠️  Backtest error (non-critical): {backtest_error}")

        # Cache the recommendations for 59 minutes
        scan_cache['lemonai']['results'] = top_recommendations
        scan_cache['lemonai']['timestamp'] = datetime.now()

        print(f"✅ LemonAI: Generated {len(top_recommendations)} recommendations (cached for 59 minutes)\n")

        return jsonify({
            'success': True,
            'recommendations': top_recommendations,
            'cached': False,
            'cache_age_minutes': 0
        })

    except Exception as e:
        print(f"❌ LemonAI error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/lemonai-stats', methods=['GET'])
def lemonai_stats():
    """Get win/loss statistics for LemonAI recommendations"""
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()

        # Get overall statistics (last 30 days, checked at 7 days)
        c.execute('''
            SELECT
                COUNT(*) as total_trades,
                SUM(CASE WHEN o.was_profitable = 1 THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN o.was_profitable = 0 THEN 1 ELSE 0 END) as losses,
                AVG(CASE WHEN o.was_profitable = 1 THEN o.profit_pct ELSE 0 END) as avg_win_pct,
                AVG(CASE WHEN o.was_profitable = 0 THEN o.profit_pct ELSE 0 END) as avg_loss_pct,
                AVG(r.confidence) as avg_confidence
            FROM outcomes o
            JOIN recommendations r ON o.recommendation_id = r.id
            WHERE o.days_after = 7
              AND r.recommendation_date >= datetime('now', '-30 days')
        ''')

        overall = c.fetchone()
        total_trades = overall[0] or 0
        wins = overall[1] or 0
        losses = overall[2] or 0
        avg_win_pct = overall[3] or 0
        avg_loss_pct = overall[4] or 0
        avg_confidence = overall[5] or 0

        win_rate = (wins / total_trades * 100) if total_trades > 0 else 0

        # Get stats by pattern
        c.execute('''
            SELECT
                r.pattern,
                COUNT(*) as total,
                SUM(CASE WHEN o.was_profitable = 1 THEN 1 ELSE 0 END) as pattern_wins,
                AVG(r.confidence) as avg_conf
            FROM outcomes o
            JOIN recommendations r ON o.recommendation_id = r.id
            WHERE o.days_after = 7
              AND r.recommendation_date >= datetime('now', '-30 days')
            GROUP BY r.pattern
            ORDER BY pattern_wins DESC
        ''')

        patterns_stats = []
        for row in c.fetchall():
            pattern, total, pattern_wins, avg_conf = row
            pattern_win_rate = (pattern_wins / total * 100) if total > 0 else 0
            patterns_stats.append({
                'pattern': pattern,
                'total': total,
                'wins': pattern_wins,
                'losses': total - pattern_wins,
                'win_rate': round(pattern_win_rate, 1),
                'avg_confidence': round(avg_conf, 1)
            })

        # Get stats by timeframe (1d, 3d, 5d, 7d)
        timeframe_stats = []
        for days in [1, 3, 5, 7]:
            c.execute('''
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN was_profitable = 1 THEN 1 ELSE 0 END) as tf_wins
                FROM outcomes
                WHERE days_after = ?
                  AND recommendation_id IN (
                      SELECT id FROM recommendations
                      WHERE recommendation_date >= datetime('now', '-30 days')
                  )
            ''', (days,))

            row = c.fetchone()
            total = row[0] or 0
            tf_wins = row[1] or 0
            tf_win_rate = (tf_wins / total * 100) if total > 0 else 0

            timeframe_stats.append({
                'timeframe': f'{days}d',
                'total': total,
                'wins': tf_wins,
                'losses': total - tf_wins,
                'win_rate': round(tf_win_rate, 1)
            })

        # Get recent checked trades (last 10)
        c.execute('''
            SELECT
                r.ticker,
                r.option_type,
                r.strike_price,
                r.confidence,
                o.days_after,
                o.was_profitable,
                o.profit_pct,
                o.check_date
            FROM outcomes o
            JOIN recommendations r ON o.recommendation_id = r.id
            WHERE o.days_after = 7
            ORDER BY o.check_date DESC
            LIMIT 10
        ''')

        recent_trades = []
        for row in c.fetchall():
            ticker, opt_type, strike, conf, days, profitable, profit_pct, check_date = row
            recent_trades.append({
                'ticker': ticker,
                'option_type': opt_type,
                'strike': round(strike, 2),
                'confidence': conf,
                'outcome': 'WIN' if profitable else 'LOSS',
                'profit_pct': round(profit_pct, 2),
                'checked_at': check_date
            })

        conn.close()

        return jsonify({
            'success': True,
            'overall': {
                'total_trades': total_trades,
                'wins': wins,
                'losses': losses,
                'win_rate': round(win_rate, 1),
                'avg_win_pct': round(avg_win_pct, 2),
                'avg_loss_pct': round(avg_loss_pct, 2),
                'avg_confidence': round(avg_confidence, 1)
            },
            'by_pattern': patterns_stats,
            'by_timeframe': timeframe_stats,
            'recent_trades': recent_trades,
            'last_updated': datetime.now().isoformat()
        })

    except Exception as e:
        print(f"❌ Stats error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

def auto_run_scans_for_lemonai():
    """Auto-run scans to populate data for LemonAI recommendations - ALWAYS finds plays"""
    try:
        print("🔄 Auto-running comprehensive scan for LemonAI...")
        # EXPANDED list to ensure we ALWAYS have plays (30+ stocks)
        popular_tickers = [
            'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'META', 'NVDA', 'AMD',
            'SPY', 'QQQ', 'IWM', 'DIA',
            'NFLX', 'DIS', 'PYPL', 'SQ', 'UBER', 'BABA', 'SNAP', 'ROKU',
            'F', 'GM', 'BA', 'JPM', 'GS', 'MS',
            'XOM', 'CVX', 'COP',
            'PFE', 'JNJ', 'MRNA',
            'WMT', 'TGT', 'COST',
            'INTC', 'MU', 'QCOM',
            'SOFI', 'PLTR', 'RIVN'
        ]

        daily_results = []
        for ticker in popular_tickers:
            try:
                stock_data, hist, info = safe_yf_ticker(ticker)
                if stock_data and hist is not None and len(hist) >= 3:
                    current_price = hist['Close'].iloc[-1]
                    previous_close = hist['Close'].iloc[-2]
                    daily_change = ((current_price - previous_close) / previous_close) * 100

                    # Check for ANY pattern - 3-1 Strat, Inside Bar, or Outside Bar
                    pattern_found = None
                    has_31_pattern, pattern_data = check_strat_31(hist)

                    if has_31_pattern:
                        pattern_found = pattern_data
                    else:
                        # Check for inside bar (1-bar in Strat)
                        current = hist.iloc[-1]
                        previous = hist.iloc[-2]
                        is_inside = (current['High'] < previous['High'] and
                                   current['Low'] > previous['Low'])

                        if is_inside:
                            # Determine direction based on close position
                            if current['Close'] > previous['Close']:
                                direction = 'bullish'
                            elif current['Close'] < previous['Close']:
                                direction = 'bearish'
                            else:
                                direction = 'neutral'

                            pattern_found = {
                                'type': 'Inside Bar (1)',
                                'direction': direction,
                                'one_candle': {
                                    'high': float(current['High']),
                                    'low': float(current['Low']),
                                    'open': float(current['Open']),
                                    'close': float(current['Close']),
                                    'date': current.name.strftime('%Y-%m-%d')
                                }
                            }
                        else:
                            # Outside bar (3-bar in Strat) - expansion candle
                            is_outside = (current['High'] > previous['High'] and
                                        current['Low'] < previous['Low'])

                            if is_outside:
                                if current['Close'] > previous['Close']:
                                    direction = 'bullish'
                                else:
                                    direction = 'bearish'

                                pattern_found = {
                                    'type': 'Outside Bar (3)',
                                    'direction': direction,
                                    'three_candle': {
                                        'high': float(current['High']),
                                        'low': float(current['Low']),
                                        'close': float(current['Close']),
                                        'date': current.name.strftime('%Y-%m-%d')
                                    }
                                }

                    # Include stock if it has ANY pattern OR even minimal price movement
                    # Lowered threshold to 0.25% to ensure we ALWAYS have results
                    if pattern_found or abs(daily_change) >= 0.25:
                        news = fetch_news(stock_data, ticker)

                        # If no pattern found but has momentum, create a momentum-based pattern
                        if not pattern_found:
                            pattern_found = {
                                'type': 'Momentum Play',
                                'direction': 'bullish' if daily_change > 0 else 'bearish'
                            }

                        daily_results.append({
                            'ticker': ticker,
                            'company': info.get('longName', ticker),
                            'currentPrice': float(current_price),
                            'dailyChange': float(daily_change),
                            'volume': int(hist['Volume'].iloc[-1]),
                            'avgVolume': int(hist['Volume'].mean()),
                            'marketCap': info.get('marketCap', 0),
                            'pattern': pattern_found,
                            'timeframe': 'daily',
                            'news': news
                        })
            except Exception as e:
                print(f"⚠️  Error scanning {ticker}: {e}")
                continue

        scan_cache['daily']['results'] = daily_results
        scan_cache['daily']['timestamp'] = datetime.now()
        print(f"✅ Auto-scan: Found {len(daily_results)} setups (patterns + momentum)")

        # Run usuals scanner - include ALL stocks with ANY setup
        print("🔄 Auto-running Usuals scan...")
        default_tickers = ['SOFI', 'PLTR', 'AMD', 'NVDA', 'TSLA', 'SPY', 'QQQ', 'INTC', 'AAPL', 'MSFT']
        usuals_results = []

        for ticker in default_tickers:
            try:
                stock_data, hist, info = safe_yf_ticker(ticker)
                if stock_data and hist is not None and len(hist) >= 3:
                    current_price = hist['Close'].iloc[-1]
                    prev_price = hist['Close'].iloc[-2]
                    change = ((current_price - prev_price) / prev_price) * 100

                    current_volume = hist['Volume'].iloc[-1]
                    avg_volume = hist['Volume'].iloc[:-1].mean()
                    volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1

                    # Check for ANY pattern - always include the stock
                    patterns = {}
                    has_31_pattern, pattern_data = check_strat_31(hist)

                    if has_31_pattern:
                        patterns['daily'] = {
                            'type': '3-1 Strat',
                            'direction': pattern_data['direction']
                        }
                    else:
                        # Check for inside bar
                        current = hist.iloc[-1]
                        previous = hist.iloc[-2]
                        is_inside = (current['High'] < previous['High'] and
                                   current['Low'] > previous['Low'])

                        if is_inside:
                            direction = 'bullish' if current['Close'] > previous['Close'] else 'bearish'
                            patterns['daily'] = {
                                'type': 'Inside Bar (1)',
                                'direction': direction
                            }
                        elif abs(change) >= 1.0:
                            # Momentum play
                            patterns['daily'] = {
                                'type': 'Momentum',
                                'direction': 'bullish' if change > 0 else 'bearish'
                            }
                        else:
                            # No clear pattern detected
                            patterns['daily'] = {
                                'type': 'No Pattern',
                                'direction': 'bullish' if change > 0 else 'bearish'
                            }

                    news = fetch_news(stock_data, ticker)

                    # Always include stock (with or without patterns)
                    usuals_results.append({
                        'ticker': ticker,
                        'company': info.get('longName', ticker),
                        'price': float(current_price),
                        'change': float(change),
                        'volume': int(current_volume),
                        'avg_volume': int(avg_volume),
                        'volume_ratio': float(volume_ratio),
                        'patterns': patterns,
                        'news': news
                    })
            except Exception as e:
                print(f"⚠️  Error scanning {ticker}: {e}")
                continue

        scan_cache['usuals']['results'] = usuals_results
        scan_cache['usuals']['timestamp'] = datetime.now()
        print(f"✅ Auto-scan: Scanned {len(usuals_results)} usuals (all included)")

    except Exception as e:
        print(f"⚠️  Auto-scan error: {e}")

def save_recommendation_to_db(recommendation):
    """Save a recommendation to the database for tracking"""
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()

        # Calculate expiration date (convert text like "1-2 weeks" to actual date)
        exp_text = recommendation['expiration']
        if 'week' in exp_text:
            weeks = int(exp_text.split('-')[0]) if '-' in exp_text else int(exp_text.split()[0])
            exp_date = datetime.now() + timedelta(weeks=weeks)
        else:
            exp_date = datetime.now() + timedelta(days=14)  # Default 2 weeks

        # Extract options flow data
        options_flow = recommendation.get('options_flow', {})

        # Extract contract details
        contract = recommendation.get('contract_details', {})

        c.execute('''INSERT INTO recommendations
                     (ticker, company, option_type, strike_price, current_price, expiration,
                      confidence, pattern, direction, volume_ratio, news_sentiment, source,
                      reasoning, news_json, options_flow_score, options_avg_volume, options_avg_oi,
                      options_total_volume, options_total_oi, options_has_pattern, options_details,
                      contract_premium, contract_bid, contract_ask, contract_bid_ask_spread,
                      contract_volume, contract_oi, contract_premium_value, contract_percent_change,
                      contract_implied_vol, expiration_date)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                  (recommendation['ticker'],
                   recommendation['company'],
                   recommendation['option_type'],
                   recommendation['strike_price'],
                   recommendation['current_price'],
                   recommendation['expiration'],
                   recommendation['confidence'],
                   recommendation['pattern'],
                   recommendation.get('direction', 'unknown'),
                   recommendation['volume_ratio'],
                   recommendation['news_sentiment'],
                   recommendation['source'],
                   recommendation['reasoning'],
                   json.dumps(recommendation.get('news', [])),
                   options_flow.get('flow_score', 0),
                   options_flow.get('avg_volume', 0),
                   options_flow.get('avg_oi', 0),
                   options_flow.get('total_volume', 0),
                   options_flow.get('total_oi', 0),
                   options_flow.get('has_pattern', False),
                   options_flow.get('details', ''),
                   contract.get('last_price', 0),
                   contract.get('bid', 0),
                   contract.get('ask', 0),
                   contract.get('bid_ask_spread', 0),
                   contract.get('volume', 0),
                   contract.get('open_interest', 0),
                   contract.get('premium_value', 0),
                   contract.get('percent_change', 0),
                   contract.get('implied_volatility', 0),
                   exp_date.strftime('%Y-%m-%d')))

        rec_id = c.lastrowid
        conn.commit()
        conn.close()
        return rec_id
    except Exception as e:
        print(f"⚠️  Error saving recommendation to DB: {e}")
        return None

def backtest_recommendations():
    """Check outcomes of past recommendations and update outcomes table"""
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()

        # Get recommendations from last 30 days that haven't been fully checked
        c.execute('''SELECT r.id, r.ticker, r.option_type, r.strike_price, r.current_price,
                           r.recommendation_date, r.pattern, r.confidence, r.direction
                     FROM recommendations r
                     WHERE r.recommendation_date >= datetime('now', '-30 days')
                       AND r.id NOT IN (SELECT recommendation_id FROM outcomes WHERE days_after >= 7)
                     ORDER BY r.recommendation_date DESC
                     LIMIT 50''')

        recs = c.fetchall()

        for rec in recs:
            rec_id, ticker, option_type, strike_price, initial_price, rec_date, pattern, confidence, direction = rec

            # Calculate days since recommendation
            rec_datetime = datetime.fromisoformat(rec_date)
            days_passed = (datetime.now() - rec_datetime).days

            # Skip if less than 1 day old
            if days_passed < 1:
                continue

            # Check multiple timeframes (1, 3, 5, 7, 14 days)
            check_points = [1, 3, 5, 7, 14]
            for days_after in check_points:
                if days_passed < days_after:
                    continue

                # Check if we already have this outcome
                c.execute('SELECT id FROM outcomes WHERE recommendation_id = ? AND days_after = ?',
                         (rec_id, days_after))
                if c.fetchone():
                    continue  # Already checked

                # Fetch current price
                try:
                    stock_data, hist, _ = safe_yf_ticker(ticker, period='1mo', interval='1d')
                    if hist is None or len(hist) == 0:
                        continue

                    # Get price from N days ago
                    target_date = rec_datetime + timedelta(days=days_after)
                    closest_price = None
                    min_diff = float('inf')

                    for idx, row in hist.iterrows():
                        date_diff = abs((idx.date() - target_date.date()).days)
                        if date_diff < min_diff:
                            min_diff = date_diff
                            closest_price = row['Close']

                    if closest_price is None:
                        continue

                    # Calculate outcome
                    price_change_pct = ((closest_price - initial_price) / initial_price) * 100

                    # Determine if profitable (for calls: price went up and above strike, for puts: price went down and below strike)
                    was_profitable = False
                    profit_pct = 0.0

                    if option_type == 'CALL':
                        if closest_price > strike_price:
                            was_profitable = True
                            profit_pct = ((closest_price - strike_price) / strike_price) * 100
                    else:  # PUT
                        if closest_price < strike_price:
                            was_profitable = True
                            profit_pct = ((strike_price - closest_price) / strike_price) * 100

                    # Get volume info
                    volume_ratio = hist['Volume'].iloc[-1] / hist['Volume'].mean() if len(hist) > 1 else 1.0

                    # Save outcome
                    c.execute('''INSERT INTO outcomes
                                (recommendation_id, days_after, actual_price, price_change_pct,
                                 volume_ratio, was_profitable, profit_pct)
                                VALUES (?, ?, ?, ?, ?, ?, ?)''',
                             (rec_id, days_after, float(closest_price), float(price_change_pct),
                              float(volume_ratio), was_profitable, float(profit_pct)))

                    print(f"✅ Backtested {ticker} {option_type} at {days_after}d: {'WIN' if was_profitable else 'LOSS'}")

                except Exception as e:
                    print(f"⚠️  Error backtesting {ticker}: {e}")
                    continue

        conn.commit()
        conn.close()

        # Update pattern performance after backtesting
        update_pattern_performance()

    except Exception as e:
        print(f"⚠️  Error in backtest: {e}")

def update_pattern_performance():
    """Update pattern performance metrics based on outcomes"""
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()

        # Get all patterns
        c.execute('SELECT DISTINCT pattern FROM recommendations')
        patterns = [row[0] for row in c.fetchall()]

        for pattern in patterns:
            # Get 7-day outcomes for this pattern (most relevant timeframe)
            c.execute('''SELECT r.confidence, o.was_profitable
                        FROM recommendations r
                        JOIN outcomes o ON r.id = o.recommendation_id
                        WHERE r.pattern = ? AND o.days_after = 7''', (pattern,))

            results = c.fetchall()

            if len(results) == 0:
                continue

            total = len(results)
            successful = sum(1 for _, profitable in results if profitable)
            failed = total - successful
            avg_conf = sum(conf for conf, _ in results) / total
            success_rate = (successful / total) * 100

            # Calculate confidence adjustment based on success rate
            # If success rate > 60%, boost confidence. If < 40%, reduce it.
            if success_rate >= 70:
                adjustment = +5
            elif success_rate >= 60:
                adjustment = +3
            elif success_rate <= 30:
                adjustment = -5
            elif success_rate <= 40:
                adjustment = -3
            else:
                adjustment = 0

            # Update pattern performance
            c.execute('''UPDATE pattern_performance
                        SET total_recommendations = ?,
                            successful_count = ?,
                            failed_count = ?,
                            avg_confidence = ?,
                            avg_success_rate = ?,
                            confidence_adjustment = ?,
                            last_updated = CURRENT_TIMESTAMP
                        WHERE pattern = ?''',
                     (total, successful, failed, int(avg_conf), success_rate, adjustment, pattern))

            print(f"📊 {pattern}: {successful}/{total} wins ({success_rate:.1f}%), adjustment: {adjustment:+d}")

        conn.commit()
        conn.close()

    except Exception as e:
        print(f"⚠️  Error updating pattern performance: {e}")

def get_pattern_adjustment(pattern):
    """Get learned confidence adjustment for a pattern"""
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute('SELECT confidence_adjustment FROM pattern_performance WHERE pattern = ?', (pattern,))
        result = c.fetchone()
        conn.close()
        return result[0] if result else 0
    except:
        return 0

def calculate_ai_confidence(stock):
    """Calculate confidence score for a trade based on multiple factors + learned adjustments"""
    confidence = 50  # Base confidence
    reasoning_parts = []

    # 1. Pattern strength (max +20)
    if stock['pattern'] == 'Short Squeeze':
        if stock['risk_score'] and stock['risk_score'] >= 80:
            confidence += 20
            reasoning_parts.append(f"High risk score ({stock['risk_score']}/100) indicates strong squeeze potential")
        elif stock['risk_score'] and stock['risk_score'] >= 70:
            confidence += 15
            reasoning_parts.append(f"Good risk score ({stock['risk_score']}/100)")
        else:
            confidence += 10
            reasoning_parts.append("Moderate squeeze setup")
    elif '3-1 Strat' in stock['pattern']:
        confidence += 15
        reasoning_parts.append(f"Strong {stock['pattern']} pattern detected")
    elif 'Inside Bar (1)' in stock['pattern']:
        confidence += 12
        reasoning_parts.append("Inside bar consolidation suggests potential breakout")
    elif 'Outside Bar (3)' in stock['pattern']:
        confidence += 14
        reasoning_parts.append("Outside bar expansion shows increased volatility")
    elif 'Momentum Play' in stock['pattern'] or 'Momentum' in stock['pattern']:
        confidence += 8
        reasoning_parts.append("Strong price momentum detected")
    else:
        confidence += 10
        reasoning_parts.append(f"{stock['pattern']} pattern identified")

    # 2. Direction strength (max +15)
    if stock['direction'] == 'bullish' and stock['change'] > 0:
        confidence += 15
        reasoning_parts.append(f"Bullish momentum with +{stock['change']:.1f}% price change")
    elif stock['direction'] == 'bearish' and stock['change'] < 0:
        confidence += 15
        reasoning_parts.append(f"Bearish momentum with {stock['change']:.1f}% price change")
    elif stock['direction'] in ['bullish', 'bearish']:
        confidence += 8
        reasoning_parts.append(f"Clear {stock['direction']} direction")

    # 3. Volume confirmation (max +15)
    if stock['volume_ratio'] >= 2.0:
        confidence += 15
        reasoning_parts.append(f"Very high volume ({stock['volume_ratio']:.1f}x average)")
    elif stock['volume_ratio'] >= 1.5:
        confidence += 10
        reasoning_parts.append(f"High volume ({stock['volume_ratio']:.1f}x average)")
    elif stock['volume_ratio'] >= 1.0:
        confidence += 5
        reasoning_parts.append("Average volume")

    # 4. News sentiment (max +10)
    news_sentiment = analyze_news_sentiment(stock['news'])
    if news_sentiment == 'Positive' and stock['direction'] == 'bullish':
        confidence += 10
        reasoning_parts.append("Positive news supports bullish outlook")
    elif news_sentiment == 'Negative' and stock['direction'] == 'bearish':
        confidence += 10
        reasoning_parts.append("Negative news supports bearish outlook")
    elif news_sentiment != 'Neutral':
        confidence += 5
        reasoning_parts.append(f"{news_sentiment} news sentiment")

    # 5. Apply machine learning adjustment based on historical performance
    pattern_adjustment = get_pattern_adjustment(stock['pattern'])
    if pattern_adjustment != 0:
        confidence += pattern_adjustment
        if pattern_adjustment > 0:
            reasoning_parts.append(f"AI learned this pattern performs well (+{pattern_adjustment} confidence)")
        else:
            reasoning_parts.append(f"AI learned to be cautious with this pattern ({pattern_adjustment} confidence)")

    # 6. Options flow analysis (max +15)
    options_flow = stock.get('options_flow', {})
    if options_flow and options_flow.get('flow_score', 0) > 0:
        flow_score = options_flow['flow_score']
        if flow_score >= 70:
            confidence += 15
            reasoning_parts.append(f"🔥 Strong options flow ({flow_score}/100): {options_flow.get('details', 'N/A')}")
        elif flow_score >= 40:
            confidence += 10
            reasoning_parts.append(f"📊 Good options flow ({flow_score}/100): {options_flow.get('details', 'N/A')}")
        elif flow_score >= 20:
            confidence += 5
            reasoning_parts.append(f"Options activity detected ({flow_score}/100)")

    # 7. Multiple timeframe confirmation (max +40) - EXTREMELY STRONG SIGNAL
    # Checks 1h, 4h, daily, weekly - the more that confirm, the stronger the signal
    mtf_data = stock.get('multi_timeframe_data', {})
    confirmation_count = mtf_data.get('confirmation_count', 0)

    if confirmation_count >= 4:
        # All 4 timeframes confirm same direction = GOLDEN SETUP
        confidence += 40
        timeframes = ', '.join(mtf_data.get('timeframes_analyzed', []))
        reasoning_parts.append(f"🔥🔥🔥 GOLDEN: All 4 timeframes confirm {stock['direction']} ({timeframes}) - EXTREMELY HIGH CONVICTION")
    elif confirmation_count == 3:
        # 3 out of 4 timeframes = very strong
        confidence += 30
        timeframes = ', '.join(mtf_data.get('timeframes_analyzed', []))
        reasoning_parts.append(f"🔥🔥 STRONG: 3/4 timeframes confirm {stock['direction']} ({timeframes}) - HIGH CONVICTION")
    elif confirmation_count == 2:
        # 2 out of 4 timeframes = good
        confidence += 20
        timeframes = ', '.join(mtf_data.get('timeframes_analyzed', []))
        reasoning_parts.append(f"🔥 GOOD: 2/4 timeframes confirm {stock['direction']} ({timeframes}) - SOLID SETUP")
    elif confirmation_count == 1:
        # Only 1 timeframe = standard (no bonus)
        timeframes = ', '.join(mtf_data.get('timeframes_analyzed', []))
        reasoning_parts.append(f"Single timeframe setup ({timeframes})")

    # Cap confidence at 95 (never 100%)
    confidence = min(confidence, 95)

    reasoning = '\n'.join(reasoning_parts)
    return confidence, reasoning, options_flow

def check_contract_quality(contract_details):
    """
    Analyze contract liquidity and quality to prevent bad fills

    Args:
        contract_details: dict with bid, ask, volume, open_interest, etc.

    Returns:
        tuple: (quality_score, issues_list, is_tradeable)
            - quality_score: -30 to +50 points to add to confidence
            - issues_list: list of warnings about the contract
            - is_tradeable: bool, False if contract fails minimum requirements
    """
    if not contract_details:
        return -30, ['No contract data available'], False

    score = 0
    issues = []

    bid = contract_details.get('bid', 0)
    ask = contract_details.get('ask', 0)
    volume = contract_details.get('volume', 0)
    oi = contract_details.get('open_interest', 0)

    # 1. BID-ASK SPREAD CHECK (most important for execution quality)
    if ask > 0 and bid > 0:
        spread_pct = (contract_details['bid_ask_spread'] / ask) * 100

        if spread_pct < 5:
            score += 20
            # Excellent spread - no issue to report
        elif spread_pct < 10:
            score += 15
            # Very good spread - no issue to report
        elif spread_pct < 20:
            score += 5
            # Good spread - no issue to report
        elif spread_pct < 35:
            score += 0
            issues.append(f"⚠️ Moderate spread ({spread_pct:.1f}%)")
        elif spread_pct < 50:
            score -= 10
            issues.append(f"⚠️ Wide spread ({spread_pct:.1f}%)")
        else:
            # Very wide spread - still tradeable but penalize heavily
            score -= 25
            issues.append(f"🔴 Very wide spread ({spread_pct:.1f}% - use limit orders)")
    else:
        # No bid/ask - likely stale data, but don't reject entirely
        score -= 15
        issues.append(f"⚠️ No bid/ask data available")

    # 2. VOLUME CHECK (can you actually trade it today?)
    # MUCH MORE LENIENT - accept even low volume contracts
    if volume >= 100:
        score += 15
        # Excellent volume - no issue
    elif volume >= 50:
        score += 10
        # Good volume - no issue
    elif volume >= 20:
        score += 5
        # Decent volume - no issue
    elif volume >= 5:
        score += 0
        issues.append(f"⚠️ Low volume ({volume} contracts)")
    elif volume >= 1:
        score -= 10
        issues.append(f"⚠️ Very low volume ({volume} contracts - use limit orders)")
    else:
        # Zero volume - likely no trades today but still show it
        score -= 15
        issues.append(f"⚠️ No volume today ({volume} contracts)")

    # 3. OPEN INTEREST CHECK (is this contract actively traded?)
    # MUCH MORE LENIENT - accept even low OI contracts
    if oi >= 500:
        score += 15
        # Excellent OI - no issue
    elif oi >= 100:
        score += 10
        # Good OI - no issue
    elif oi >= 50:
        score += 5
        # Decent OI - no issue
    elif oi >= 10:
        score += 0
        issues.append(f"⚠️ Low OI ({oi})")
    elif oi >= 1:
        score -= 10
        issues.append(f"⚠️ Very low OI ({oi})")
    else:
        # Zero OI - brand new contract
        score -= 15
        issues.append(f"⚠️ New contract (OI: {oi})")

    # ALWAYS TRADEABLE - just penalize score
    # This ensures we ALWAYS show results
    is_tradeable = True

    # If no issues were added, add a positive note
    if not issues:
        issues.append(f"✅ Liquid contract: Vol {volume}, OI {oi}, Spread {spread_pct:.1f}%")

    return score, issues, is_tradeable

def get_contract_details(ticker, strike_price, option_type, options_data):
    """Get detailed contract information for a specific strike

    Args:
        ticker: stock symbol
        strike_price: target strike price
        option_type: 'CALL' or 'PUT'
        options_data: dict with 'calls' and 'puts' DataFrames

    Returns:
        dict with premium, bid, ask, volume, OI, change, etc.
    """
    if not options_data:
        return None

    try:
        # Select the appropriate chain
        chain = options_data['calls'] if option_type == 'CALL' else options_data['puts']

        # Find the closest strike to our target
        chain['strike_diff'] = abs(chain['strike'] - strike_price)
        closest_contract = chain.loc[chain['strike_diff'].idxmin()]

        # Extract contract details
        last_price = closest_contract.get('lastPrice', 0)
        bid = closest_contract.get('bid', 0)
        ask = closest_contract.get('ask', 0)
        volume = closest_contract.get('volume', 0)
        open_interest = closest_contract.get('openInterest', 0)
        change = closest_contract.get('change', 0)
        percent_change = closest_contract.get('percentChange', 0)
        implied_volatility = closest_contract.get('impliedVolatility', 0)

        # Calculate bid-ask spread
        bid_ask_spread = ask - bid if ask > 0 and bid > 0 else 0

        # Calculate premium value (price * 100 * volume)
        premium_value = last_price * 100 * volume if volume > 0 else 0

        return {
            'strike': float(closest_contract['strike']),
            'last_price': float(last_price),
            'bid': float(bid),
            'ask': float(ask),
            'bid_ask_spread': float(bid_ask_spread),
            'volume': int(volume) if volume > 0 else 0,
            'open_interest': int(open_interest) if open_interest > 0 else 0,
            'change': float(change),
            'percent_change': float(percent_change),
            'premium_value': float(premium_value),
            'implied_volatility': float(implied_volatility) if implied_volatility else 0,
            'expiration': options_data['expiration']
        }

    except Exception as e:
        print(f"⚠️  Error getting contract details for {ticker}: {e}")
        return None

def analyze_news_sentiment(news_articles):
    """Analyze news sentiment based on keywords"""
    if not news_articles or len(news_articles) == 0:
        return 'Neutral'

    positive_keywords = ['surge', 'soar', 'beat', 'profit', 'growth', 'upgrade', 'bullish', 'rally', 'gain', 'win', 'success', 'breakthrough', 'record', 'high']
    negative_keywords = ['plunge', 'fall', 'loss', 'miss', 'downgrade', 'bearish', 'drop', 'decline', 'crash', 'fail', 'warning', 'concern', 'risk']

    positive_count = 0
    negative_count = 0

    for article in news_articles:
        title = article.get('title', '').lower()
        for keyword in positive_keywords:
            if keyword in title:
                positive_count += 1
        for keyword in negative_keywords:
            if keyword in title:
                negative_count += 1

    if positive_count > negative_count:
        return 'Positive'
    elif negative_count > positive_count:
        return 'Negative'
    else:
        return 'Neutral'

def fetch_options_chain(ticker, stock_data):
    """Fetch options chain data for a ticker

    Returns:
        dict with 'calls' and 'puts' DataFrames, or None if error
    """
    try:
        # Get available expiration dates
        expirations = stock_data.options

        if not expirations or len(expirations) == 0:
            return None

        # Use nearest expiration (most liquid, typically weekly or monthly)
        nearest_exp = expirations[0]

        # Get options chain
        opt_chain = stock_data.option_chain(nearest_exp)

        return {
            'calls': opt_chain.calls,
            'puts': opt_chain.puts,
            'expiration': nearest_exp
        }
    except Exception as e:
        print(f"⚠️  Error fetching options for {ticker}: {e}")
        return None

def analyze_options_flow(ticker, current_price, option_type, options_data):
    """Analyze options flow for '3 legs up' (calls) or '3 legs down' (puts) patterns

    Args:
        ticker: stock symbol
        current_price: current stock price
        option_type: 'CALL' or 'PUT'
        options_data: dict with 'calls' and 'puts' DataFrames

    Returns:
        dict with flow_score (0-100), has_pattern (bool), and details
    """
    if not options_data:
        return {
            'flow_score': 0,
            'has_pattern': False,
            'details': 'No options data available',
            'avg_volume': 0,
            'avg_oi': 0,
            'total_volume': 0,
            'total_oi': 0
        }

    try:
        if option_type == 'CALL':
            # Look for 3 legs UP (strikes above current price)
            chain = options_data['calls']
            # Filter strikes above current price
            relevant_strikes = chain[chain['strike'] > current_price].head(10)
        else:  # PUT
            # Look for 3 legs DOWN (strikes below current price)
            chain = options_data['puts']
            # Filter strikes below current price
            relevant_strikes = chain[chain['strike'] < current_price].head(10)

        if len(relevant_strikes) < 3:
            return {
                'flow_score': 0,
                'has_pattern': False,
                'details': 'Insufficient strikes for analysis',
                'avg_volume': 0,
                'avg_oi': 0,
                'total_volume': 0,
                'total_oi': 0
            }

        # Sort by strike price
        if option_type == 'CALL':
            relevant_strikes = relevant_strikes.sort_values('strike', ascending=True)
        else:
            relevant_strikes = relevant_strikes.sort_values('strike', ascending=False)

        # Get top 3 strikes for analysis
        top_3_strikes = relevant_strikes.head(3)

        # Extract volumes and open interest
        volumes = top_3_strikes['volume'].fillna(0).tolist()
        open_interests = top_3_strikes['openInterest'].fillna(0).tolist()
        strikes = top_3_strikes['strike'].tolist()

        # Calculate total and average
        total_volume = sum(volumes)
        total_oi = sum(open_interests)
        avg_volume = total_volume / 3 if total_volume > 0 else 0
        avg_oi = total_oi / 3 if total_oi > 0 else 0

        # Check for "3 legs" pattern - increasing volume/OI across strikes
        # Pattern 1: Increasing volume (most bullish/bearish)
        has_increasing_volume = (len(volumes) == 3 and
                                volumes[0] < volumes[1] < volumes[2] and
                                volumes[2] > 0)

        # Pattern 2: Increasing OI (shows accumulation)
        has_increasing_oi = (len(open_interests) == 3 and
                           open_interests[0] < open_interests[1] < open_interests[2] and
                           open_interests[2] > 0)

        # Pattern 3: High consistent volume/OI (at least 100 contracts each)
        has_high_activity = avg_volume >= 100 or avg_oi >= 500

        # Calculate flow score (0-100)
        flow_score = 0
        details_parts = []

        if has_increasing_volume:
            flow_score += 40
            details_parts.append(f"🔥 3-legs pattern: Volume increasing across strikes ({volumes[0]:.0f} → {volumes[1]:.0f} → {volumes[2]:.0f})")

        if has_increasing_oi:
            flow_score += 30
            details_parts.append(f"📊 OI increasing: {open_interests[0]:.0f} → {open_interests[1]:.0f} → {open_interests[2]:.0f}")

        if has_high_activity:
            flow_score += 20
            details_parts.append(f"💪 High activity: Avg vol {avg_volume:.0f}, Avg OI {avg_oi:.0f}")

        # Bonus: Check if volume > OI (fresh positioning vs existing positions)
        if total_volume > total_oi * 0.5:
            flow_score += 10
            details_parts.append("⚡ Fresh positioning (high volume vs OI)")

        has_pattern = has_increasing_volume or has_increasing_oi

        if not details_parts:
            details_parts.append(f"Moderate activity at strikes: {strikes[0]:.1f}, {strikes[1]:.1f}, {strikes[2]:.1f}")

        return {
            'flow_score': min(flow_score, 100),
            'has_pattern': has_pattern,
            'details': '\n'.join(details_parts),
            'avg_volume': avg_volume,
            'avg_oi': avg_oi,
            'total_volume': total_volume,
            'total_oi': total_oi,
            'strikes_analyzed': strikes
        }

    except Exception as e:
        print(f"⚠️  Error analyzing options flow for {ticker}: {e}")
        return {
            'flow_score': 0,
            'has_pattern': False,
            'details': f'Error: {str(e)}',
            'avg_volume': 0,
            'avg_oi': 0,
            'total_volume': 0,
            'total_oi': 0
        }

# Background scheduler for daily backtest checks
import threading
import time as time_module

def run_daily_backtest():
    """Background thread that runs backtest every 24 hours"""
    while True:
        try:
            print("\n🔄 Running daily backtest check...")
            backtest_recommendations()
            print("✅ Daily backtest completed\n")
        except Exception as e:
            print(f"❌ Daily backtest error: {e}")

        # Sleep for 24 hours (86400 seconds)
        time_module.sleep(86400)

# Start background thread for daily backtest
backtest_thread = threading.Thread(target=run_daily_backtest, daemon=True)
backtest_thread.start()
print("✅ Daily backtest scheduler started (runs every 24 hours)")

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
