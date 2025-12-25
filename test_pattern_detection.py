#!/usr/bin/env python3
"""Test pattern detection to see why all stocks are showing patterns"""

import yfinance as yf
from datetime import datetime

def test_pattern_detection():
    """Test a few stocks to see what's being detected"""

    test_tickers = ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'SPY']

    for ticker in test_tickers:
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period='3mo', interval='1d')

            if len(hist) < 3:
                print(f"{ticker}: Not enough data")
                continue

            current = hist.iloc[-1]
            previous = hist.iloc[-2]
            before_prev = hist.iloc[-3]

            # Check for 3-1 pattern
            is_three = (previous['High'] > before_prev['High'] and
                       previous['Low'] < before_prev['Low'])
            is_one = (current['High'] < previous['High'] and
                     current['Low'] > previous['Low'])

            has_31 = is_three and is_one

            # Check for inside bar
            is_inside = (current['High'] < previous['High'] and
                        current['Low'] > previous['Low'])

            # Calculate validation metrics
            three_range_pct = ((previous['High'] - previous['Low']) / previous['Low']) * 100
            prev_range_pct = ((previous['High'] - previous['Low']) / previous['Low']) * 100
            avg_volume = hist['Volume'].tail(20).mean()
            current_vol_pct = (current['Volume'] / avg_volume) * 100

            print(f"\n{ticker}:")
            print(f"  3-1 Pattern (basic): {has_31}")
            print(f"  Inside Bar (basic): {is_inside}")
            print(f"  Previous bar range: {three_range_pct:.2f}%")
            print(f"  Current volume vs avg: {current_vol_pct:.1f}%")
            print(f"  Passes 0.8% range check: {three_range_pct >= 0.8}")
            print(f"  Passes 30% volume check: {current_vol_pct >= 30}")

            if has_31:
                passes_validation = three_range_pct >= 0.8 and current_vol_pct >= 30
                print(f"  ✅ 3-1 WOULD SHOW: {passes_validation}")
            elif is_inside:
                passes_validation = prev_range_pct >= 0.5 and current_vol_pct >= 30
                print(f"  ✅ INSIDE BAR WOULD SHOW: {passes_validation}")
            else:
                print(f"  ❌ No pattern")

        except Exception as e:
            print(f"{ticker}: Error - {e}")

if __name__ == '__main__':
    test_pattern_detection()
