# SovereignForge Telegram Alert Setup

This guide explains how to set up Telegram alerts for the SovereignForge arbitrage detection system.

## 🚀 Quick Setup

### 1. Create a Telegram Bot

1. **Open Telegram** and search for `@BotFather`
2. **Send** `/newbot` to BotFather
3. **Follow prompts** to create your bot:
   - Choose a name (e.g., "SovereignForge Alerts")
   - Choose a username (must end with "bot", e.g., "sovereignforge_bot")
4. **Copy the API token** - you'll need this next

### 2. Get Your Chat ID

1. **Start a chat** with your new bot by sending `/start`
2. **Send a message** to the bot (any message)
3. **Get your Chat ID** by visiting:
   ```
   https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates
   ```
   Replace `<YOUR_BOT_TOKEN>` with your actual token.

### 3. Configure Environment Variables

Set these environment variables before running SovereignForge:

```bash
# Required
export TELEGRAM_BOT_TOKEN="your_bot_token_here"
export TELEGRAM_CHAT_IDS="your_chat_id_here"

# Optional - multiple chat IDs (comma-separated)
export TELEGRAM_CHAT_IDS="chat_id_1,chat_id_2,chat_id_3"
```

### 4. Test the Setup

Run the Telegram test:

```bash
cd /path/to/sovereignforge
python -c "
import asyncio
import os
os.environ['TELEGRAM_BOT_TOKEN'] = 'your_token'
os.environ['TELEGRAM_CHAT_IDS'] = 'your_chat_id'
from src.telegram_alerts import send_system_alert
asyncio.run(send_system_alert('Test', 'Telegram alerts are working!', 'success'))
"
```

## 📱 Telegram Bot Features

### Interactive Commands
- `/start` - Welcome message and feature overview
- `/status` - Current system status and statistics
- `/help` - Command reference and tips

### Alert Types

#### 🚀 Arbitrage Opportunities
Rich-formatted alerts with:
- Trading pair and timestamp
- Probability and confidence scores
- Spread predictions and profit estimates
- Risk assessments (Low/Medium/High)
- Exchange information with prices and volumes
- Recommended actions

#### ⚠️ System Alerts
- Pipeline start/stop notifications
- Error warnings and system health
- Configuration changes
- Performance metrics

## 🔧 Advanced Configuration

### Multiple Recipients
Send alerts to multiple Telegram chats:

```bash
export TELEGRAM_CHAT_IDS="123456789,987654321,555666777"
```

### Custom Alert Filtering
Modify alert thresholds in `live_arbitrage_pipeline.py`:

```python
config = {
    'min_probability': 0.75,  # Minimum probability to alert
    'min_spread': 0.001,      # Minimum spread to alert
    'max_risk_score': 0.25,   # Maximum risk score to alert
}
```

### Bot Permissions
Your bot needs these permissions (automatically granted):
- ✅ Send messages
- ✅ Send media (for future features)
- ✅ Web previews disabled (for clean alerts)

## 🛠️ Troubleshooting

### Bot Not Responding
1. Check bot token is correct
2. Verify bot is not blocked
3. Ensure `/start` was sent to initialize chat

### Alerts Not Sending
1. Verify `TELEGRAM_BOT_TOKEN` is set
2. Check `TELEGRAM_CHAT_IDS` format
3. Look for error messages in logs

### Rate Limiting
Telegram has rate limits:
- 30 messages/second for bots
- SovereignForge includes automatic rate limiting

## 📊 Alert Statistics

Monitor your bot's performance:
- Total alerts sent
- Success/error rates
- Active chat count
- System uptime

Use `/status` command in Telegram to view real-time statistics.

## 🔒 Security Notes

- Keep your bot token secure (never commit to code)
- Use environment variables for configuration
- Bot tokens can be regenerated in BotFather if compromised
- Alerts contain sensitive trading information

## 🎯 Example Alert Format

```
🚀 ARBITRAGE OPPORTUNITY DETECTED

📊 Pair: BTC/USDC
⏰ Time: 14:30:25
🎯 Probability: 87.3%
📈 Spread: 0.0024
💰 Est. Profit: 2.34%
🟢 Risk: Low (0.12)

🏦 Exchanges:
  1. binance: $45000.50 (150.0)
  2. coinbase: $44950.20 (120.0)
  3. kraken: $45020.80 (180.0)

⚡ Confidence: 91.2%
```

## 🚀 Next Steps

Once configured, your SovereignForge system will automatically send real-time arbitrage alerts to your Telegram chats. The system includes intelligent filtering, risk assessment, and comprehensive market data analysis.

For production deployment, consider setting up dedicated alert channels for different alert types and user groups.