# Railway Environment Variables

Required environment variables for GoldAntelope ASIA deployment:

## Required Secrets

| Variable | Description |
|----------|-------------|
| `SESSION_SECRET` | Flask session secret key (generate a random string) |
| `TELEGRAM_BOT_TOKEN` | Telegram Bot API token from @BotFather |
| `TELEGRAM_API_ID` | Telegram API ID from my.telegram.org |
| `TELEGRAM_API_HASH` | Telegram API Hash from my.telegram.org |
| `BUNNY_API_KEY` | Bunny.net Storage API key |
| `BUNNY_STORAGE_ZONE` | Bunny.net storage zone name |
| `BUNNY_CDN_URL` | Bunny.net CDN URL (e.g., https://yourzone.b-cdn.net) |
| `GOOGLE_AI_API_KEY` | Google AI API key for translations |

## Optional Variables

| Variable | Description |
|----------|-------------|
| `TELEGRAM_CHAT_ID` | Default Telegram chat ID for notifications |
| `PHOTO_CHANNEL_ID` | Telegram channel ID for photo storage |

## Railway Setup

1. Create new project on Railway
2. Connect your GitHub repository
3. Add all environment variables in Settings > Variables
4. Deploy

## Notes

- PORT is automatically set by Railway
- Python 3.11 is specified in runtime.txt
- Gunicorn timeout set to 120 seconds for large data loads
