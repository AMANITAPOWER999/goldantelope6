#!/usr/bin/env python3
"""
Fix Thailand listings:
1. Re-process all prices (remove URL contamination)
2. Download photos from Telethon for historical listings
3. Remove truly non-Thailand listings
"""
import os
import io
import re
import json
import asyncio
import logging
import time
from datetime import timezone

logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
logger = logging.getLogger(__name__)

TELETHON_SESSION = 'telegram_user_session'
LISTINGS_FILE = 'listings_thailand.json'
PHOTOS_DIR = 'static/images/thailand'
STATIC_URL_BASE = '/static/images/thailand'

TELETHON_API_ID = int(os.environ.get('TELETHON_API_ID', 0))
TELETHON_API_HASH = os.environ.get('TELETHON_API_HASH', '')


def load_listings():
    with open(LISTINGS_FILE, encoding='utf-8') as f:
        return json.load(f)


def save_listings(data):
    tmp = LISTINGS_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, LISTINGS_FILE)


def fix_prices():
    """Re-run extract_price on all listings to remove URL-contaminated prices."""
    from thailandparsing_parser import extract_price, extract_title_th, detect_city, detect_listing_type

    data = load_listings()
    items = data.get('real_estate', [])
    fixed = 0
    for item in items:
        text = item.get('text', '')
        if not text:
            continue
        old_price = item.get('price', 0)
        new_price, new_display = extract_price(text)
        if old_price != new_price:
            item['price'] = new_price
            item['price_display'] = new_display
            fixed += 1
        # Also fix titles that might have been bad
        new_title = extract_title_th(text)
        if new_title and new_title != item.get('title', ''):
            old_title = item.get('title', '')
            # Only update if old title was clearly a URL-based title
            if old_title.startswith('Ссылка:') or old_title.startswith('http') or not old_title:
                item['title'] = new_title

    save_listings(data)
    logger.info(f'Fixed prices for {fixed} listings')
    return fixed


def filter_non_thailand():
    """Remove listings that clearly belong to Vietnam/other countries (not Thailand)."""
    from thailandparsing_parser import is_spam

    # Extended spam keywords for non-Thailand listings
    non_thailand_keywords = [
        'vnd', 'вьетнам', 'hanoi', 'ханой', 'хошимин', 'ho chi minh',
        'da nang', 'дананг', 'nha trang', 'нячанг', 'hoi an', 'хой ан',
        'mui ne', 'муй не', 'vung tau', 'вунг тау',
    ]

    data = load_listings()
    items = data.get('real_estate', [])
    filtered = []
    removed = 0
    for item in items:
        text = (item.get('text', '') + ' ' + item.get('title', '')).lower()
        price_display = item.get('price_display', '')
        is_vn = False
        # Remove if price is in VND
        if 'VND' in price_display or 'vnd' in price_display.lower():
            is_vn = True
        # Remove if text clearly mentions Vietnam cities (not just partial matches)
        for kw in non_thailand_keywords:
            if kw in text:
                is_vn = True
                break
        if is_vn:
            removed += 1
            logger.info(f'  Removed non-Thailand: [{item["id"]}] {item["title"][:60]}')
        else:
            filtered.append(item)

    data['real_estate'] = filtered
    save_listings(data)
    logger.info(f'Removed {removed} non-Thailand listings. Remaining: {len(filtered)}')
    return removed


