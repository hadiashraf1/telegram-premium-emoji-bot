"""Dependency-free Telegram Bot API long-polling application."""
import html
import json
import logging
import os
import secrets
import time
import urllib.error
import urllib.request
import urllib.parse
from collections import OrderedDict

from catalog import Catalog, ID, custom_ids, pack_name, utf16_length

VERSION = '0.5.1'
LOG = logging.getLogger('premium-emoji')
HELP = """راهنمای بانک ایموجی پرمیوم

• ایموجی پرمیوم را ارسال یا فوروارد کنید تا شناسه آن را دریافت کنید.
• برای جستجو، نام فارسی یا انگلیسی، ایموجی یا شناسه را بفرستید.
• /browse — مرور بانک
• /categories — دسته‌بندی‌ها
• /packs — فهرست پک‌ها
• /search قلب — جستجو
• /id شناسه — جزئیات و کپی کد
• /stats — آمار بانک

مدیر: /import دسته‌بندی | نام_پک
مثال: /import قلب | HeartsEmoji"""


class ApiError(Exception):
    def __init__(self, code, description='', retry_after=0):
        super().__init__(f'Telegram API error {code}')
        self.code, self.description, self.retry_after = code, description, retry_after


class Telegram:
    def __init__(self, token):
        self.base = 'https://api.telegram.org/bot' + token + '/'
        self.file_base = 'https://api.telegram.org/file/bot' + token + '/'

    def call(self, method, **payload):
        req = urllib.request.Request(self.base + method, json.dumps(payload).encode(), {'Content-Type':'application/json'})
        started = time.monotonic()
        deadline = 8 if method == 'getUpdates' else (20 if method == 'getStickerSet' else 12)
        try:
            with urllib.request.urlopen(req, timeout=deadline) as response:
                data = json.load(response)
        except urllib.error.HTTPError as err:
            try:
                data = json.load(err)
            except (ValueError, OSError):
                raise ApiError(err.code) from None
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            raise ApiError(0) from None
        finally:
            elapsed = time.monotonic() - started
            if elapsed >= (5 if method == 'getUpdates' else 2):
                LOG.warning('Slow Telegram method=%s elapsed=%.2fs', method, elapsed)
        if not data.get('ok'):
            raise ApiError(data.get('error_code', 0), data.get('description', ''), data.get('parameters', {}).get('retry_after', 0))
        return data['result']


    def thumbnail(self, file_id):
        """Download only a small Telegram-hosted image; never expose token URLs."""
        info = self.call('getFile', file_id=file_id)
        path = info.get('file_path', '')
        if not path or path.startswith('/') or '..' in path.split('/'):
            raise ApiError(400)
        try:
            with urllib.request.urlopen(self.file_base + urllib.parse.quote(path, safe='/'), timeout=8) as r:
                data = r.read(1024 * 1024 + 1)
        except (OSError, ValueError):
            raise ApiError(0) from None
        if len(data) > 1024 * 1024:
            raise ApiError(400)
        if data.startswith(b'\xff\xd8\xff'): return data, 'jpg', 'image/jpeg'
        if data.startswith(b'\x89PNG\r\n\x1a\n'): return data, 'png', 'image/png'
        if data[:4] == b'RIFF' and data[8:12] == b'WEBP': return data, 'webp', 'image/webp'
        raise ApiError(400)

    def send_thumbnail(self, chat, file_id, caption, keyboard):
        data, ext, mime = self.thumbnail(file_id)
        # Telegram accepts JPEG/PNG photos; WebP is also available as a document.
        method, field = ('sendDocument', 'document') if ext == 'webp' else ('sendPhoto', 'photo')
        boundary = secrets.token_hex(24)
        def part(name, value):
            return f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
        body = part('chat_id', chat) + part('caption', caption) + part('reply_markup', json.dumps(markup(keyboard)))
        body += f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"; filename="preview.{ext}"\r\nContent-Type: {mime}\r\n\r\n'.encode() + data + f'\r\n--{boundary}--\r\n'.encode()
        req = urllib.request.Request(self.base + method, body, {'Content-Type': 'multipart/form-data; boundary=' + boundary})
        try:
            with urllib.request.urlopen(req, timeout=12) as r:
                result = json.load(r)
        except urllib.error.HTTPError as err:
            raise ApiError(err.code) from None
        except (OSError, ValueError):
            raise ApiError(0) from None
        if not result.get('ok'): raise ApiError(result.get('error_code', 0))
        return result['result']


