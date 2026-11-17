#!/usr/bin/env python3
"""Independent MTProto discovery + Bot API importer for public Telegram custom emoji sets."""
import argparse, fcntl, json, os, re, sqlite3, time, urllib.error, urllib.request
from pathlib import Path

PACK_RE=re.compile(r"^[A-Za-z0-9_]{1,64}$")
ID_RE=re.compile(r"^[1-9][0-9]{0,19}$")
DEFAULT_DB="/data/emoji.sqlite3"
DEFAULT_STATE="/state/mtproto-harvester.sqlite3"
DEFAULT_SESSION="/sessions/emoji-reader"
DEFAULT_QUERY_FILE=str(Path(__file__).with_name("queries.txt"))
SCHEMA="""
CREATE TABLE IF NOT EXISTS candidates(
 short_name TEXT PRIMARY KEY,title TEXT NOT NULL DEFAULT '',source TEXT NOT NULL DEFAULT '',
 status TEXT NOT NULL DEFAULT 'pending',attempts INTEGER NOT NULL DEFAULT 0,
 imported_count INTEGER NOT NULL DEFAULT 0,last_error TEXT NOT NULL DEFAULT '',
 discovered_at INTEGER NOT NULL,updated_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS search_progress(
 kind TEXT NOT NULL,query TEXT NOT NULL,status TEXT NOT NULL,
 updated_at INTEGER NOT NULL,error TEXT NOT NULL DEFAULT '',PRIMARY KEY(kind,query));
"""

def state_connect(path):
    Path(path).parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    db=sqlite3.connect(path,timeout=60)
    db.execute("PRAGMA busy_timeout=60000")
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript(SCHEMA)
    return db

def queue_candidate(db,name,title="",source=""):
    name=(name or "").strip()
    if not PACK_RE.fullmatch(name): return False
    now=int(time.time())
    cur=db.execute("""INSERT OR IGNORE INTO candidates
      (short_name,title,source,status,discovered_at,updated_at)
      VALUES(?,?,?,'pending',?,?)""",(name,str(title or "")[:200],source[:200],now,now))
    return cur.rowcount==1

def mark_candidate(db,name,status,error="",added=None):
    now=int(time.time())
    if added is None:
        db.execute("UPDATE candidates SET status=?,last_error=?,updated_at=? WHERE short_name=?",(status,str(error)[:500],now,name))
    else:
        db.execute("""UPDATE candidates SET status=?,last_error=?,imported_count=?,
          attempts=attempts+1,updated_at=? WHERE short_name=?""",(status,str(error)[:500],int(added),now,name))

def insert_pack_data(db_path,pack):
    """Insert only new IDs; existing bank records are never overwritten."""
    name=str(pack.get("name","")).strip().lower()
    title=str(pack.get("title",name))[:200]
    rows=[]
    for st in pack.get("stickers",[]) or []:
        eid=str(st.get("custom_emoji_id",""))
        if ID_RE.fullmatch(eid):
            rows.append((eid,st.get("emoji") or "⭐",name,title,"عمومی",st.get("file_id","") or "",int(bool(st.get("is_animated"))),int(bool(st.get("is_video")))))
    if not rows: return 0
    db=sqlite3.connect(db_path,timeout=60)
    try:
        db.execute("PRAGMA busy_timeout=60000"); db.execute("BEGIN IMMEDIATE")
        before=db.total_changes
        db.executemany("""INSERT OR IGNORE INTO emoji
          (id,emoji,pack,title,category,file_id,animated,video) VALUES(?,?,?,?,?,?,?,?)""",rows)
        added=db.total_changes-before; db.commit(); return added
    except Exception: db.rollback(); raise
    finally: db.close()

class BotAPI:
    def __init__(self,token):
        if not token or ":" not in token: raise RuntimeError("BOT_TOKEN is missing or invalid")
        self.base="https://api.telegram.org/bot"+token+"/"
    def call(self,method,**payload):
        req=urllib.request.Request(self.base+method,data=json.dumps(payload).encode(),headers={"Content-Type":"application/json"},method="POST")
        try:
            with urllib.request.urlopen(req,timeout=25) as r: data=json.load(r)
        except urllib.error.HTTPError as e:
            try: data=json.load(e)
            except Exception: raise RuntimeError("Bot API HTTP "+str(e.code)) from None
        except (urllib.error.URLError,TimeoutError,OSError,ValueError) as e:
            raise RuntimeError("Bot API transport: "+type(e).__name__) from None
        if not data.get("ok"):
            err=RuntimeError("Bot API "+str(data.get("error_code",0))+": "+str(data.get("description","unknown")))
            err.code=int(data.get("error_code",0))
            err.retry_after=int((data.get("parameters") or {}).get("retry_after",0) or 0)
            raise err
        return data["result"]

