# 🔑 Tradier API Setup Guide

If you're experiencing issues with Yahoo Finance (rate limits, parsing errors, or "delisted" errors), you can add Tradier as a reliable fallback data source.

## Why Use Tradier?

- **Free Tier Available**: Tradier offers a free sandbox account with 120 API calls per minute
- **Reliable**: No parsing errors or rate limit issues like Yahoo Finance
- **Real-time Data**: Get actual market data (with 15-minute delay on free tier)
- **Automatic Fallback**: The app will automatically use Tradier when Yahoo Finance fails

## Setup Instructions

### Step 1: Create a Tradier Developer Account

1. Go to [Tradier Developer Portal](https://developer.tradier.com/)
2. Click **"Sign Up"** in the top right
3. Create a free account with your email

### Step 2: Get Your API Key

1. Log in to your Tradier Developer account
2. Go to **"Applications"** in the dashboard
3. Click **"Create New Application"**
   - Application Name: `Lemon Squeeze Bot`
   - Description: `Stock market scanner`
4. Once created, you'll see your **API Access Token**
5. Copy this token (it looks like: `Bearer ABC123xyz...`)

### Step 3: Add API Key to Your Environment

#### For Local Development:

**On Linux/Mac:**
```bash
export TRADIER_API_KEY="your_api_key_here"
```

**OPTIONAL - Use Tradier as PRIMARY data source** (recommended if Yahoo Finance is broken):
```bash
export TRADIER_API_KEY="your_api_key_here"
export USE_TRADIER_FIRST="true"
```

Add this to your `~/.bashrc` or `~/.zshrc` to make it permanent:
```bash
echo 'export TRADIER_API_KEY="your_api_key_here"' >> ~/.bashrc
echo 'export USE_TRADIER_FIRST="true"' >> ~/.bashrc
source ~/.bashrc
```

**On Windows:**
```cmd
set TRADIER_API_KEY=your_api_key_here
set USE_TRADIER_FIRST=true
```

Or use PowerShell:
```powershell
$env:TRADIER_API_KEY="your_api_key_here"
$env:USE_TRADIER_FIRST="true"
```

#### For Production (Railway, Heroku, etc.):

1. Go to your deployment platform's dashboard
2. Find **Environment Variables** or **Config Vars**
3. Add:
   - **Key**: `TRADIER_API_KEY`
   - **Value**: Your API token
   - **Key** (Optional): `USE_TRADIER_FIRST`
   - **Value**: `true` (use Tradier as primary source)

**Railway:**
- Settings → Variables → Add `TRADIER_API_KEY`
- Settings → Variables → Add `USE_TRADIER_FIRST=true` (optional)

**Heroku:**
- Settings → Config Vars → Add `TRADIER_API_KEY`
- Settings → Config Vars → Add `USE_TRADIER_FIRST=true` (optional)

**Docker:**
Add to your `docker-compose.yml`:
```yaml
environment:
  - TRADIER_API_KEY=your_api_key_here
  - USE_TRADIER_FIRST=true  # Optional: use Tradier first
```

### Step 4: Verify Setup

1. Restart your application
2. Check the logs when running a scan
3. You should see messages like:
   - `🔄 AAPL: Tradier fallback SUCCESS`
   - This means Yahoo failed but Tradier worked!

## API Limits

**Free Sandbox Account:**
- 120 requests per minute
- Delayed data (15 minutes)
- Perfect for development and testing

**Production Account (Optional):**
- Higher rate limits
- Real-time data
- Costs apply (see Tradier pricing)

## Troubleshooting

### "No Tradier API key found"
- Make sure you exported the environment variable
- Restart your terminal/application after setting it
- Check for typos in the variable name

### "Tradier also failed"
- Check if your API key is valid
- Verify you haven't exceeded the 120 calls/minute limit
- Make sure your Tradier account is active

### Still getting Yahoo Finance errors?
- This is normal - Yahoo Finance can be unreliable
- With Tradier configured, the app will automatically fall back
- Failed tickers will be skipped, but most should work

## Data Source Modes

### Mode 1: Yahoo First (Default)
- Tries Yahoo Finance first with 3 retries
- Falls back to Tradier if all Yahoo attempts fail
- **Best for**: Normal operation when Yahoo works most of the time

### Mode 2: Tradier First (`USE_TRADIER_FIRST=true`)
- Tries Tradier API first
- Falls back to Yahoo Finance if Tradier fails
- **Best for**: When Yahoo Finance is completely broken
- **Rate Limit**: 120 calls/minute, so scans will be paced

### Rate Limit Protection
- The app tracks Tradier API usage automatically
- Warns you at 100/120 calls per minute
- Blocks calls at 120/120 to prevent errors
- Automatically waits when limit is reached

**Example**: Scanning 47 stocks with Tradier-first mode takes about 30-40 seconds to stay under the 120 calls/minute limit.

---

**Need Help?**
- Tradier Docs: https://documentation.tradier.com/
- Tradier Support: https://tradier.com/contact
