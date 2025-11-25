"""
🍋 LEMON SQUEEZE WEB APP v4.0 - WITH POSTGRESQL DATABASE 🍋
Complete backend with persistent storage for all user data
"""

from flask import Flask, render_template, jsonify, request, send_from_directory, session
import yfinance as yf
from datetime import datetime
import time
import os
import json
import hashlib
import secrets
import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))

# ===== DATABASE CONFIGURATION =====
DATABASE_URL = os.environ.get('DATABASE_URL')

@contextmanager
def get_db():
    """Context manager for database connections"""
    conn = psycopg2.connect(DATABASE_URL)
    conn.cursor_factory = RealDictCursor
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def init_db():
    """Initialize database tables"""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Users table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    email TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    password TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # User profiles table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS profiles (
                    email TEXT PRIMARY KEY,
                    bio TEXT DEFAULT '',
                    trader_types JSONB DEFAULT '[]'::jsonb,
                    FOREIGN KEY (email) REFERENCES users(email) ON DELETE CASCADE
                )
            """)
            
            # Username changes table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS username_changes (
                    id SERIAL PRIMARY KEY,
                    email TEXT NOT NULL,
                    old_name TEXT,
                    new_name TEXT,
                    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (email) REFERENCES users(email) ON DELETE CASCADE
                )
            """)
            
            # Favorites table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS favorites (
                    id SERIAL PRIMARY KEY,
                    email TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    company TEXT,
                    timeframe TEXT,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (email) REFERENCES users(email) ON DELETE CASCADE,
                    UNIQUE(email, ticker, timeframe)
                )
            """)
            
            # Trading journal table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS journal_entries (
                    id TEXT PRIMARY KEY,
                    email TEXT NOT NULL,
                    date TEXT NOT NULL,
                    profited BOOLEAN,
                    percent REAL,
                    type TEXT,
                    stock TEXT,
                    reason TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (email) REFERENCES users(email) ON DELETE CASCADE
                )
            """)
            
            conn.commit()
            print("✅ Database initialized successfully!")
    except Exception as e:
        print(f"❌ Database initialization error: {e}")

# Initialize database on startup
if DATABASE_URL:
    init_db()
else:
    print("⚠️ WARNING: DATABASE_URL not set! Add PostgreSQL database in Railway.")

# Load high short interest stocks
def load_stock_data():
    """Load stocks from CSV - LIMITED TO TOP 30"""
    stocks = []
    csv_path = 'high_short_stocks.csv'
    
    if not os.path.exists(csv_path):
        print(f"Warning: {csv_path} not found")
        return stocks
    
    try:
        with open(csv_path, 'r') as f:
            next(f)  # Skip header
            for i, line in enumerate(f):
                if i >= 30:  # LIMIT TO TOP 30
                    break
                parts = line.strip().split(',')
                if len(parts) >= 3:
                    stocks.append({
                        'ticker': parts[0].strip(),
                        'company': parts[1].strip(),
                        'short_interest': float(parts[2].strip())
                    })
    except Exception as e:
        print(f"Error loading CSV: {e}")
    
    return stocks

HIGH_SHORT_STOCKS = load_stock_data()

# Daily plays list (47 stocks)
DAILY_PLAYS_TICKERS = [
    'TSLA', 'NVDA', 'AMD', 'AAPL', 'MSFT', 'GOOGL', 'META', 'AMZN',
    'NFLX', 'DIS', 'COIN', 'SQ', 'PYPL', 'SHOP', 'UBER', 'LYFT',
    'PLTR', 'SOFI', 'RIVN', 'LCID', 'NIO', 'XPEV', 'LI',
    'GME', 'AMC', 'BB', 'BBBY', 'TLRY', 'SNDL', 'MARA', 'RIOT',
    'SPCE', 'ARKK', 'HOOD', 'RBLX', 'U', 'SNAP', 'PINS',
    'DKNG', 'DRAFT', 'PENN', 'FUBO', 'SKLZ', 'PTON', 'ZM', 'DOCU', 'ROKU'
]

