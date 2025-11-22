"""
🍋 LEMON SQUEEZE WEB APP v2.2 - COMPLETE EDITION 🍋
Flask-based web interface with:
- Short Squeeze Scanner
- Daily/Weekly/Hourly Plays (3-1 Strat Pattern Scanner)
- Crypto Scanner
- 🔊 Volemon (Auto Volume Scanner)
- ⭐ Usuals (Favorite Stocks Auto-Scanner)
- 👤 Profile Management (Bio + Trader Type)
- 💬 Community Chat (Real-time with trader badges)
- 🔐 User Authentication System

UPDATED v2.2:
- Chat messages now include user trader_type for badge display
- Profile tab integrated with header button
- Enhanced authentication flow
"""

from flask import Flask, render_template, jsonify, request, send_from_directory, session
import yfinance as yf
from datetime import datetime, timedelta
import time
import os
import json
import hashlib
import secrets
import sqlite3
from functools import wraps

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)  # Secure secret key for sessions
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)  # Sessions last 7 days

# Database setup
DATABASE = 'lemon_squeeze.db'

def get_db():
    """Get database connection"""
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    return db

def init_db():
    """Initialize the database with users table"""
    db = get_db()
    db.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            bio TEXT DEFAULT '',
            trader_type TEXT DEFAULT 'swing_trader',
            profile_image TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP,
            is_active INTEGER DEFAULT 1
        )
    ''')
    
    db.execute('''
        CREATE TABLE IF NOT EXISTS user_favorites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            ticker TEXT NOT NULL,
            company TEXT,
            timeframe TEXT,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id),
            UNIQUE(user_id, ticker, timeframe)
        )
    ''')
    
    db.execute('''
        CREATE TABLE IF NOT EXISTS user_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            theme TEXT DEFAULT 'light',
            email_notifications INTEGER DEFAULT 1,
            FOREIGN KEY (user_id) REFERENCES users (id),
            UNIQUE(user_id)
        )
    ''')
    
    db.execute('''
        CREATE TABLE IF NOT EXISTS chat_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            user_name TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    db.commit()
    db.close()

def hash_password(password):
    """Hash a password with SHA-256"""
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password, password_hash):
    """Verify a password against its hash"""
    return hash_password(password) == password_hash

