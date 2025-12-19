# Pattern Detection - Important Notes

## Overview
This file explains the pattern detection logic and why the validation thresholds are set the way they are.

## Problem History
After multiple iterations, we found the right balance for pattern validation:

### ❌ What Didn't Work:

1. **No validation** (Original simple logic)
   - Result: 36/46 stocks showing patterns
   - Problem: Almost every stock showed a "pattern" - too many false positives
   - Not tradeable - just noise

2. **Ultra-strict validation** (2-3% range, 60-80% volume)
   - Result: Missed real patterns like coinbase inside bars
   - Problem: Too restrictive - filtered out tradeable patterns
   - User couldn't trade the good setups

### ✅ What Works:

**Minimal validation** (0.8% range for 3-1, 0.5% range for inside bars, 30% volume)
- Filters out tiny meaningless bars
- Filters out dead volume
- Still catches all real tradeable patterns
- Perfect balance between noise filtering and pattern detection

## Current Thresholds

### 3-1 Strat Patterns
```python
# Outside bar must have at least 0.8% range
three_range_pct >= 0.8%

# Volume must be at least 30% of 20-day average
current_volume >= avg_volume * 0.3
```

### Inside Bar Patterns
```python
# Previous bar must have at least 0.5% range
previous_range_pct >= 0.5%

# Volume must be at least 30% of 20-day average
current_volume >= avg_volume * 0.3
```

## Why These Numbers?

- **0.8% and 0.5% range**: These are VERY low thresholds. They only filter out the tiniest price movements that aren't tradeable anyway. Any real price action will easily exceed these.

- **30% volume**: Also very low. Only filters out completely dead volume. Real patterns will have this easily.

## DO NOT CHANGE Unless:

1. You have tested thoroughly on real market data
2. You understand the history above
3. You have a very good reason
4. You're willing to deal with either:
   - Too many false positives (if you remove validation)
   - Missing real patterns (if you make it stricter)

## Testing
When you make changes, test by:
1. Running a full Daily scan
2. Checking if you get 5-15 patterns (normal range)
3. Manually verifying the patterns are real on a chart
4. If you get 30+ patterns = too loose
5. If you get 0-2 patterns = too strict

## Last Updated
December 2025 - After extensive testing and multiple iterations
