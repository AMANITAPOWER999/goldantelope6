#!/usr/bin/env python3
"""
Standalone script to fetch ALL historical messages from the Thailand supergroup
using Telethon user session (MTProto API).

Usage:
  python3 fetch_thailand_history.py

Requires:
  TELETHON_API_ID, TELETHON_API_HASH environment variables
  A valid 'telegram_user_session.session' file (run once with phone auth if missing)
"""
import os
import asyncio
import logging
import json

logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
logger = logging.getLogger(__name__)

TELETHON_API_ID = int(os.environ.get('TELETHON_API_ID', 0))
TELETHON_API_HASH = os.environ.get('TELETHON_API_HASH', '')
SESSION_FILE = 'telegram_user_session'
CHAT = 'thailandparsing'
BATCH_SIZE = 200


async def fetch_all_messages(client, chat, min_id: int = 0, max_id: int = 0) -> list:
    from telethon.tl.types import Message
    messages = []
    offset_id = max_id if max_id else 0
    logger.info(f'Fetching from {CHAT} starting at offset_id={offset_id}...')
    while True:
        batch = await client.get_messages(
            chat,
            limit=BATCH_SIZE,
            offset_id=offset_id,
            min_id=min_id,
        )
        if not batch:
            break
        real_msgs = [m for m in batch if isinstance(m, Message)]
        messages.extend(real_msgs)
        oldest = min(m.id for m in real_msgs) if real_msgs else 0
        logger.info(f'  Got {len(real_msgs)} messages (oldest id: {oldest}), total so far: {len(messages)}')
        offset_id = oldest
        if len(batch) < BATCH_SIZE:
            break
        await asyncio.sleep(0.5)
    return messages


async def run_fetch():
    from telethon import TelegramClient

    if not TELETHON_API_ID or not TELETHON_API_HASH:
        logger.error('TELETHON_API_ID / TELETHON_API_HASH not set in environment!')
        return 0

    client = TelegramClient(SESSION_FILE, TELETHON_API_ID, TELETHON_API_HASH)
    phone = os.environ.get('TELETHON_PHONE', '')

    try:
        if phone:
            await client.start(phone=phone)
        else:
            await client.start()

        me = await client.get_me()
        logger.info(f'Logged in as: {me.first_name} (@{me.username})')

        # Find existing max/min IDs to avoid reprocessing
        from thailandparsing_parser import (
            load_listings, get_existing_ids, build_listing_from_scraped,
            save_listings, is_spam, extract_price, detect_city,
            detect_listing_type, extract_title_th, extract_source
        )
        from datetime import datetime, timezone

        data = load_listings()
        existing_ids = get_existing_ids(data)
        if 'real_estate' not in data:
            data['real_estate'] = []

        existing_nums = set()
        for eid in existing_ids:
            if eid.startswith('thailand_'):
                try:
                    existing_nums.add(int(eid.split('_')[1]))
                except ValueError:
                    pass

        logger.info(f'Existing listings: {len(data["real_estate"])}, IDs: {len(existing_nums)}')

        all_msgs = await fetch_all_messages(client, CHAT)
        logger.info(f'Total messages fetched: {len(all_msgs)}')

        new_count = 0
        for msg in all_msgs:
            if msg.id in existing_nums:
                continue

            text = msg.text or msg.caption or ''
            if not text or len(text) < 20:
                continue
            if is_spam(text):
                continue

            # Gather photos
            photos = []
            if msg.photo:
                try:
                    from telethon.tl.types import MessageMediaPhoto
                    if hasattr(msg, 'media') and msg.media:
                        # CDN approach not possible via MTProto directly, build CDN-style URL
                        # We'll use the file ID as best-effort identifier
                        pass
                except Exception:
                    pass

            item_id = f'thailand_{msg.id}'
            price_val, price_display = extract_price(text)
            city = detect_city(text)
            listing_type = detect_listing_type(text)
            title = extract_title_th(text)
            source = extract_source(text)
            telegram_link = f'https://t.me/{CHAT}/{msg.id}'

            import re
            tg_link_m = re.search(r'https?://t\.me/\S+', text)
            if tg_link_m:
                telegram_link = tg_link_m.group(0)

            date_str = msg.date.astimezone(timezone.utc).isoformat() if msg.date else datetime.now(timezone.utc).isoformat()

            item = {
                'id': item_id,
                'title': title,
                'description': text[:500],
                'text': text,
                'price': price_val,
                'price_display': price_display,
                'city': city,
                'listing_type': listing_type,
                'contact': source,
                'telegram_link': telegram_link,
                'photos': photos,
                'image_url': photos[0] if photos else '',
                'all_images': photos,
                'date': date_str,
                'source': 'telegram',
                'channel': CHAT,
            }

            data['real_estate'].append(item)
            existing_nums.add(msg.id)
            existing_ids.add(item_id)
            new_count += 1

            if new_count % 50 == 0:
                logger.info(f'  Saved {new_count} new listings so far...')
                data['real_estate'].sort(key=lambda x: x.get('date', ''), reverse=True)
                save_listings(data)

        # Final sort and save
        data['real_estate'].sort(key=lambda x: x.get('date', ''), reverse=True)
        save_listings(data)
        logger.info(f'Done. Added {new_count} new listings. Total: {len(data["real_estate"])}')
        return new_count

    except Exception as e:
        logger.error(f'Error: {e}', exc_info=True)
        return 0
    finally:
        await client.disconnect()


if __name__ == '__main__':
    asyncio.run(run_fetch())
