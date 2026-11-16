"""Import a curated list of publicly linked packs, with per-pack validation and retry."""
import argparse
import os
import time
from pathlib import Path
from app import Telegram, ApiError
from catalog import Catalog, pack_name


def read_manifest(path):
    seen = set()
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        if not line.strip() or line.lstrip().startswith('#'): continue
        category, name = line.split('|', 1)
        name = pack_name(name)
        if name.lower() not in seen:
            seen.add(name.lower()); yield category.strip(), name


def seed(api, catalog, entries, sleep=time.sleep):
    ok = failed = 0
    for category, name in entries:
        for attempt in range(3):
            try:
                pack = api.call('getStickerSet', name=name)
                if pack.get('sticker_type') != 'custom_emoji':
                    print(f'SKIP {name}: not custom emoji', flush=True); failed += 1; break
                n = catalog.import_pack(pack['name'],pack['title'],category,pack['stickers'])
                print(f'OK {name}: {n} emoji', flush=True); ok += 1; break
            except ApiError as err:
                if err.code in (401,404): raise
                if attempt < 2 and err.code in (0,429,500,502,503,504):
                    sleep(max(2,err.retry_after)); continue
                print(f'FAILED {name}: API {err.code}', flush=True); failed += 1; break
        sleep(0.35)
    print(f'SEED RESULT: {ok} packs succeeded; {failed} failed; database totals: {catalog.stats()}', flush=True)
    return ok, failed


def main():
    p = argparse.ArgumentParser(); p.add_argument('--manifest',default=str(Path(__file__).with_name('seed-packs.txt'))); args=p.parse_args()
    token=os.environ.get('BOT_TOKEN','').strip()
    if not token or ':' not in token or token.startswith('123456:'): raise SystemExit('Set BOT_TOKEN')
    entries=list(read_manifest(args.manifest))
    ok, failed=seed(Telegram(token),Catalog(os.environ.get('DB_PATH','data/emoji.sqlite3')),entries)
    if failed: raise SystemExit(2)

if __name__=='__main__': main()