def backup_database(path):
    srcp=Path(path)
    if not srcp.exists(): raise RuntimeError("Bank DB not found: "+str(srcp))
    dstp=srcp.with_name("backup-before-mtproto-"+time.strftime("%Y%m%d-%H%M%S",time.gmtime())+".sqlite3")
    with sqlite3.connect(srcp,timeout=60) as src, sqlite3.connect(dstp) as dst:
        src.backup(dst)
        check=dst.execute("PRAGMA quick_check").fetchone()[0]
        count=dst.execute("SELECT COUNT(*) FROM emoji").fetchone()[0]
    if check!="ok": raise RuntimeError("Backup validation failed: "+str(check))
    os.chmod(dstp,0o600)
    print("BACKUP:",dstp,"EMOJIS:",count,"CHECK:",check,flush=True)

def known_packs(path):
    with sqlite3.connect(path,timeout=60) as db:
        return {str(r[0]).lower() for r in db.execute("SELECT DISTINCT pack FROM emoji WHERE pack IS NOT NULL")}

def import_pending(state_path,db_path,token,limit=1000,delay=1.0,backup=True):
    api=BotAPI(token)
    with sqlite3.connect(state_path,timeout=60) as state:
        state.row_factory=sqlite3.Row
        known=known_packs(db_path)
        if backup: backup_database(db_path)
        rows=state.execute("SELECT short_name FROM candidates WHERE status IN ('pending','retry') ORDER BY discovered_at LIMIT ?",(limit,)).fetchall()
        added_total=0
        for i,row in enumerate(rows,1):
            name=row["short_name"]
            if name.lower() in known:
                mark_candidate(state,name,"known"); print(f"KNOWN {i}/{len(rows)} {name}",flush=True)
            else:
                try:
                    pack=None
                    for attempt in range(3):
                        try: pack=api.call("getStickerSet",name=name); break
                        except Exception as exc:
                            code=getattr(exc,"code",0)
                            if code in (401,403): raise SystemExit("Bot token/permission error; stopped safely.") from None
                            wait=max(getattr(exc,"retry_after",0),5 if code==429 else min(60,3*(2**attempt)))
                            if code not in (0,429,500,502,503,504) or attempt==2: raise
                            print(f"RETRY {name} code={code} wait={wait}s",flush=True); time.sleep(wait)
                    if not pack or pack.get("sticker_type")!="custom_emoji":
                        mark_candidate(state,name,"not_custom","Not a custom emoji set")
                        print(f"NOT_CUSTOM {i}/{len(rows)} {name}",flush=True)
                    else:
                        added=insert_pack_data(db_path,pack); known.add(name.lower())
                        mark_candidate(state,name,"ok" if added else "empty",added=added)
                        added_total+=added
                        print(f"MT_OK {i}/{len(rows)} {name} +{added} new_total={added_total}",flush=True)
                except Exception as exc:
                    code=getattr(exc,"code",0)
                    if code==400:
                        mark_candidate(state,name,"invalid",str(exc)); print(f"INVALID {i}/{len(rows)} {name}",flush=True)
                    else:
                        mark_candidate(state,name,"retry",str(exc)); print(f"FAILED_RETRY {i}/{len(rows)} {name}: {type(exc).__name__}",flush=True)
            state.commit()  # durable checkpoint after each pack
            time.sleep(max(.2,delay))
        return added_total,len(rows)

def meta_from_cover(item): return getattr(item,"set",None) or item

def add_meta(db,item,source):
    meta=meta_from_cover(item)
    if getattr(meta,"emojis",True) is False: return False
    return queue_candidate(db,getattr(meta,"short_name",""),getattr(meta,"title",""),source)

def load_queries(path):
    out=[]
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        q=line.strip()
        if q and not q.startswith("#") and q not in out: out.append(q)
    return out

def query_done(db,kind,q):
    row=db.execute("SELECT status FROM search_progress WHERE kind=? AND query=?",(kind,q)).fetchone()
    return bool(row and row[0]=="done")

def mark_query(db,kind,q,status,error=""):
    db.execute("""INSERT INTO search_progress VALUES(?,?,?,?,?) ON CONFLICT(kind,query)
      DO UPDATE SET status=excluded.status,updated_at=excluded.updated_at,error=excluded.error""",
      (kind,q,status,int(time.time()),str(error)[:500]))

