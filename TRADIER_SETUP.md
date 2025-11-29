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

Add this to your `~/.bashrc` or `~/.zshrc` to make it permanent:
```bash
echo 'export TRADIER_API_KEY="your_api_key_here"' >> ~/.bashrc
source ~/.bashrc
```

**On Windows:**
```cmd
set TRADIER_API_KEY=your_api_key_here
```

Or use PowerShell:
```powershell
$env:TRADIER_API_KEY="your_api_key_here"
```

#### For Production (Railway, Heroku, etc.):

1. Go to your deployment platform's dashboard
2. Find **Environment Variables** or **Config Vars**
3. Add:
   - **Key**: `TRADIER_API_KEY`
   - **Value**: Your API token

**Railway:**
- Settings → Variables → Add `TRADIER_API_KEY`

**Heroku:**
- Settings → Config Vars → Add `TRADIER_API_KEY`

**Docker:**
Add to your `docker-compose.yml`:
```yaml
environment:
  - TRADIER_API_KEY=your_api_key_here
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

## Alternative: Use Tradier-Only Mode

If Yahoo Finance is completely broken, you can modify the code to use Tradier as the primary source. Let me know if you need help with this!

---

**Need Help?**
- Tradier Docs: https://documentation.tradier.com/
- Tradier Support: https://tradier.com/contact