def markup(rows):
    return {'inline_keyboard': rows}


def copy_button(label, value):
    return {'text': label, 'copy_text': {'text': value}}


def html_code(eid, emoji):
    return f'<tg-emoji emoji-id="{eid}">{html.escape(emoji)}</tg-emoji>'


class Bot:
    def __init__(self, api, catalog, admins):
        self.api, self.catalog, self.admins = api, catalog, admins
        self.sessions = OrderedDict()

    def send(self, chat, text, keyboard=None, **extra):
        if keyboard:
            extra['reply_markup'] = markup(keyboard)
        extra.setdefault('link_preview_options', {'is_disabled': True})
        return self.api.call('sendMessage', chat_id=chat, text=text, **extra)

    def new_session(self, uid, query='', category='', pack=''):
        sid = secrets.token_hex(6)
        self.sessions[sid] = (uid, query, category, pack)
        while len(self.sessions) > 1000:
            self.sessions.popitem(last=False)
        return sid

    def page(self, chat, uid, sid, page=0, message_id=None):
        owner, query, category, pack = self.sessions[sid]
        if owner != uid:
            return
        rows, total, page = self.catalog.search(query, category, pack, page)
        label = query or category or pack or 'همه ایموجی‌ها'
        text = f'🔎 {label}\nتعداد: {total} | صفحه {page+1}/{max(1,(total+7)//8)}\n'
        plain = text
        buttons, entities = [], []
        if not rows:
            text += '\nنتیجه‌ای پیدا نشد. یک عبارت دیگر را امتحان کنید.'
            plain = text
        for i, row in enumerate(rows, 1):
            emoji = row['emoji'] or '⭐'
            prefix = f'\n{i}. '
            entities.append({'type': 'custom_emoji', 'offset': utf16_length(text + prefix),
                             'length': utf16_length(emoji), 'custom_emoji_id': row['id']})
            text += prefix + f"{emoji} | {row['id']}\n{row['title']}"
            plain += prefix + f"{row['id']}\n{row['title']}"
            buttons.append([copy_button(f'{i}. کپی شناسه', row['id']),
                            copy_button(f'{i}. کپی HTML', html_code(row['id'], emoji))])
        nav = []
        if page: nav.append({'text':'◀️ قبلی','callback_data':f'p:{sid}:{page-1}'})
        if (page+1)*8 < total: nav.append({'text':'بعدی ▶️','callback_data':f'p:{sid}:{page+1}'})
        if nav: buttons.append(nav)
        buttons.append([{'text':'🏠 منوی اصلی','callback_data':'home'}])
        payload = {'chat_id': chat, 'text': text, 'reply_markup': markup(buttons),
                   'link_preview_options': {'is_disabled': True}}
        if entities: payload['entities'] = entities
        method = 'editMessageText' if message_id else 'sendMessage'
        if message_id: payload['message_id'] = message_id
        try:
            result = self.api.call(method, **payload)
        except ApiError as err:
            if err.code != 400 or not entities: raise
            if 'message is not modified' in err.description.lower(): return
            LOG.warning('Inline custom emoji rejected: HTTP 400')
            result = None
        if entities and (result is None or (isinstance(result, dict) and
                [e.get('custom_emoji_id') for e in result.get('entities', []) if e.get('type') == 'custom_emoji'] !=
                [e['custom_emoji_id'] for e in entities])):
            LOG.warning('Inline custom emoji unavailable; verify bot owner Premium or Fragment username')
            payload.pop('entities', None)
            payload['text'] = plain + '\n\nنمایش ایموجی پرمیوم در پیام توسط تلگرام تأیید نشد. مالک ربات باید مجوز ارسال ایموجی پرمیوم داشته باشد.'
            if isinstance(result, dict) and result.get('message_id'):
                payload['message_id'] = result['message_id']
                method = 'editMessageText'
            self.api.call(method, **payload)
        elif entities:
            LOG.info('Inline custom emoji accepted: %d', len(entities))

    def preview(self, chat, eid):
        row = self.catalog.get(eid) or {}
        # Reuse the exact sticker file ID where Telegram permits it.
        file_id = row.get('file_id')
        sticker = None
        if not file_id:
            items = self.api.call('getCustomEmojiStickers', custom_emoji_ids=[eid])
            sticker = next((x for x in items if str(x.get('custom_emoji_id')) == eid), None)
            if not sticker:
                self.send(chat, 'ایموجی با این شناسه پیدا نشد.'); return
            file_id = sticker.get('file_id')
        emoji = row.get('emoji') or (sticker or {}).get('emoji') or '⭐'
        title = row.get('title') or (sticker or {}).get('set_name') or '—'
        pack = row.get('pack') or (sticker or {}).get('set_name')
        buttons = [[copy_button('📋 کپی شناسه', eid), copy_button('کپی HTML', html_code(eid, emoji))]]
        if pack and pack.replace('_', '').isalnum():
            buttons.append([{'text':'مشاهده پک اصلی', 'url':'https://t.me/addemoji/'+pack}])
        buttons.append([{'text':'🏠 منوی اصلی', 'callback_data':'home'}])
        if file_id:
            try:
                self.api.call('sendSticker', chat_id=chat, sticker=file_id, reply_markup=markup(buttons))
                return
            except ApiError as err:
                if err.code != 400: raise
        if sticker is None:
            items = self.api.call('getCustomEmojiStickers', custom_emoji_ids=[eid])
            sticker = next((x for x in items if str(x.get('custom_emoji_id')) == eid), {})
        thumb = (sticker.get('thumbnail') or {}).get('file_id')
        if thumb:
            try:
                self.api.send_thumbnail(chat, thumb, f'پیش‌نمایش ثابت | {title}\nشناسه: {eid}', buttons)
                return
            except ApiError as err:
                if err.code != 400: raise
        self.send(chat, f'نمایش فایل این ایموجی در ربات در دسترس نیست. پک اصلی را باز کنید.\n{title}\nشناسه: {eid}', buttons)

    def detail(self, chat, eid, row=None):
        row = row or self.catalog.get(eid)
        if not row:
            stickers = self.api.call('getCustomEmojiStickers', custom_emoji_ids=[eid])
            row = next((s for s in stickers if str(s.get('custom_emoji_id')) == eid), None)
        if not row:
            self.send(chat, 'ایموجی با این شناسه پیدا نشد.'); return
        emoji = row.get('emoji') or '⭐'
        title = row.get('title') or row.get('set_name') or '—'
        text = f'{emoji} ایموجی پرمیوم\nشناسه: {eid}\nپک: {title}'
        buttons = [[copy_button('📋 کپی شناسه', eid),copy_button('کپی HTML',html_code(eid,emoji))]]
        buttons.append([{'text':'🎨 پیش‌نمایش واقعی','callback_data':'v:'+eid}])
        pack = row.get('pack') or row.get('set_name')
        if pack and pack.replace('_','').isalnum():
            buttons.append([{'text':'مشاهده پک تلگرام','url':'https://t.me/addemoji/'+pack}])
        try:
            self.send(chat,text,buttons,entities=[{'type':'custom_emoji','offset':0,'length':utf16_length(emoji),'custom_emoji_id':eid}])
        except ApiError as err:
            if err.code != 400: raise
            self.send(chat,text,buttons)

    def start(self, chat):
        count, packs, categories = self.catalog.stats()
        self.send(chat, f'✨ بانک ایموجی پرمیوم تلگرام\n\n{count:,} ایموجی | {packs:,} پک | {categories} دسته\n\nایموجی پرمیوم را بفرستید تا شناسه آن را بگیرید یا از منوی زیر انتخاب کنید.', [
            [{'text':'🔎 جستجو','callback_data':'search'},{'text':'📚 مرور بانک','callback_data':'browse'}],
            [{'text':'🗂 دسته‌بندی‌ها','callback_data':'categories'},{'text':'🎨 پک‌ها','callback_data':'packs:0'}],
            [{'text':'📊 آمار بانک','callback_data':'stats'},{'text':'❔ راهنما','callback_data':'help'}]])

    def stats(self, chat):
        count, packs, categories = self.catalog.stats()
        self.send(chat, f'📊 آمار بانک\n\nایموجی‌ها: {count:,}\nپک‌ها: {packs:,}\nدسته‌ها: {categories}\n\nاین آمار فقط شامل موارد واردشده به بانک است.')

    def packs(self, chat, uid, page=0, message_id=None):
        rows, total, page = self.catalog.packs(page)
        buttons = [[{'text':f'{title[:42]} ({count})','callback_data':'p:'+self.new_session(uid,pack=pack)+':0'}] for pack,title,count in rows]
        nav = []
        if page: nav.append({'text':'◀️ قبلی','callback_data':f'packs:{page-1}'})
        if (page+1)*12 < total: nav.append({'text':'بعدی ▶️','callback_data':f'packs:{page+1}'})
        if nav: buttons.append(nav)
        buttons.append([{'text':'🏠 منوی اصلی','callback_data':'home'}])
        text = f'🎨 پک‌های ایموجی\nتعداد: {total} | صفحه {page+1}/{max(1,(total+11)//12)}'
        if message_id:
            self.api.call('editMessageText',chat_id=chat,message_id=message_id,text=text,reply_markup=markup(buttons))
        else: self.send(chat,text,buttons)

    def categories(self, chat, uid):
        rows = self.catalog.categories()
        if not rows:
            self.send(chat,'هنوز پکی به بانک اضافه نشده است.'); return
        # Use a paginated category list with IDs encoded in session keys.
        for i in range(0, len(rows), 40):
            buttons = [[{'text':f'{category} ({count})','callback_data':'p:'+self.new_session(uid, category=category)+':0'}] for category,count in rows[i:i+40]]
            self.send(chat,'🗂 دسته‌بندی‌ها',buttons)

    def import_pack(self, chat, uid, args):
        if uid not in self.admins:
            self.send(chat,'فقط مدیر می‌تواند پک وارد کند.'); return
        category, sep, value = args.partition('|')
        if not sep:
            value, category = category, 'عمومی'
        name = pack_name(value)
        pack = self.api.call('getStickerSet',name=name)
        if pack.get('sticker_type') != 'custom_emoji':
            self.send(chat,'این پک از نوع ایموجی سفارشی نیست.'); return
        count = self.catalog.import_pack(pack['name'],pack['title'],category,pack['stickers'])
        self.send(chat,f'✅ {count} ایموجی از پک {pack["title"]} ثبت یا به‌روزرسانی شد.')

    def handle_message(self, msg):
        if msg.get('chat',{}).get('type') != 'private': return
        chat, uid = msg['chat']['id'],msg.get('from',{}).get('id')
        ids = custom_ids(msg)
        if ids:
            # One compact result avoids flooding on messages with many entities.
            for i in range(0,len(ids),30):
                group = ids[i:i+30]
                self.send(chat,'شناسه‌های ایموجی:\n'+'\n'.join(group),[[{'text':f'جزئیات {eid}','callback_data':'e:'+eid},copy_button('کپی',eid)] for eid in group])
            return
        text = (msg.get('text') or '').strip()
        cmd, _, args = text.partition(' ')
        cmd = cmd.split('@',1)[0].lower()
        if cmd == '/start': self.start(chat)
        elif cmd == '/help': self.send(chat,HELP)
        elif cmd == '/stats': self.stats(chat)
        elif cmd == '/packs': self.packs(chat,uid)
        elif cmd == '/browse': self.page(chat,uid,self.new_session(uid))
        elif cmd == '/search':
            if not args.strip(): self.send(chat,'مثال: /search heart'); return
            self.page(chat,uid,self.new_session(uid,query=args))
        elif cmd == '/categories': self.categories(chat,uid)
        elif cmd == '/pack': self.page(chat,uid,self.new_session(uid,pack=pack_name(args)))
        elif cmd == '/id':
            if not ID.fullmatch(args.strip()): self.send(chat,'شناسه عددی معتبر ارسال کنید.'); return
            self.detail(chat,args.strip())
        elif cmd == '/import': self.import_pack(chat,uid,args)
        elif text.startswith(('https://t.me/addemoji/','https://telegram.me/addemoji/')):
            if uid in self.admins: self.import_pack(chat,uid,text)
            else: self.page(chat,uid,self.new_session(uid,pack=pack_name(text)))
        elif text: self.page(chat,uid,self.new_session(uid,query=text))
        else: self.send(chat,'یک ایموجی پرمیوم یا متن جستجو ارسال کنید.')

    def handle_callback(self, cb):
        self.api.call('answerCallbackQuery',callback_query_id=cb['id'])
        msg = cb.get('message',{}); chat = msg.get('chat',{}).get('id'); uid = cb['from']['id']
        if not chat or msg.get('chat',{}).get('type') != 'private': return
        data = cb.get('data','')
        if data == 'home': self.start(chat)
        elif data == 'search': self.send(chat,'🔎 نام فارسی، انگلیسی، ایموجی یا شناسه را همینجا بفرستید. مثال: قلب یا fire')
        elif data == 'help': self.send(chat,HELP)
        elif data == 'stats': self.stats(chat)
        elif data.startswith('packs:') and data[6:].isdigit(): self.packs(chat,uid,int(data[6:]),msg.get('message_id') if data!='packs:0' else None)
        elif data == 'browse': self.page(chat,uid,self.new_session(uid))
        elif data == 'categories': self.categories(chat,uid)
        elif data.startswith('e:') and ID.fullmatch(data[2:]): self.detail(chat,data[2:])
        elif data.startswith('v:') and ID.fullmatch(data[2:]): self.preview(chat,data[2:])
        elif data.startswith('p:'):
            parts = data.split(':')
            if len(parts)!=3 or not parts[2].isdigit(): return
            sid = parts[1]
            if sid not in self.sessions or self.sessions[sid][0]!=uid:
                self.send(chat,'این صفحه منقضی شده؛ دوباره /browse را بزنید.'); return
            self.page(chat,uid,sid,int(parts[2]),msg.get('message_id'))

    def handle(self, update):
        msg = update.get('message') or update.get('callback_query',{}).get('message',{})
        try:
            if 'message' in update: self.handle_message(update['message'])
            elif 'callback_query' in update: self.handle_callback(update['callback_query'])
        except (ValueError, ApiError) as err:
            if isinstance(err, ApiError) and err.code in (0,429,500,502,503,504): raise
            chat = msg.get('chat',{}).get('id')
            if chat:
                self.send(chat,'درخواست نامعتبر بود یا تلگرام پاسخ نداد. لینک یا شناسه را بررسی کنید.')

    def run(self):
        while True:
            try:
                self.api.call('deleteWebhook',drop_pending_updates=False)
                break
            except ApiError as err:
                if err.code in (401,404,409): raise SystemExit(f'Telegram API error {err.code}; check token or competing poller.') from None
                LOG.warning('Startup Telegram connection failed: %s',err)
                time.sleep(min(max(err.retry_after,3),60))
        offset = 0
        while True:
            try:
                updates = self.api.call('getUpdates',offset=offset,timeout=2,allowed_updates=['message','callback_query'])
                if not updates:
                    time.sleep(0.7)
                for update in updates:
                    started = time.monotonic()
                    msg = update.get('message', {})
                    age = max(0, time.time() - msg['date']) if isinstance(msg.get('date'), (int, float)) else -1
                    LOG.info('Update received age=%.1fs', age)
                    try: self.handle(update)
                    except ApiError as err:
                        if err.retry_after: time.sleep(min(err.retry_after,60))
                        LOG.warning('Update failed: %s',err)
                    except Exception: LOG.error('Update processing failed')
                    LOG.info('Update handled elapsed=%.2fs', time.monotonic()-started)
                    offset = update['update_id']+1
            except ApiError as err:
                if err.code in (401,404,409): raise SystemExit(f'Telegram API error {err.code}; check token or competing poller.') from None
                LOG.warning('Polling failed: %s',err)
                time.sleep(min(max(err.retry_after,3),60))


def main():
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    token = os.environ.get('BOT_TOKEN','').strip()
    if not token or ':' not in token or token.startswith('123456:'):
        raise SystemExit('Set BOT_TOKEN using BotFather.')
    try: admins = {int(x.strip()) for x in os.environ.get('ADMIN_IDS','').split(',') if x.strip()}
    except ValueError: raise SystemExit('ADMIN_IDS must be comma-separated numeric Telegram user IDs.') from None
    if not admins: raise SystemExit('Set ADMIN_IDS to at least one Telegram user ID.')
    bot = Bot(Telegram(token),Catalog(os.environ.get('DB_PATH','data/emoji.sqlite3')),admins)
    LOG.info('Premium Emoji Bot v%s starting',VERSION)
    bot.run()

if __name__ == '__main__': main()
