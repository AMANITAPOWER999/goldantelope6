#!/usr/bin/env python3
import os
import asyncio
from telethon import TelegramClient

API_ID = os.environ.get('TELETHON_API_ID')
API_HASH = os.environ.get('TELETHON_API_HASH')
PHONE = os.environ.get('TELETHON_PHONE')

async def setup_session():
    if not API_ID or not API_HASH:
        print("Error: TELETHON_API_ID and TELETHON_API_HASH must be set")
        return False
    
    print(f"Setting up Telegram session...")
    print(f"API ID: {API_ID}")
    print(f"Phone: {PHONE}")
    
    client = TelegramClient('telegram_session', int(API_ID), API_HASH)
    
    try:
        await client.start(phone=PHONE)
        print("Session created successfully!")
        print("You can now run the parser.")
        me = await client.get_me()
        print(f"Logged in as: {me.first_name} (@{me.username})")
        return True
    except Exception as e:
        print(f"Error: {e}")
        return False
    finally:
        await client.disconnect()

if __name__ == "__main__":
    asyncio.run(setup_session())
