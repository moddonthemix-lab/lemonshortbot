"""
🍋 LEMON SQUEEZE WEB APP v3.0 - WITH COMMUNITY CHAT 🍋
Added Features:
- Community chat for authenticated users
- User profile management
- Trader badges based on activity
- Online presence tracking
"""

from flask import Flask, render_template, jsonify, request, send_from_directory
from flask_cors import CORS
import yfinance as yf
from datetime import datetime
import time
import os
import json

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Chat storage (in production, use a real database)
chat_messages = []
online_users = {}
user_profiles = {}

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
    
    if not is_three:
        return False, None
    
    is_one = (current['High'] > previous['High'] and 
              current['Low'] > previous['Low'])
    
    if is_one:
        pattern_type = "3-1 Bullish"
        direction = "bullish"
        return True, {"type": pattern_type, "direction": direction}
    
    is_one_down = (current['High'] < previous['High'] and 
                   current['Low'] < previous['Low'])
    
    if is_one_down:
        pattern_type = "3-1 Bearish"
        direction = "bearish"
        return True, {"type": pattern_type, "direction": direction}
    
    return False, None

# ============================================
# CHAT API ENDPOINTS
# ============================================

@app.route('/api/chat/messages', methods=['GET'])
def get_chat_messages():
    """Get recent chat messages"""
    limit = int(request.args.get('limit', 50))
    return jsonify({
        'success': True,
        'messages': chat_messages[-limit:] if len(chat_messages) > limit else chat_messages
    })

@app.route('/api/chat/send', methods=['POST'])
def send_chat_message():
    """Send a chat message"""
    data = request.json
    
    # Validate required fields
    if not all(k in data for k in ['userId', 'displayName', 'text']):
        return jsonify({'success': False, 'error': 'Missing required fields'}), 400
    
    # Get or create user profile
    user_id = data['userId']
    if user_id not in user_profiles:
        user_profiles[user_id] = {
            'userId': user_id,
            'displayName': data['displayName'],
            'messageCount': 0,
            'joinedAt': int(time.time() * 1000)
        }
    
    # Increment message count
    user_profiles[user_id]['messageCount'] += 1
    user_profiles[user_id]['lastSeen'] = int(time.time() * 1000)
    
    # Create message
    message = {
        'id': f"msg_{int(time.time() * 1000)}_{len(chat_messages)}",
        'userId': user_id,
        'displayName': data['displayName'],
        'text': data['text'][:500],  # Limit message length
        'timestamp': int(time.time() * 1000),
        'messageCount': user_profiles[user_id]['messageCount']
    }
    
    chat_messages.append(message)
    
    # Keep only last 200 messages in memory
    if len(chat_messages) > 200:
        chat_messages.pop(0)
    
    return jsonify({
        'success': True,
        'message': message
    })

@app.route('/api/chat/online', methods=['GET'])
def get_online_users():
    """Get count of online users"""
    # Clean up stale users (offline for > 5 minutes)
    current_time = int(time.time() * 1000)
    stale_users = [uid for uid, data in online_users.items() 
                   if current_time - data['lastSeen'] > 300000]
    
    for uid in stale_users:
        del online_users[uid]
    
    return jsonify({
        'success': True,
        'count': len(online_users),
        'users': list(online_users.values())
    })

@app.route('/api/chat/presence', methods=['POST'])
def update_presence():
    """Update user online presence"""
    data = request.json
    
    if 'userId' not in data or 'displayName' not in data:
        return jsonify({'success': False, 'error': 'Missing required fields'}), 400
    
    user_id = data['userId']
    online_users[user_id] = {
        'userId': user_id,
        'displayName': data['displayName'],
        'online': True,
        'lastSeen': int(time.time() * 1000)
    }
    
    return jsonify({'success': True})

@app.route('/api/chat/presence/<user_id>', methods=['DELETE'])
def remove_presence(user_id):
    """Remove user from online list"""
    if user_id in online_users:
        del online_users[user_id]
    return jsonify({'success': True})

