# MTProto Harvester v2 — جستجوی گسترده پک‌های ایموجی تلگرام

این ابزار مستقل با حساب مجاز تلگرام از MTProto برای کشف پک‌های عمومی Custom Emoji استفاده می‌کند و سپس با Bot API متادیتای پک‌ها را به بانک موجود وارد می‌کند. ربات اصلی را اجرا یا ری‌استارت نمی‌کند.

## متدهای رسمی
- `messages.searchEmojiStickerSets`: جستجوی پک‌های Custom Emoji بر اساس نام.
- `messages.getEmojiStickers`: دریافت پک‌های ایموجی نصب‌شده حساب.
- `messages.getFeaturedEmojiStickers`: دریافت پک‌های ویژه در صورت پشتیبانی API.

جستجوی جهانی کامل و نامحدود نیست؛ نتایج وابسته به عبارت و رتبه‌بندی تلگرام هستند.

## امنیت
- فقط از حساب خودت یا حسابی که مجاز به استفاده از آن هستی استفاده کن؛ ترجیحاً حساب جداگانه.
- کد ورود، رمز دومرحله‌ای و فایل `.session` را برای هیچ‌کس ارسال نکن.
- نشست در `/var/lib/emoji-mtproto` روی سرور ذخیره می‌شود.
- `.env`، session، دیتابیس و بکاپ نباید وارد Git شوند.
- ابزار فقط پک‌های عمومی را جستجو می‌کند؛ به کانال خصوصی نمی‌پیوندد و پیامی ارسال نمی‌کند.
- FloodWait رعایت می‌شود و نرخ درخواست محدود است.

## نصب
فایل ZIP را در `/root/` آپلود کن، سپس:

```bash
cd /opt/telegram-premium-emoji-bot
python3 -m zipfile -e /root/mtproto-harvester-v2.zip .
```

در فایل محلی `.env` مقادیر API را از `my.telegram.org` اضافه کن:

```env
API_ID=YOUR_NUMERIC_API_ID
API_HASH=YOUR_API_HASH
```

این مقادیر را در GitHub منتشر نکن.

```bash
install -d -m 700 /var/lib/emoji-mtproto /var/lib/emoji-mtproto-state

docker compose -f compose.yaml -f mtproto-harvester-v2/compose.mtproto.yaml build mtproto-harvester mtproto-login
```

## ورود یک‌باره
```bash
docker compose -f compose.yaml -f mtproto-harvester-v2/compose.mtproto.yaml run --rm -it mtproto-login
```

شماره تلفن، کد ورود و رمز دومرحله‌ای را فقط در ترمینال سرور وارد کن.

## اجرای آزمایشی — فقط کشف، بدون تغییر بانک
```bash
docker compose -f compose.yaml -f mtproto-harvester-v2/compose.mtproto.yaml run --rm mtproto-harvester python /app/harvest.py --discover-only --max-queries 30
```

## اجرای کامل
```bash
docker compose -f compose.yaml -f mtproto-harvester-v2/compose.mtproto.yaml run --rm mtproto-harvester python /app/harvest.py --max-import 1000
```

قبل از واردسازی، بکاپ SQLite گرفته و `quick_check` اجرا می‌شود. شناسه‌ها با `INSERT OR IGNORE` ذخیره می‌شوند تا رکوردهای قبلی بازنویسی نشوند.

## گزارش
```bash
docker compose -f compose.yaml -f mtproto-harvester-v2/compose.mtproto.yaml run --rm mtproto-harvester python /app/harvest.py --stats
```

صف و checkpoint عبارت‌ها در `/state/mtproto-harvester.sqlite3` نگهداری می‌شوند؛ اجرای دوباره عبارت‌های موفق را تکرار نمی‌کند.

## تست آفلاین
```bash
python3 -m unittest discover -s mtproto-harvester-v2/tests -v
```

بانک اصلی: `/data/emoji.sqlite3`؛ نشست: `/sessions/emoji-reader.session`؛ صف: `/state/mtproto-harvester.sqlite3`.

**محدودیت:** MTProto نیز export کامل همه پک‌های تلگرام را ارائه نمی‌کند؛ نتایج جستجو وابسته به عبارت و رتبه‌بندی سرور است.