def discover(client,state_path,query_file,max_queries=0,delay=.8,max_wait=180):
    from telethon import functions
    from telethon.errors import FloodWaitError
    queries=load_queries(query_file)
    if max_queries: queries=queries[:max_queries]
    found=0
    with sqlite3.connect(state_path,timeout=60) as db:
        db.execute("PRAGMA busy_timeout=60000")
        for kind,request in [
            ("installed",lambda:client(functions.messages.GetEmojiStickersRequest(hash=0))),
            ("featured",lambda:client(functions.messages.GetFeaturedEmojiStickersRequest(hash=0)))
        ]:
            try:
                result=request(); items=getattr(result,"sets",[]) or []; n=0
                for item in items: n+=int(add_meta(db,item,"account-"+kind))
                db.commit(); found+=n
                print("MT_"+kind.upper(),"sets=",len(items),"new=",n,flush=True)
            except FloodWaitError as e:
                print("MT_FLOOD_WAIT",kind,"seconds=",e.seconds,flush=True)
                if e.seconds>max_wait: return found
                time.sleep(e.seconds+2)
            except Exception as e: print("MT_"+kind.upper()+"_SKIP",type(e).__name__,flush=True)
        for i,q in enumerate(queries,1):
            if query_done(db,"emoji-set-search",q): continue
            try:
                result=client(functions.messages.SearchEmojiStickerSetsRequest(q=q,hash=0))
                items=getattr(result,"sets",[]) or []; n=0
                for item in items: n+=int(add_meta(db,item,"searchEmojiStickerSets:"+q))
                db.commit(); mark_query(db,"emoji-set-search",q,"done"); db.commit()
                found+=n
                print(f"MT_QUERY {i}/{len(queries)} {q!r} results={len(items)} new={n}",flush=True)
            except FloodWaitError as e:
                mark_query(db,"emoji-set-search",q,"paused","FloodWait "+str(e.seconds)); db.commit()
                print("MT_FLOOD_WAIT query=",repr(q),"seconds=",e.seconds,flush=True)
                if e.seconds>max_wait: break
                time.sleep(e.seconds+2)
            except Exception as e:
                mark_query(db,"emoji-set-search",q,"error",type(e).__name__+": "+str(e)); db.commit()
                print("MT_QUERY_ERROR",repr(q),type(e).__name__,flush=True)
            time.sleep(max(.2,delay))
    return found

def report(state_path,db_path):
    with sqlite3.connect(state_path) as db:
        counts=dict(db.execute("SELECT status,COUNT(*) FROM candidates GROUP BY status"))
        done=db.execute("SELECT COUNT(*) FROM search_progress WHERE status='done'").fetchone()[0]
        totalq=db.execute("SELECT COUNT(*) FROM search_progress").fetchone()[0]
        candidates=db.execute("SELECT COUNT(*) FROM candidates").fetchone()[0]
    with sqlite3.connect(db_path) as db:
        bank=db.execute("SELECT COUNT(*),COUNT(DISTINCT pack),COUNT(DISTINCT category) FROM emoji").fetchone()
    print("QUEUE:",counts); print("CANDIDATES:",candidates,"SEARCH_PROGRESS:",f"{done}/{totalq}"); print("BANK:",bank)

def main():
    p=argparse.ArgumentParser(description="Discover public Telegram custom emoji sets via official MTProto search.")
    p.add_argument("--discover-only",action="store_true"); p.add_argument("--import-only",action="store_true")
    p.add_argument("--max-queries",type=int,default=0); p.add_argument("--max-import",type=int,default=1000)
    p.add_argument("--query-delay",type=float,default=.8); p.add_argument("--import-delay",type=float,default=1.0)
    p.add_argument("--max-flood-wait",type=int,default=180); p.add_argument("--skip-backup",action="store_true"); p.add_argument("--stats",action="store_true")
    a=p.parse_args(); dbp=os.environ.get("DB_PATH",DEFAULT_DB); sp=os.environ.get("STATE_PATH",DEFAULT_STATE)
    qp=os.environ.get("QUERY_FILE",DEFAULT_QUERY_FILE); session=os.environ.get("SESSION_PATH",DEFAULT_SESSION)
    Path(sp).parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    if a.stats: report(sp,dbp); return
    with open(sp+".lock","a") as lock:
        os.chmod(sp+".lock",0o600)
        try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: raise SystemExit("Another MTProto harvester is already running.")
        if not a.import_only:
            api_id=os.environ.get("API_ID","").strip(); api_hash=os.environ.get("API_HASH","").strip()
            if not api_id.isdigit() or not api_hash: raise SystemExit("Set API_ID and API_HASH in local .env first.")
            try: from telethon.sync import TelegramClient
            except ImportError: raise SystemExit("Telethon missing; rebuild the image.")
            client=TelegramClient(session,int(api_id),api_hash,flood_sleep_threshold=60)
            try:
                client.connect()
                if not client.is_user_authorized(): raise SystemExit("MTProto session not authorized; run mtproto-login first.")
                me=client.get_me(); print("MTProto authorized user_id=",getattr(me,"id","unknown"),flush=True)
                n=discover(client,sp,qp,a.max_queries,a.query_delay,a.max_flood_wait)
                print("MT_DISCOVERY_DONE new_candidates=",n,flush=True)
            finally: client.disconnect()
        if not a.discover_only:
            added,attempted=import_pending(sp,dbp,os.environ.get("BOT_TOKEN",""),a.max_import,a.import_delay,not a.skip_backup)
            print("MT_IMPORT_DONE attempted=",attempted,"new_emoji=",added,flush=True)
        report(sp,dbp)

if __name__=="__main__": main()
