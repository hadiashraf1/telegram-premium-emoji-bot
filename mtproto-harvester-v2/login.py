#!/usr/bin/env python3
"""Create a local Telethon session. Never upload the resulting session file."""
import os
from pathlib import Path

def main():
    try:
        from telethon.sync import TelegramClient
    except ImportError:
        raise SystemExit("Telethon is missing; rebuild the mtproto-harvester image.")
    api_id=os.environ.get("API_ID","").strip()
    api_hash=os.environ.get("API_HASH","").strip()
    session=os.environ.get("SESSION_PATH","/sessions/emoji-reader")
    if not api_id.isdigit() or not api_hash:
        raise SystemExit("Set API_ID and API_HASH in the local .env file.")
    Path(session).parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    phone=input("Telegram phone number (international format): ").strip()
    if not phone: raise SystemExit("Phone number is required.")
    client=TelegramClient(session,int(api_id),api_hash)
    try:
        client.start(phone=phone)
        if not client.is_user_authorized(): raise SystemExit("Authorization was not completed.")
        me=client.get_me()
        print("AUTHORIZED USER ID:",getattr(me,"id","unknown"))
        print("SESSION SAVED LOCALLY:",session+".session")
        print("Never send or commit this session file.")
    finally: client.disconnect()

if __name__=="__main__": main()
