# Telegram Premium Emoji Bot

A Persian-language, self-hosted Telegram custom emoji catalog and ID extractor. Rebuilt as **v0.3.0** from the previous project requirements. The original archive was not available. Uses Python 3.12 (standard library only), SQLite and the official Telegram Bot API; no MTProto user session or third-party catalog is required.

## Features
- Extract unique `custom_emoji_id` values from messages and captions.
- Import public custom emoji packs using `getStickerSet`, with administrator-only writes.
- Browse, search, categorize, and paginate a persistent local catalog.
- Copy an ID or its Telegram HTML representation with one tap on supported clients.
- Resolve an individual ID with `getCustomEmojiStickers`; render a custom-emoji preview when the bot is permitted, otherwise use its ordinary emoji fallback.
- Docker Compose deployment and offline automated tests.

## Setup (Ubuntu / Docker)

```sh
git clone https://github.com/hadiashraf1/telegram-premium-emoji-bot.git
cd telegram-premium-emoji-bot
cp .env.example .env
nano .env
docker compose up -d --build
docker compose logs -f bot
```

Create a bot using Telegram @BotFather and put its token in `BOT_TOKEN`. Set `ADMIN_IDS` to your numeric Telegram user ID (comma-separated for multiple admins). Do not commit `.env`, database files, session files, or tokens. The named volume persists the SQLite database across container restarts; keep separate backups of that volume. Do not run two polling instances with the same token. Startup removes any existing webhook without dropping pending updates.

For local development (Python 3.11+): set environment variables `BOT_TOKEN`, `ADMIN_IDS` and optionally `DB_PATH` (default `data/emoji.sqlite3`), then run `python app.py`. The app does not load `.env` automatically outside Compose.

## Commands

| Command | Action |
|---|---|
| `/start` | Open main menu |
| `/browse` | Browse all indexed emoji |
| `/search heart` | Search title, category, pack, base emoji or ID |
| `/categories` | Browse categories |
| `/pack PackName` | Browse a previously indexed pack |
| `/id 123456789` | Resolve a custom emoji ID |
| `/import عمومی \| https://t.me/addemoji/PackName` | Admin: import a pack under a category |

Send or forward a message with custom emoji to extract its IDs. An admin can send a pack link directly to import it under the default category. The catalog starts empty: import real pack names to populate it. Re-importing updates metadata without duplicating IDs. Search uses literal substrings, not a translation dictionary.

## Coverage and Telegram limitations

The Bot API does not expose an exhaustive list of all Telegram custom emoji packs. This version indexes packs you import; it does not scrape Telegram, and no 90–95% coverage claim is made. Sending actual custom emoji entities is subject to Telegram's bot/account permissions. ID extraction and copying work independently of preview permission. The source contains no copyrighted emoji assets, no user credentials, and no prefilled private database. The bot only handles private chats, and non-admin messages do not add data to the catalog. See https://core.telegram.org/bots/api for API details.

## Tests

```sh
python -m unittest discover -s tests -v
```

Tests use temporary databases and fake Telegram responses; no bot token or network is needed. A real Telegram smoke test requires your own bot token and admin ID.