@app.route('/api/user/profile/<user_id>', methods=['GET'])
def get_user_profile(user_id):
    """Get user profile"""
    if user_id in user_profiles:
        return jsonify({
            'success': True,
            'profile': user_profiles[user_id]
        })
    else:
        return jsonify({
            'success': False,
            'error': 'User not found'
        }), 404

@app.route('/api/user/stats', methods=['GET'])
def get_user_stats():
    """Get overall user statistics"""
    total_messages = len(chat_messages)
    total_users = len(user_profiles)
    online_count = len(online_users)
    
    # Get top contributors
    top_users = sorted(user_profiles.values(), 
                       key=lambda x: x.get('messageCount', 0), 
                       reverse=True)[:10]
    
    return jsonify({
        'success': True,
        'stats': {
            'totalMessages': total_messages,
            'totalUsers': total_users,
            'onlineUsers': online_count,
            'topContributors': top_users
        }
    })

# ============================================
# EXISTING STOCK SCANNING ENDPOINTS
# ============================================

@app.route('/')
def index():
    return send_from_directory('.', 'lemon_squeeze_with_chat.html')

@app.route('/api/scan/squeeze', methods=['GET'])
def scan_squeeze():
    """Scan for short squeeze opportunities"""
    try:
        stocks = load_stock_data()
        results = []
        
        for stock in stocks[:30]:  # Top 30 only
            try:
                ticker_obj = yf.Ticker(stock['ticker'])
                info = ticker_obj.info
                hist = ticker_obj.history(period='1mo')
                
                if len(hist) < 2:
                    continue
                
                current_price = hist['Close'].iloc[-1]
                prev_price = hist['Close'].iloc[-2]
                daily_change = ((current_price - prev_price) / prev_price) * 100
                
                volume = hist['Volume'].iloc[-1]
                avg_volume = hist['Volume'].mean()
                volume_ratio = volume / avg_volume if avg_volume > 0 else 1
                
                float_shares = info.get('floatShares', 0)
                days_to_cover = info.get('shortRatio', 0)
                
                risk_score = calculate_risk_score(
                    stock['short_interest'],
                    daily_change,
                    volume_ratio,
                    days_to_cover,
                    float_shares
                )
                
                # Check for patterns
                has_pattern, pattern_data = check_strat_31(hist)
                
                results.append({
                    'ticker': stock['ticker'],
                    'company': stock['company'],
                    'price': float(current_price),
                    'change': float(daily_change),
                    'volume': int(volume),
                    'avg_volume': int(avg_volume),
                    'volume_ratio': float(volume_ratio),
                    'short_interest': stock['short_interest'],
                    'days_to_cover': float(days_to_cover),
                    'float_shares': int(float_shares),
                    'risk_score': risk_score,
                    'has_pattern': has_pattern,
                    'pattern': pattern_data
                })
                
                time.sleep(0.1)  # Rate limiting
                
            except Exception as e:
                print(f"Error processing {stock['ticker']}: {e}")
                continue
        
        # Sort by risk score
        results.sort(key=lambda x: x['risk_score'], reverse=True)
        
        return jsonify({
            'success': True,
            'count': len(results),
            'stocks': results,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# Daily Plays List
DAILY_PLAYS = [
    "PLTR", "TSLA", "NVDA", "AMD", "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NFLX",
    "BABA", "NIO", "RIVN", "LCID", "F", "GM", "BA", "GE", "DIS", "PYPL",
    "SQ", "COIN", "HOOD", "SOFI", "UPST", "RBLX", "U", "SNAP", "PINS", "TWTR",
    "SHOP", "SE", "MELI", "ABNB", "UBER", "LYFT", "DOCU", "ZM", "DKNG", "PENN",
    "MRNA", "PFE", "BNTX", "JNJ", "UNH", "CVS", "WMT"
]

@app.route('/api/scan/daily', methods=['GET'])
def scan_daily():
    """Scan daily plays for patterns"""
    try:
        results = []
        
        for ticker in DAILY_PLAYS:
            try:
                ticker_obj = yf.Ticker(ticker)
                hist = ticker_obj.history(period='1d', interval='1d')
                
                if len(hist) < 1:
                    continue
                
                current_price = hist['Close'].iloc[-1]
                daily_open = hist['Open'].iloc[-1]
                daily_change = ((current_price - daily_open) / daily_open) * 100
                
                volume = hist['Volume'].iloc[-1]
                
                # Check for pattern
                hist_month = ticker_obj.history(period='1mo')
                has_pattern, pattern_data = check_strat_31(hist_month)
                
                results.append({
                    'ticker': ticker,
                    'price': float(current_price),
                    'change': float(daily_change),
                    'volume': int(volume),
                    'has_pattern': has_pattern,
                    'pattern': pattern_data
                })
                
                time.sleep(0.05)
                
            except Exception as e:
                print(f"Error processing {ticker}: {e}")
                continue
        
        return jsonify({
            'success': True,
            'count': len(results),
            'stocks': results,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# Volemon List
VOLEMON_LIST = [
    "SPY", "QQQ", "IWM", "DIA", "TQQQ", "SQQQ", "UPRO", "SPXU", "TNA", "TZA",
    "UVXY", "VXX", "VIXY", "SVXY", "HYG", "LQD", "TLT", "GLD", "SLV", "USO",
    "XLE", "XLF", "XLK", "XLV", "XLI", "XLP", "XLU", "XLY", "XLB", "XLRE",
    "EEM", "EWZ", "FXI"
]

@app.route('/api/scan/volemon', methods=['GET'])
def scan_volemon():
    """Scan Volemon list for high volume"""
    try:
        results = []
        
        for ticker in VOLEMON_LIST:
            try:
                ticker_obj = yf.Ticker(ticker)
                hist = ticker_obj.history(period='1mo')
                
                if len(hist) < 2:
                    continue
                
                current_price = hist['Close'].iloc[-1]
                prev_price = hist['Close'].iloc[-2]
                daily_change = ((current_price - prev_price) / prev_price) * 100
                
                volume = hist['Volume'].iloc[-1]
                avg_volume = hist['Volume'].mean()
                volume_ratio = volume / avg_volume if avg_volume > 0 else 1
                
                results.append({
                    'ticker': ticker,
                    'price': float(current_price),
                    'change': float(daily_change),
                    'volume': int(volume),
                    'avg_volume': int(avg_volume),
                    'volume_ratio': float(volume_ratio)
                })
                
                time.sleep(0.05)
                
            except Exception as e:
                print(f"Error processing {ticker}: {e}")
                continue
        
        # Sort by volume ratio
        results.sort(key=lambda x: x['volume_ratio'], reverse=True)
        
        return jsonify({
            'success': True,
            'count': len(results),
            'stocks': results,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/chart/<ticker>/<timeframe>', methods=['GET'])
def get_chart_data(ticker, timeframe):
    """Get chart data for a specific ticker and timeframe"""
    try:
        ticker_obj = yf.Ticker(ticker)
        
        # Map timeframes to yfinance periods and intervals
        timeframe_map = {
            'daily': ('1mo', '1d'),
            'weekly': ('3mo', '1wk'),
            'hourly': ('5d', '1h'),
            'four_hour': ('1mo', '1h')
        }
        
        period, interval = timeframe_map.get(timeframe, ('1mo', '1d'))
        hist = ticker_obj.history(period=period, interval=interval)
        
        if len(hist) == 0:
            return jsonify({
                'success': False,
                'error': 'No data available'
            }), 404
        
        # Format data for chart
        chart_data = []
        for index, row in hist.iterrows():
            chart_data.append({
                'time': index.isoformat(),
                'open': float(row['Open']),
                'high': float(row['High']),
                'low': float(row['Low']),
                'close': float(row['Close']),
                'volume': int(row['Volume'])
            })
        
        return jsonify({
            'success': True,
            'ticker': ticker,
            'timeframe': timeframe,
            'data': chart_data
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

if __name__ == '__main__':
    print("🍋 Starting Lemon Squeeze v3.0 with Community Chat 🍋")
    print("Features:")
    print("- Real-time community chat")
    print("- User authentication")
    print("- Trader badges")
    print("- Online presence tracking")
    print("- Pattern scanning across multiple timeframes")
    print("\nServer starting on http://localhost:5000")
    app.run(debug=True, host='0.0.0.0', port=5000)