# Volemon stocks (33 stocks - volume spike monitoring)
VOLEMON_TICKERS = [
    'SPY', 'QQQ', 'IWM', 'DIA',  # Major ETFs
    'TSLA', 'NVDA', 'AMD', 'AAPL', 'MSFT', 'GOOGL', 'META', 'AMZN',
    'GME', 'AMC', 'PLTR', 'SOFI', 'COIN', 'HOOD',
    'MARA', 'RIOT', 'TLRY', 'SNDL',
    'RIVN', 'LCID', 'NIO', 'XPEV',
    'RBLX', 'SNAP', 'U', 'DKNG', 'PTON', 'ZM', 'ROKU'
]

# The Usuals (user's watchlist - 14 stocks)
USUALS_TICKERS = [
    'TSLA', 'NVDA', 'AMD', 'AAPL', 'MSFT',
    'GME', 'AMC', 'PLTR', 'COIN',
    'MARA', 'RIOT', 'RIVN', 'NIO', 'RBLX'
]

# Crypto tickers
CRYPTO_TICKERS = ['BTC-USD', 'ETH-USD', 'SOL-USD', 'DOGE-USD', 'SHIB-USD']

def hash_password(password):
    """Hash password with SHA-256"""
    return hashlib.sha256(password.encode()).hexdigest()