def login_required(f):
    """Decorator to require login for certain routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'success': False, 'error': 'Authentication required'}), 401
        return f(*args, **kwargs)
    return decorated_function

# Initialize database on startup
init_db()

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
    ULTRA-ACCURATE: 100% reliable pattern detection
    - Detects 3-1 patterns (Outside bar + Inside bar)
    - Detects standalone Inside bars
    - Strict validation for data quality
    - Minimum size requirements (filters noise)
    - Clear mathematical definitions
    """
    if len(hist) < 2:
        return False, None
    
    # Get candles
    current = hist.iloc[-1]
    previous = hist.iloc[-2]
    
    # Extract OHLC values as floats
    try:
        curr_high = float(current['High'])
        curr_low = float(current['Low'])
        curr_open = float(current['Open'])
        curr_close = float(current['Close'])
        
        prev_high = float(previous['High'])
        prev_low = float(previous['Low'])
        prev_close = float(previous['Close'])
    except (ValueError, KeyError, TypeError):
        return False, None
    
    # ========================================
    # VALIDATION: Data Quality Check
    # ========================================
    if any([
        curr_high <= 0, curr_low <= 0, curr_open <= 0, curr_close <= 0,
        prev_high <= 0, prev_low <= 0
    ]):
        return False, None
    
    if curr_high < curr_low or prev_high < prev_low:
        return False, None
    
    # ========================================
    # INSIDE BAR DETECTION (Strict)
    # ========================================
    is_inside_bar = (
        curr_high < prev_high and  # STRICTLY less than
        curr_low > prev_low         # STRICTLY greater than
    )
    
    # Additional validation: Inside bar should be noticeably smaller
    if is_inside_bar:
        prev_range = prev_high - prev_low
        curr_range = curr_high - curr_low
        
        # Filter out near-identical bars (must be at least 5% smaller)
        if curr_range >= prev_range * 0.95:
            is_inside_bar = False
        
        # Minimum range check (filters noise)
        if prev_range > 0 and (curr_range / curr_close) < 0.001:
            is_inside_bar = False
    
    # Determine direction
    direction = "bullish" if curr_close > curr_open else "bearish"
    
    # Helper function to safely get date string
    def get_date_string(candle):
        """Safely extract date string from candle with multiple fallbacks"""
        try:
            # Try strftime first
            if hasattr(candle, 'name') and hasattr(candle.name, 'strftime'):
                return candle.name.strftime('%Y-%m-%d')
            # Try converting index to string
            elif hasattr(candle, 'name'):
                date_str = str(candle.name)
                # Extract YYYY-MM-DD if present
                if len(date_str) >= 10:
                    return date_str[:10]
                return date_str
            else:
                return "N/A"
        except Exception as e:
            return "N/A"
    
    # ========================================
    # 3-1 PATTERN DETECTION (Strict)
    # ========================================
    if len(hist) >= 3:
        before_prev = hist.iloc[-3]
        
        try:
            bp_high = float(before_prev['High'])
            bp_low = float(before_prev['Low'])
        except (ValueError, KeyError):
            bp_high = bp_low = None
        
        if bp_high and bp_low and bp_high > bp_low:
            # STRICT Outside Bar: Previous breaks BOTH high AND low
            is_outside_bar = (
                prev_high > bp_high and
                prev_low < bp_low
            )
            
            # Additional validation: Outside bar should be larger
            if is_outside_bar:
                bp_range = bp_high - bp_low
                prev_range = prev_high - prev_low
                
                # Outside bar should be at least 10% larger
                if prev_range < bp_range * 1.1:
                    is_outside_bar = False
                
                # Check meaningful expansion on both sides
                high_expansion = prev_high - bp_high
                low_expansion = bp_low - prev_low
                
                min_expansion = bp_range * 0.02  # 2% of base range
                if high_expansion < min_expansion or low_expansion < min_expansion:
                    is_outside_bar = False
            
            # 3-1 PATTERN: Outside bar + Inside bar
            if is_outside_bar and is_inside_bar:
                prev_range = prev_high - prev_low
                curr_range = curr_high - curr_low
                
                # Inside bar should be notably smaller (at least 20% smaller)
                if curr_range < prev_range * 0.8:
                    # Get dates safely
                    prev_date = get_date_string(previous)
                    curr_date = get_date_string(current)
                    
                    # Ensure all dates are valid strings
                    if not prev_date:
                        prev_date = "N/A"
                    if not curr_date:
                        curr_date = "N/A"
                    
                    # Ensure all values are valid floats
                    pattern_data = {
                        'type': '3-1',
                        'has_pattern': True,
                        'direction': direction,
                        'three_candle': {
                            'high': round(float(prev_high), 2),
                            'low': round(float(prev_low), 2),
                            'close': round(float(prev_close), 2),
                            'date': str(prev_date)
                        },
                        'one_candle': {
                            'high': round(float(curr_high), 2),
                            'low': round(float(curr_low), 2),
                            'close': round(float(curr_close), 2),
                            'open': round(float(curr_open), 2),
                            'date': str(curr_date)
                        }
                    }
                    return True, pattern_data
    
    # ========================================
    # STANDALONE INSIDE BAR
    # ========================================
    if is_inside_bar:
        # Get dates safely
        prev_date = get_date_string(previous)
        curr_date = get_date_string(current)
        
        # Ensure all dates are valid strings
        if not prev_date:
            prev_date = "N/A"
        if not curr_date:
            curr_date = "N/A"
            
        pattern_data = {
            'type': 'Inside',
            'has_pattern': True,
            'direction': direction,
            'description': 'Inside Bar - Consolidation pattern',
            'one_candle': {
                'high': round(float(curr_high), 2),
                'low': round(float(curr_low), 2),
                'close': round(float(curr_close), 2),
                'open': round(float(curr_open), 2),
                'date': str(curr_date)
            },
            'previous_candle': {
                'high': round(float(prev_high), 2),
                'low': round(float(prev_low), 2),
                'date': str(prev_date)
            }
        }
        return True, pattern_data
    
    # No pattern detected
    return False, None

