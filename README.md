# 🍋 Lemon Squeeze - Short Squeeze Screener

**When Life Gives You Shorts... Squeeze Them!**

A powerful web-based short squeeze screener with real-time data, risk scoring, and beautiful UI.

![Lemon Squeeze](https://img.shields.io/badge/version-2.0-yellow)
![Python](https://img.shields.io/badge/python-3.7+-blue)
![License](https://img.shields.io/badge/license-MIT-green)

---

## 🌟 Features

### 🎯 Real-Time Screening
- Live data from Yahoo Finance API
- Scans 45+ stocks with high short interest
- 2-5 minute comprehensive analysis

### 📊 Enhanced Metrics
- **Volume Analysis**: Current vs average volume ratio
- **Float Size**: Smaller floats = easier squeezes
- **Days to Cover**: Pressure indicator for shorts
- **Market Cap**: Stock size classification
- **52-Week Range**: Price context and breakout potential

### 🎲 Risk Scoring Algorithm (0-100)
Every stock gets scored based on:
- **Short Interest** (30% weight) - Higher = more shorts trapped
- **Daily Gain** (25% weight) - Bigger moves = more squeeze potential
- **Volume Ratio** (20% weight) - High volume confirms the move
- **Days to Cover** (15% weight) - Optimal range: 5-10 days
- **Float Size** (10% weight) - Smaller floats squeeze easier

### 📈 Historical Tracking
- Auto-saves every scan
- Compare scans to spot trends
- Identify "hot stocks" appearing repeatedly
- Track which opportunities materialize

### 🎨 Beautiful Interface
- Clean, modern design
- Mobile-responsive
- Real-time progress updates
- Color-coded risk levels

---

## 🚀 Quick Start

### Prerequisites
- Python 3.7 or higher
- pip (Python package manager)

### Installation

1. **Clone the repository**
```bash
git clone https://github.com/yourusername/lemon-squeeze.git
cd lemon-squeeze
```

2. **Install dependencies**
```bash
pip install -r requirements_webapp.txt
```

3. **Run the web app**
```bash
python lemon_squeeze_webapp.py
```

4. **Open your browser**
```
http://localhost:5000
```

That's it! 🎉

---

## 📖 Usage

### Running a Scan

1. **Set your criteria:**
   - Min Short Interest (default: 25%)
   - Min Daily Gain (default: 15%)
   - Min Volume Ratio (default: 1.5x)
   - Min Risk Score (default: 60)

2. **Click "SCAN FOR SQUEEZES"**
   - Takes 2-5 minutes
   - Fetches live data for each stock
   - Calculates risk scores

3. **Review results:**
   - Sorted by risk score (highest first!)
   - Detailed metrics for each candidate
   - Summary statistics

### Understanding Risk Scores

- 🔥 **90-100**: EXTREME squeeze potential (very rare!)
- 🚀 **80-89**: HIGH squeeze potential
- 💪 **70-79**: GOOD squeeze potential
- ✅ **60-69**: MODERATE squeeze potential
- ⚡ **50-59**: LOW squeeze potential

---

## 📁 Project Structure

```
lemon-squeeze/
├── lemon_squeeze_webapp.py      # Flask backend (real data)
├── lemon_squeeze_webapp.html    # Beautiful frontend
├── high_short_stocks.csv        # Stock data (45 stocks)
├── requirements_webapp.txt      # Python dependencies
├── README.md                    # This file
└── scan_history.json           # Auto-generated scan history
```

---

## 🔧 Configuration

### Adjust Scan Criteria

Edit the default values in the HTML interface or change them programmatically:

```python
min_short = 25      # Minimum short interest %
min_gain = 15       # Minimum daily gain %
min_vol_ratio = 1.5 # Minimum volume ratio
min_risk = 60       # Minimum risk score
```

### Update Stock List

Edit `high_short_stocks.csv`:
```csv
TICKER,Company Name,Short%
BYND,Beyond Meat Inc,38.94
SOUN,SoundHound AI Inc,33.74
```

Get updated data from: https://www.highshortinterest.com/

---

## 📊 API Endpoints

### POST /api/scan
Scan for squeeze candidates

**Request:**
```json
{
  "minShort": 25,
  "minGain": 15,
  "minVolRatio": 1.5,
  "minRisk": 60
}
```

**Response:**
```json
{
  "success": true,
  "results": [
    {
      "ticker": "BYND",
      "company": "Beyond Meat Inc",
      "shortInterest": 38.94,
      "dailyChange": 24.67,
      "riskScore": 87.5,
      ...
    }
  ],
  "timestamp": "2025-10-21T17:00:00"
}
```

### GET /api/history
Get scan history

**Response:**
```json
{
  "success": true,
  "history": [...]
}
```

---

## 🎓 How It Works

### 1. Data Collection
- Loads stocks from CSV (25%+ short interest)
- Fetches live prices from Yahoo Finance
- Gets volume, float, and other metrics

### 2. Risk Calculation
```python
risk_score = (
    short_score * 0.30 +
    gain_score * 0.25 +
    vol_score * 0.20 +
    dtc_score * 0.15 +
    float_score * 0.10
)
```

### 3. Filtering
- Applies user criteria
- Sorts by risk score
- Returns top candidates

### 4. Display
- Beautiful cards for each stock
- Color-coded risk badges
- Detailed metrics breakdown

---

## ⚠️ Disclaimer

**IMPORTANT:** This tool is for informational and educational purposes only.

- ❌ This is NOT financial advice
- ❌ Not a guarantee of profits
- ❌ Short squeezes are extremely high-risk
- ✅ Always do your own research (DYOR)
- ✅ Never invest more than you can afford to lose
- ✅ Use stop-losses and proper risk management

Market data is delayed 15-20 minutes (standard free tier). Short interest data may be 1-2 weeks old. Always verify information before making trading decisions.

---

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

---

## 📝 Roadmap

- [ ] Options data integration
- [ ] Social sentiment analysis (Reddit, Twitter)
- [ ] Real-time alerts via email/SMS
- [ ] Mobile app version
- [ ] Advanced charting
- [ ] Portfolio tracking
- [ ] Paper trading simulator

---

## 🐛 Known Issues

- macOS tkinter compatibility issues (use web version instead)
- Yahoo Finance API occasional outages
- Some delisted stocks may fail to load

---

## 💡 Tips for Best Results

1. **Scan after market close** for complete daily data
2. **Run multiple scans** throughout the day
3. **Track hot stocks** appearing repeatedly
4. **Cross-reference** with news and social media
5. **Use appropriate risk management**
6. **Start with paper trading**

---

## 📚 Resources

### Learn About Short Squeezes
- [Investopedia: Short Squeeze](https://www.investopedia.com/terms/s/shortsqueeze.asp)
- [Investopedia: Short Interest](https://www.investopedia.com/terms/s/shortinterest.asp)

### Data Sources
- [High Short Interest Stocks](https://www.highshortinterest.com/)
- [Yahoo Finance](https://finance.yahoo.com/)
- [FINRA Short Interest](http://finra-markets.morningstar.com/MarketData/EquityOptions/default.jsp)

---

## 📜 License

This project is licensed under the MIT License - see the LICENSE file for details.

---

## 🙏 Acknowledgments

- Yahoo Finance for providing free market data API
- Flask for the excellent web framework
- The short squeeze community for inspiration

---

## 📸 Screenshots

### Main Interface
![Main Interface](screenshots/main.png)

### Scan Results
![Scan Results](screenshots/results.png)

### Risk Score Breakdown
![Risk Scores](screenshots/risk-scores.png)

---

Made with 🍋 and ☕ by traders, for traders.