# ===== AUTHENTICATION ENDPOINTS =====

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
        
        if len(password) < 6:
            return jsonify({'success': False, 'error': 'Password must be at least 6 characters'}), 400
        
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Check if email exists
            cursor.execute('SELECT email FROM users WHERE email = %s', (email,))
            if cursor.fetchone():
                return jsonify({'success': False, 'error': 'Email already registered'}), 400
            
            # Create user
            cursor.execute(
                'INSERT INTO users (email, name, password, created_at) VALUES (%s, %s, %s, %s)',
                (email, name, hash_password(password), datetime.now())
            )
            
            # Create empty profile
            cursor.execute(
                'INSERT INTO profiles (email, bio, trader_types) VALUES (%s, %s, %s)',
                (email, '', '[]')
            )
            
            conn.commit()
        
        # Create session
        session['user_email'] = email
        
        return jsonify({
            'success': True,
            'user': {
                'name': name,
                'email': email,
                'joinedDate': datetime.now().isoformat(),
                'avatar': name[0].upper()
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
        
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT name, password, created_at FROM users WHERE email = %s', (email,))
            user = cursor.fetchone()
            
            if not user:
                return jsonify({'success': False, 'error': 'Invalid email or password'}), 401
            
            if user['password'] != hash_password(password):
                return jsonify({'success': False, 'error': 'Invalid email or password'}), 401
        
        # Create session
        session['user_email'] = email
        
        return jsonify({
            'success': True,
            'user': {
                'name': user['name'],
                'email': email,
                'joinedDate': user['created_at'].isoformat(),
                'avatar': user['name'][0].upper()
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/auth/me', methods=['GET'])
def get_current_user():
    """Get current authenticated user"""
    try:
        user_email = session.get('user_email')
        
        if not user_email:
            return jsonify({'success': False, 'error': 'Not authenticated'}), 401
        
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT name, email, created_at FROM users WHERE email = %s', (user_email,))
            user = cursor.fetchone()
            
            if not user:
                session.clear()
                return jsonify({'success': False, 'error': 'User not found'}), 404
        
        return jsonify({
            'success': True,
            'user': {
                'name': user['name'],
                'email': user['email'],
                'joinedDate': user['created_at'].isoformat(),
                'avatar': user['name'][0].upper()
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/auth/signout', methods=['POST'])
def signout():
    """Sign out user"""
    session.clear()
    return jsonify({'success': True})

# ===== FAVORITES ENDPOINTS =====

@app.route('/api/favorites', methods=['GET'])
def get_favorites():
    """Get user's favorites"""
    try:
        user_email = session.get('user_email')
        
        if not user_email:
            return jsonify({'success': False, 'error': 'Not authenticated'}), 401
        
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT ticker, company, timeframe, added_at
                FROM favorites
                WHERE email = %s
                ORDER BY added_at DESC
            ''', (user_email,))
            
            favorites = cursor.fetchall()
        
        return jsonify({
            'success': True,
            'favorites': [dict(f) for f in favorites]
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
        ticker = data.get('ticker', '').upper()
        company = data.get('company', '')
        timeframe = data.get('timeframe', '')
        
        if not ticker or not timeframe:
            return jsonify({'success': False, 'error': 'Ticker and timeframe required'}), 400
        
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO favorites (email, ticker, company, timeframe, added_at)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (email, ticker, timeframe) DO NOTHING
            ''', (user_email, ticker, company, timeframe, datetime.now()))
            
            conn.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/favorites/<ticker>/<timeframe>', methods=['DELETE'])
def remove_favorite(ticker, timeframe):
    """Remove a favorite stock"""
    try:
        user_email = session.get('user_email')
        
        if not user_email:
            return jsonify({'success': False, 'error': 'Not authenticated'}), 401
        
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                DELETE FROM favorites
                WHERE email = %s AND ticker = %s AND timeframe = %s
            ''', (user_email, ticker.upper(), timeframe))
            
            conn.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ===== PROFILE ENDPOINTS =====

@app.route('/api/profile', methods=['GET'])
def get_profile():
    """Get user profile"""
    try:
        user_email = session.get('user_email')
        if not user_email:
            return jsonify({'success': False, 'error': 'Not authenticated'}), 401
        
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Get user info
            cursor.execute('SELECT name, created_at FROM users WHERE email = %s', (user_email,))
            user = cursor.fetchone()
            
            # Get profile
            cursor.execute('SELECT bio, trader_types FROM profiles WHERE email = %s', (user_email,))
            profile = cursor.fetchone()
            
            # Get username changes
            cursor.execute('''
                SELECT old_name, new_name, changed_at
                FROM username_changes
                WHERE email = %s
                ORDER BY changed_at DESC
            ''', (user_email,))
            changes = cursor.fetchall()
        
        return jsonify({
            'success': True,
            'profile': {
                'name': user['name'],
                'email': user_email,
                'bio': profile['bio'] if profile else '',
                'trader_types': profile['trader_types'] if profile else [],
                'username_changes': [{'old_name': c['old_name'], 'new_name': c['new_name'], 'date': c['changed_at'].isoformat()} for c in changes],
                'joined_date': user['created_at'].isoformat()
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/profile/update', methods=['POST'])
def update_profile():
    """Update user profile"""
    try:
        user_email = session.get('user_email')
        if not user_email:
            return jsonify({'success': False, 'error': 'Not authenticated'}), 401
        
        data = request.json
        
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Update bio
            if 'bio' in data:
                bio = data['bio'].strip()[:100]
                cursor.execute('UPDATE profiles SET bio = %s WHERE email = %s', (bio, user_email))
            
            # Update trader types
            if 'trader_types' in data:
                valid_types = ['day', 'swing', 'hodler']
                trader_types = [t for t in data['trader_types'] if t in valid_types]
                cursor.execute('UPDATE profiles SET trader_types = %s WHERE email = %s', (json.dumps(trader_types), user_email))
            
            # Update username (with restrictions)
            if 'name' in data:
                new_name = data['name'].strip()
                
                if not new_name:
                    return jsonify({'success': False, 'error': 'Name cannot be empty'}), 400
                
                # Check recent changes
                cursor.execute('''
                    SELECT COUNT(*) as count FROM username_changes
                    WHERE email = %s AND changed_at > NOW() - INTERVAL '14 days'
                ''', (user_email,))
                
                recent_count = cursor.fetchone()['count']
                
                if recent_count >= 2:
                    return jsonify({
                        'success': False,
                        'error': 'You can only change your username 2 times every 14 days'
                    }), 400
                
                # Get old name
                cursor.execute('SELECT name FROM users WHERE email = %s', (user_email,))
                old_name = cursor.fetchone()['name']
                
                # Update name
                cursor.execute('UPDATE users SET name = %s WHERE email = %s', (new_name, user_email))
                
                # Record change
                cursor.execute('''
                    INSERT INTO username_changes (email, old_name, new_name, changed_at)
                    VALUES (%s, %s, %s, %s)
                ''', (user_email, old_name, new_name, datetime.now()))
            
            conn.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ===== SETTINGS ENDPOINTS =====

@app.route('/api/settings/email', methods=['POST'])
def update_email():
    """Update user email"""
    try:
        user_email = session.get('user_email')
        if not user_email:
            return jsonify({'success': False, 'error': 'Not authenticated'}), 401
        
        data = request.json
        new_email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        
        if not new_email or not password:
            return jsonify({'success': False, 'error': 'Email and password required'}), 400
        
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Verify password
            cursor.execute('SELECT password FROM users WHERE email = %s', (user_email,))
            user = cursor.fetchone()
            
            if user['password'] != hash_password(password):
                return jsonify({'success': False, 'error': 'Invalid password'}), 401
            
            # Check if new email exists
            cursor.execute('SELECT email FROM users WHERE email = %s', (new_email,))
            if cursor.fetchone() and new_email != user_email:
                return jsonify({'success': False, 'error': 'Email already in use'}), 400
            
            # Update email everywhere
            cursor.execute('UPDATE users SET email = %s WHERE email = %s', (new_email, user_email))
            cursor.execute('UPDATE profiles SET email = %s WHERE email = %s', (new_email, user_email))
            cursor.execute('UPDATE favorites SET email = %s WHERE email = %s', (new_email, user_email))
            cursor.execute('UPDATE journal_entries SET email = %s WHERE email = %s', (new_email, user_email))
            cursor.execute('UPDATE username_changes SET email = %s WHERE email = %s', (new_email, user_email))
            
            conn.commit()
        
        session['user_email'] = new_email
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/settings/password', methods=['POST'])
def update_password():
    """Update user password"""
    try:
        user_email = session.get('user_email')
        if not user_email:
            return jsonify({'success': False, 'error': 'Not authenticated'}), 401
        
        data = request.json
        current_password = data.get('current_password', '')
        new_password = data.get('new_password', '')
        
        if not current_password or not new_password:
            return jsonify({'success': False, 'error': 'Both passwords required'}), 400
        
        if len(new_password) < 6:
            return jsonify({'success': False, 'error': 'New password must be at least 6 characters'}), 400
        
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Verify current password
            cursor.execute('SELECT password FROM users WHERE email = %s', (user_email,))
            user = cursor.fetchone()
            
            if user['password'] != hash_password(current_password):
                return jsonify({'success': False, 'error': 'Current password is incorrect'}), 401
            
            # Update password
            cursor.execute('UPDATE users SET password = %s WHERE email = %s', (hash_password(new_password), user_email))
            
            conn.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ===== TRADING JOURNAL ENDPOINTS =====

@app.route('/api/journal', methods=['GET'])
def get_journal_entries():
    """Get all journal entries for user"""
    try:
        user_email = session.get('user_email')
        if not user_email:
            return jsonify({'success': False, 'error': 'Not authenticated'}), 401
        
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, date, profited, percent, type, stock, reason, created_at
                FROM journal_entries
                WHERE email = %s
                ORDER BY date DESC
            ''', (user_email,))
            
            entries = cursor.fetchall()
        
        return jsonify({
            'success': True,
            'entries': [dict(e) for e in entries]
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/journal', methods=['POST'])
def add_journal_entry():
    """Add a trading journal entry"""
    try:
        user_email = session.get('user_email')
        if not user_email:
            return jsonify({'success': False, 'error': 'Not authenticated'}), 401
        
        data = request.json
        
        entry_id = secrets.token_hex(8)
        entry = {
            'id': entry_id,
            'date': data.get('date', datetime.now().strftime('%Y-%m-%d')),
            'profited': data.get('profited', False),
            'percent': float(data.get('percent', 0)),
            'type': data.get('type', 'shares'),
            'stock': data.get('stock', '').upper(),
            'reason': data.get('reason', '').strip()[:500],
        }
        
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO journal_entries (id, email, date, profited, percent, type, stock, reason, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (entry_id, user_email, entry['date'], entry['profited'], entry['percent'],
                  entry['type'], entry['stock'], entry['reason'], datetime.now()))
            
            conn.commit()
        
        return jsonify({
            'success': True,
            'entry': entry
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/journal/<entry_id>', methods=['DELETE'])
def delete_journal_entry(entry_id):
    """Delete a journal entry"""
    try:
        user_email = session.get('user_email')
        if not user_email:
            return jsonify({'success': False, 'error': 'Not authenticated'}), 401
        
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                DELETE FROM journal_entries
                WHERE id = %s AND email = %s
            ''', (entry_id, user_email))
            
            conn.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

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