@app.route('/')
def index():
    """Serve the main page"""
    html_files = [
        'lemon_squeeze_with_howto.html',
        'lemon_squeeze_with_volemon__4___2_.html',
        'lemon_squeeze_webapp.html',
        'lemon_squeeze.html',
        'index.html'
    ]
    
    for html_file in html_files:
        if os.path.exists(html_file):
            return send_from_directory('.', html_file)
    
    return "<h1>🍋 Lemon Squeeze - Backend Ready!</h1>"

# ===== AUTHENTICATION ROUTES =====

@app.route('/api/auth/signup', methods=['POST'])
def signup():
    """Register a new user"""
    try:
        data = request.json
        name = data.get('name', '').strip()
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        
        # Validation
        if not name or not email or not password:
            return jsonify({'success': False, 'error': 'All fields are required'}), 400
        
        if len(password) < 6:
            return jsonify({'success': False, 'error': 'Password must be at least 6 characters'}), 400
        
        if '@' not in email or '.' not in email:
            return jsonify({'success': False, 'error': 'Invalid email format'}), 400
        
        # Check if email already exists
        db = get_db()
        existing_user = db.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone()
        
        if existing_user:
            db.close()
            return jsonify({'success': False, 'error': 'Email already registered'}), 400
        
        # Create new user
        password_hash = hash_password(password)
        cursor = db.execute(
            'INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)',
            (name, email, password_hash)
        )
        user_id = cursor.lastrowid
        
        # Create default settings
        db.execute('INSERT INTO user_settings (user_id) VALUES (?)', (user_id,))
        
        db.commit()
        
        # Get user data
        user = db.execute('SELECT id, name, email, created_at FROM users WHERE id = ?', (user_id,)).fetchone()
        db.close()
        
        # Create session
        session.permanent = True
        session['user_id'] = user['id']
        session['user_name'] = user['name']
        session['user_email'] = user['email']
        
        return jsonify({
            'success': True,
            'user': {
                'id': user['id'],
                'name': user['name'],
                'email': user['email'],
                'bio': '',
                'trader_type': 'swing_trader',
                'avatar': user['name'][0].upper(),
                'joinedDate': user['created_at']
            }
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/auth/signin', methods=['POST'])
def signin():
    """Sign in an existing user"""
    try:
        data = request.json
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        
        if not email or not password:
            return jsonify({'success': False, 'error': 'Email and password required'}), 400
        
        # Find user
        db = get_db()
        user = db.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        
        if not user:
            db.close()
            return jsonify({'success': False, 'error': 'Invalid email or password'}), 401
        
        # Verify password
        if not verify_password(password, user['password_hash']):
            db.close()
            return jsonify({'success': False, 'error': 'Invalid email or password'}), 401
        
        # Check if account is active
        if not user['is_active']:
            db.close()
            return jsonify({'success': False, 'error': 'Account is disabled'}), 401
        
        # Update last login
        db.execute('UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?', (user['id'],))
        db.commit()
        db.close()
        
        # Create session
        session.permanent = True
        session['user_id'] = user['id']
        session['user_name'] = user['name']
        session['user_email'] = user['email']
        
        return jsonify({
            'success': True,
            'user': {
                'id': user['id'],
                'name': user['name'],
                'email': user['email'],
                'bio': user['bio'] or '',
                'trader_type': user['trader_type'] or 'swing_trader',
                'avatar': user['name'][0].upper(),
                'joinedDate': user['created_at']
            }
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/auth/signout', methods=['POST'])
@login_required
def signout():
    """Sign out the current user"""
    session.clear()
    return jsonify({'success': True, 'message': 'Signed out successfully'})

@app.route('/api/auth/me', methods=['GET'])
@login_required
def get_current_user():
    """Get current user info"""
    try:
        user_id = session.get('user_id')
        
        db = get_db()
        user = db.execute('SELECT id, name, email, bio, trader_type, created_at FROM users WHERE id = ?', (user_id,)).fetchone()
        db.close()
        
        if not user:
            return jsonify({'success': False, 'error': 'User not found'}), 404
        
        return jsonify({
            'success': True,
            'user': {
                'id': user['id'],
                'name': user['name'],
                'email': user['email'],
                'bio': user['bio'] or '',
                'trader_type': user['trader_type'] or 'swing_trader',
                'avatar': user['name'][0].upper(),
                'joinedDate': user['created_at']
            }
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/profile', methods=['PUT'])
@login_required
def update_profile():
    """Update user profile"""
    try:
        user_id = session.get('user_id')
        data = request.json
        
        bio = data.get('bio', '').strip()
        trader_type = data.get('trader_type', 'swing_trader')
        
        # Validate trader type
        valid_types = ['day_trader', 'swing_trader', 'hodl']
        if trader_type not in valid_types:
            return jsonify({'success': False, 'error': 'Invalid trader type'}), 400
        
        # Validate bio length
        if len(bio) > 500:
            return jsonify({'success': False, 'error': 'Bio must be 500 characters or less'}), 400
        
        db = get_db()
        db.execute(
            'UPDATE users SET bio = ?, trader_type = ? WHERE id = ?',
            (bio, trader_type, user_id)
        )
        db.commit()
        db.close()
        
        return jsonify({'success': True, 'message': 'Profile updated successfully'})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/chat/messages', methods=['GET'])
@login_required
def get_chat_messages():
    """Get recent chat messages with trader type"""
    try:
        limit = int(request.args.get('limit', 50))
        
        db = get_db()
        # JOIN with users table to get trader_type for badges
        messages = db.execute('''
            SELECT 
                cm.id, 
                cm.user_id, 
                cm.user_name, 
                cm.message, 
                cm.created_at,
                COALESCE(u.trader_type, 'swing_trader') as user_trader_type
            FROM chat_messages cm
            LEFT JOIN users u ON cm.user_id = u.id
            ORDER BY cm.created_at DESC 
            LIMIT ?
        ''', (limit,)).fetchall()
        db.close()
        
        return jsonify({
            'success': True,
            'messages': [dict(msg) for msg in reversed(messages)]
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/chat/messages', methods=['POST'])
@login_required
def send_chat_message():
    """Send a chat message"""
    try:
        user_id = session.get('user_id')
        user_name = session.get('user_name')
        data = request.json
        
        message = data.get('message', '').strip()
        
        if not message:
            return jsonify({'success': False, 'error': 'Message cannot be empty'}), 400
        
        if len(message) > 500:
            return jsonify({'success': False, 'error': 'Message must be 500 characters or less'}), 400
        
        db = get_db()
        cursor = db.execute(
            'INSERT INTO chat_messages (user_id, user_name, message) VALUES (?, ?, ?)',
            (user_id, user_name, message)
        )
        message_id = cursor.lastrowid
        
        # Get the created message with trader_type for badge
        new_message = db.execute('''
            SELECT 
                cm.id, 
                cm.user_id, 
                cm.user_name, 
                cm.message, 
                cm.created_at,
                COALESCE(u.trader_type, 'swing_trader') as user_trader_type
            FROM chat_messages cm
            LEFT JOIN users u ON cm.user_id = u.id
            WHERE cm.id = ?
        ''', (message_id,)).fetchone()
        
        db.commit()
        db.close()
        
        return jsonify({
            'success': True,
            'message': dict(new_message)
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/favorites', methods=['GET'])
@login_required
def get_favorites():
    """Get user's favorite stocks"""
    try:
        user_id = session.get('user_id')
        
        db = get_db()
        favorites = db.execute(
            'SELECT ticker, company, timeframe, added_at FROM user_favorites WHERE user_id = ? ORDER BY added_at DESC',
            (user_id,)
        ).fetchall()
        db.close()
        
        return jsonify({
            'success': True,
            'favorites': [dict(fav) for fav in favorites]
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/favorites', methods=['POST'])
@login_required
def add_favorite():
    """Add a stock to favorites"""
    try:
        user_id = session.get('user_id')
        data = request.json
        
        ticker = data.get('ticker')
        company = data.get('company', '')
        timeframe = data.get('timeframe', 'daily')
        
        if not ticker:
            return jsonify({'success': False, 'error': 'Ticker required'}), 400
        
        db = get_db()
        try:
            db.execute(
                'INSERT INTO user_favorites (user_id, ticker, company, timeframe) VALUES (?, ?, ?, ?)',
                (user_id, ticker, company, timeframe)
            )
            db.commit()
        except sqlite3.IntegrityError:
            db.close()
            return jsonify({'success': False, 'error': 'Already in favorites'}), 400
        
        db.close()
        
        return jsonify({'success': True, 'message': 'Added to favorites'})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/favorites/<ticker>/<timeframe>', methods=['DELETE'])
@login_required
def remove_favorite(ticker, timeframe):
    """Remove a stock from favorites"""
    try:
        user_id = session.get('user_id')
        
        db = get_db()
        db.execute(
            'DELETE FROM user_favorites WHERE user_id = ? AND ticker = ? AND timeframe = ?',
            (user_id, ticker, timeframe)
        )
        db.commit()
        db.close()
        
        return jsonify({'success': True, 'message': 'Removed from favorites'})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

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
                    current_price = float(hist['Close'].iloc[-1])
                    previous_close = float(hist['Close'].iloc[-2])
                    daily_change = ((current_price - previous_close) / previous_close) * 100 if previous_close > 0 else 0.0
                    
                    current_volume = float(hist['Volume'].iloc[-1])
                    avg_volume = float(hist['Volume'].iloc[-21:-1].mean() if len(hist) > 20 else hist['Volume'].mean())
                    volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0
                    
                    float_shares = float(info.get('floatShares', info.get('sharesOutstanding', 0)) or 0)
                    market_cap = float(info.get('marketCap', 0) or 0)
                    week_high_52 = float(info.get('fiftyTwoWeekHigh', current_price) or current_price)
                    week_low_52 = float(info.get('fiftyTwoWeekLow', current_price) or current_price)
                    
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
                            'shortInterest': round(float(stock['short_interest']), 2),
                            'previousClose': round(float(previous_close), 2),
                            'currentPrice': round(float(current_price), 2),
                            'dailyChange': round(float(daily_change), 2),
                            'volume': int(current_volume),
                            'avgVolume': int(avg_volume),
                            'volumeRatio': round(float(volume_ratio), 2),
                            'floatShares': int(float_shares),
                            'marketCap': int(market_cap),
                            'daysToCover': round(float(days_to_cover), 2),
                            'weekHigh52': round(float(week_high_52), 2),
                            'weekLow52': round(float(week_low_52), 2),
                            'riskScore': round(float(risk_score), 2)
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
                    
                    # Validate pattern_data exists and has required fields
                    if has_pattern and pattern_data and isinstance(pattern_data, dict):
                        current_price = float(hist['Close'].iloc[-1])
                        previous_close = float(hist['Close'].iloc[-2])
                        daily_change = ((current_price - previous_close) / previous_close) * 100 if previous_close > 0 else 0.0
                        
                        results.append({
                            'ticker': ticker,
                            'company': info.get('longName', ticker),
                            'currentPrice': round(float(current_price), 2),
                            'dailyChange': round(float(daily_change), 2),
                            'volume': int(hist['Volume'].iloc[-1]),
                            'avgVolume': int(hist['Volume'].mean()),
                            'marketCap': int(info.get('marketCap', 0) or 0),
                            'pattern': pattern_data
                        })
                        
                        print(f"✅ {ticker}: {pattern_data.get('direction', 'unknown')} ({i}/{total})")
                
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
                    
                    # Validate pattern_data exists and is valid
                    if has_pattern and pattern_data and isinstance(pattern_data, dict):
                        results.append({
                            'ticker': ticker,
                            'company': info.get('longName', ticker),
                            'currentPrice': round(float(hist['Close'].iloc[-1]), 2),
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
                    
                    # Validate pattern_data exists and is valid
                    if has_pattern and pattern_data and isinstance(pattern_data, dict):
                        results.append({
                            'ticker': ticker,
                            'company': info.get('longName', ticker),
                            'currentPrice': round(float(hist['Close'].iloc[-1]), 2),
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
                    
                    # Validate pattern_data exists and is valid
                    if has_pattern and pattern_data and isinstance(pattern_data, dict):
                        current_price = float(hist['Close'].iloc[-1])
                        prev_price = float(hist['Close'].iloc[-2])
                        change = ((current_price - prev_price) / prev_price) * 100 if prev_price > 0 else 0.0
                        
                        results.append({
                            'ticker': ticker.replace('-USD', ''),
                            'company': name,
                            'currentPrice': round(float(current_price), 2),
                            'change': round(float(change), 2),
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
                    current_volume = float(hist['Volume'].iloc[-1])
                    avg_volume = float(hist['Volume'].iloc[:-1].mean())
                    
                    if avg_volume > 0:
                        volume_multiple = current_volume / avg_volume
                        
                        if volume_multiple >= min_volume_multiple:
                            current_price = float(hist['Close'].iloc[-1])
                            prev_price = float(hist['Close'].iloc[-2])
                            change = ((current_price - prev_price) / prev_price) * 100 if prev_price > 0 else 0.0
                            
                            results.append({
                                'ticker': ticker,
                                'company': info.get('longName', ticker),
                                'price': round(float(current_price), 2),
                                'change': round(float(change), 2),
                                'volume': int(current_volume),
                                'avg_volume': int(avg_volume),
                                'volume_multiple': round(float(volume_multiple), 2),
                                'market_cap': int(info.get('marketCap', 0) or 0)
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
                    current_price = float(hist['Close'].iloc[-1])
                    prev_price = float(hist['Close'].iloc[-2])
                    change = ((current_price - prev_price) / prev_price) * 100 if prev_price > 0 else 0.0
                    
                    current_volume = float(hist['Volume'].iloc[-1])
                    avg_volume = float(hist['Volume'].iloc[:-1].mean())
                    volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0
                    
                    # Check patterns
                    patterns = {}
                    
                    try:
                        has_pattern, pattern_data = check_strat_31(hist)
                    except Exception:
                        has_pattern = False
                        pattern_data = None
                    
                    # Use simplified pattern format for Usuals tab (matching optimized version)
                    # Extra safety: ensure pattern_data is not None and is a dict before accessing
                    if has_pattern and pattern_data is not None and isinstance(pattern_data, dict) and 'direction' in pattern_data:
                        patterns['daily'] = {
                            'type': '3-1 Strat',
                            'direction': str(pattern_data.get('direction', 'neutral'))
                        }
                    else:
                        # Check inside bar as fallback
                        try:
                            current = hist.iloc[-1]
                            previous = hist.iloc[-2]
                            is_inside = (current['High'] < previous['High'] and 
                                       current['Low'] > previous['Low'])
                            if is_inside:
                                patterns['daily'] = {
                                    'type': 'Inside Bar (1)',
                                    'direction': 'neutral'
                                }
                        except Exception:
                            # If inside bar check fails, leave patterns empty
                            pass
                    
                    # Always return the stock, even if no patterns found
                    results.append({
                        'ticker': ticker,
                        'company': info.get('longName', ticker) or ticker,
                        'price': round(float(current_price), 2),
                        'change': round(float(change), 2),
                        'volume': int(current_volume),
                        'avg_volume': int(avg_volume),
                        'volume_ratio': round(float(volume_ratio), 2),
                        'patterns': patterns if patterns else {}
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
