"""Persistent custom emoji metadata; no Telegram assets or credentials stored."""
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

ID = re.compile(r'^[1-9][0-9]{0,19}$')
PACK = re.compile(r'^[A-Za-z0-9_]{1,64}$')


def pack_name(value):
    value = value.strip()
    if value.startswith(('https://', 'http://')):
        url = urlsplit(value)
        parts = url.path.strip('/').split('/')
        if url.hostname not in ('t.me', 'telegram.me') or len(parts) != 2 or parts[0] != 'addemoji':
            raise ValueError('Use a t.me/addemoji/NAME link or pack name.')
        value = parts[1]
    if not PACK.fullmatch(value):
        raise ValueError('Invalid pack name.')
    return value


def custom_ids(message):
    result = []
    for entity in message.get('entities', []) + message.get('caption_entities', []):
        value = str(entity.get('custom_emoji_id', ''))
        if entity.get('type') == 'custom_emoji' and ID.fullmatch(value) and value not in result:
            result.append(value)
    return result


def utf16_length(text):
    return len(text.encode('utf-16-le')) // 2


class Catalog:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.executescript('''PRAGMA journal_mode=WAL;
              CREATE TABLE IF NOT EXISTS emoji (
                id TEXT PRIMARY KEY, emoji TEXT NOT NULL, pack TEXT NOT NULL,
                title TEXT NOT NULL, category TEXT NOT NULL, file_id TEXT NOT NULL DEFAULT '',
                animated INTEGER NOT NULL DEFAULT 0, video INTEGER NOT NULL DEFAULT 0);
              CREATE INDEX IF NOT EXISTS emoji_category ON emoji(category);
              CREATE INDEX IF NOT EXISTS emoji_pack ON emoji(pack);''')

    @contextmanager
    def db(self):
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def import_pack(self, pack, title, category, stickers):
        pack = pack_name(pack).lower()
        category = category.strip()[:80] or 'عمومی'
        rows = []
        for sticker in stickers:
            eid = str(sticker.get('custom_emoji_id', ''))
            if ID.fullmatch(eid):
                rows.append((eid, sticker.get('emoji') or '⭐', pack, title[:200], category,
                             sticker.get('file_id', ''), int(bool(sticker.get('is_animated'))), int(bool(sticker.get('is_video')))))
        with self.db() as db:
            db.executemany('''INSERT INTO emoji VALUES (?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET emoji=excluded.emoji, pack=excluded.pack,
                title=excluded.title, category=excluded.category, file_id=excluded.file_id,
                animated=excluded.animated, video=excluded.video''', rows)
        return len({r[0] for r in rows})

    def search(self, query='', category='', pack='', page=0, size=8):
        query, category, pack = query.strip()[:200], category.strip()[:80], pack.strip().lower()
        page, size = max(0, int(page)), max(1, min(20, int(size)))
        where, args = [], []
        if query:
            where.append('(instr(lower(id),lower(?)) OR instr(lower(emoji),lower(?)) OR instr(lower(title),lower(?)) OR instr(lower(pack),lower(?)) OR instr(lower(category),lower(?)))')
            args.extend([query]*5)
        if category:
            where.append('category=?'); args.append(category)
        if pack:
            where.append('pack=?'); args.append(pack)
        clause = ' WHERE ' + ' AND '.join(where) if where else ''
        with self.db() as db:
            total = db.execute('SELECT count(*) FROM emoji'+clause, args).fetchone()[0]
            page = min(page, max(0, (total-1)//size))
            rows = db.execute('SELECT * FROM emoji'+clause+' ORDER BY pack,id LIMIT ? OFFSET ?', args+[size,page*size]).fetchall()
        return [dict(r) for r in rows], total, page

    def categories(self):
        with self.db() as db:
            return [(r[0], r[1]) for r in db.execute('SELECT category,count(*) FROM emoji GROUP BY category ORDER BY category')]

    def get(self, eid):
        with self.db() as db:
            row = db.execute('SELECT * FROM emoji WHERE id=?', (eid,)).fetchone()
        return dict(row) if row else None