async def fetch_photos_telethon():
    """Download photos for historical listings via Telethon."""
    from telethon import TelegramClient
    from telethon.tl.types import Message as TLMessage, MessageMediaPhoto

    os.makedirs(PHOTOS_DIR, exist_ok=True)

    client = TelegramClient(TELETHON_SESSION, TELETHON_API_ID, TELETHON_API_HASH)

    try:
        await client.connect()
        if not await client.is_user_authorized():
            logger.error('Session not authorized!')
            return 0

        me = await client.get_me()
        logger.info(f'Connected as {me.first_name}')

        # Load listings without photos
        data = load_listings()
        items = data.get('real_estate', [])

        # Build mapping: msg_id -> item for items without photos
        need_photos = {}
        for item in items:
            if item.get('photos') or item.get('image_url'):
                continue  # already has photo
            item_id = item.get('id', '')
            if not item_id.startswith('thailand_'):
                continue
            try:
                msg_id = int(item_id.split('_')[1])
                need_photos[msg_id] = item
            except (ValueError, IndexError):
                continue

        logger.info(f'Need photos for {len(need_photos)} listings')
        if not need_photos:
            logger.info('All listings already have photos!')
            return 0

        # Sort by msg_id descending (process newest first)
        msg_ids = sorted(need_photos.keys(), reverse=True)

        BATCH_SIZE = 50
        photo_count = 0
        save_interval = 100
        saved_count = 0

        for batch_start in range(0, len(msg_ids), BATCH_SIZE):
            batch_ids = msg_ids[batch_start:batch_start + BATCH_SIZE]

            try:
                msgs = await client.get_messages('thailandparsing', ids=batch_ids)
            except Exception as e:
                logger.warning(f'Batch {batch_start}: error getting messages: {e}')
                await asyncio.sleep(2)
                continue

            for msg in msgs:
                if not msg or not isinstance(msg, TLMessage):
                    continue
                if not msg.media or not isinstance(msg.media, MessageMediaPhoto):
                    continue

                msg_id = msg.id
                photo_path = os.path.join(PHOTOS_DIR, f'{msg_id}.jpg')

                # Skip if already downloaded
                if os.path.exists(photo_path) and os.path.getsize(photo_path) > 1000:
                    url = f'{STATIC_URL_BASE}/{msg_id}.jpg'
                    item = need_photos.get(msg_id)
                    if item:
                        item['photos'] = [url]
                        item['image_url'] = url
                        item['all_images'] = [url]
                    continue

                try:
                    buf = io.BytesIO()
                    await client.download_media(msg.media, file=buf)
                    buf.seek(0)
                    img_bytes = buf.read()
                    if len(img_bytes) < 1000:
                        continue

                    with open(photo_path, 'wb') as f:
                        f.write(img_bytes)

                    url = f'{STATIC_URL_BASE}/{msg_id}.jpg'
                    item = need_photos.get(msg_id)
                    if item:
                        item['photos'] = [url]
                        item['image_url'] = url
                        item['all_images'] = [url]

                    photo_count += 1
                    saved_count += 1

                    if saved_count % 10 == 0:
                        logger.info(f'  Downloaded {photo_count} photos so far...')

                    if saved_count >= save_interval:
                        save_listings(data)
                        saved_count = 0

                except Exception as e:
                    logger.warning(f'  Photo {msg_id}: download error: {e}')
                    await asyncio.sleep(0.5)

            # Small delay between batches
            await asyncio.sleep(0.3)

            # Flood wait check
            if (batch_start // BATCH_SIZE) % 20 == 19:
                logger.info(f'  Progress: {batch_start + BATCH_SIZE}/{len(msg_ids)}, photos: {photo_count}')
                await asyncio.sleep(1)

        # Final save
        save_listings(data)
        logger.info(f'Photo fetch complete. Downloaded {photo_count} photos.')
        return photo_count

    except Exception as e:
        logger.error(f'Error in photo fetch: {e}', exc_info=True)
        return 0
    finally:
        await client.disconnect()


async def main():
    logger.info('=== Step 1: Fix prices ===')
    fixed = fix_prices()

    logger.info('=== Step 2: Filter non-Thailand listings ===')
    removed = filter_non_thailand()

    logger.info('=== Step 3: Download photos via Telethon ===')
    photos = await fetch_photos_telethon()

    # Final stats
    data = load_listings()
    items = data.get('real_estate', [])
    with_photos = sum(1 for x in items if x.get('photos'))
    logger.info(f'=== DONE ===')
    logger.info(f'Total listings: {len(items)}')
    logger.info(f'With photos: {with_photos}')
    logger.info(f'Prices fixed: {fixed}')
    logger.info(f'Non-Thailand removed: {removed}')
    logger.info(f'New photos downloaded: {photos}')


if __name__ == '__main__':
    asyncio.run(main())
