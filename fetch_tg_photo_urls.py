#!/usr/bin/env python3
"""
Fetch Telegram CDN photo URLs for Thailand listings by scraping og:image
from source channel posts referenced in listing texts.
No files are downloaded - only URLs are stored.
"""
import os
import re
import json
import time
import logging
import requests

logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
logger = logging.getLogger(__name__)

LISTINGS_FILE = 'listings_thailand.json'
LOCAL_PHOTO_DIR = 'static/images/thailand'
TG_URL_PATTERN = re.compile(r'https?://t\.me/([^/\s]+)/(\d+)')
OG_IMAGE_PATTERN = re.compile(r'<meta\s+property=["\']og:image["\']\s+content=["\'](.*?)["\']', re.IGNORECASE)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (compatible; TelegramBot/1.0)',
    'Accept-Language': 'ru,en;q=0.9',
}


def load_listings():
    with open(LISTINGS_FILE, encoding='utf-8') as f:
        return json.load(f)


def save_listings(data):
    tmp = LISTINGS_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, LISTINGS_FILE)


def get_og_image(channel: str, msg_id: str) -> str | None:
    url = f'https://t.me/{channel}/{msg_id}'
    try:
        r = requests.get(url, headers=HEADERS, timeout=10, allow_redirects=True)
        if r.status_code != 200:
            return None
        m = OG_IMAGE_PATTERN.search(r.text)
        if m:
            img_url = m.group(1).strip()
            if img_url and 'cdn' in img_url:
                return img_url
        return None
    except Exception as e:
        logger.debug(f'Error fetching {url}: {e}')
        return None


def remove_local_files():
    """Remove any previously downloaded local photo files."""
    if not os.path.isdir(LOCAL_PHOTO_DIR):
        return 0
    removed = 0
    for fname in os.listdir(LOCAL_PHOTO_DIR):
        if fname.endswith('.jpg'):
            try:
                os.remove(os.path.join(LOCAL_PHOTO_DIR, fname))
                removed += 1
            except Exception:
                pass
    logger.info(f'Removed {removed} local photo files')
    return removed


def fix_local_urls(data):
    """Clear local /static/ URLs from listings — they'll be refetched."""
    items = data.get('real_estate', [])
    cleared = 0
    for item in items:
        url = item.get('image_url', '')
        if url and url.startswith('/static/images/thailand/'):
            item['image_url'] = ''
            item['photos'] = []
            item['all_images'] = []
            cleared += 1
    logger.info(f'Cleared {cleared} local URL references from listings')
    return cleared


def fetch_og_photos(data):
    """Scrape og:image for listings that have a source t.me link."""
    items = data.get('real_estate', [])
    updated = 0
    skipped = 0
    errors = 0
    total = 0

    for item in items:
        # Skip if already has a proper Telegram CDN URL
        existing = item.get('image_url', '')
        if existing and ('api.telegram.org' in existing or 'cdn' in existing or 'telesco.pe' in existing):
            continue

        text = item.get('text', '') + '\n' + item.get('title', '')
        m = TG_URL_PATTERN.search(text)
        if not m:
            skipped += 1
            continue

        channel, post_id = m.group(1), m.group(2)
        total += 1

        img_url = get_og_image(channel, post_id)
        if img_url:
            item['image_url'] = img_url
            item['photos'] = [img_url]
            item['all_images'] = [img_url]
            updated += 1
            if updated % 20 == 0:
                logger.info(f'  Progress: {updated} photos fetched ({errors} errors)')
                save_listings(data)
        else:
            errors += 1

        time.sleep(0.3)  # rate limiting

    save_listings(data)
    logger.info(f'Done: {updated} photo URLs fetched, {errors} errors, {skipped} had no source link')
    return updated


def main():
    logger.info('=== Step 1: Load listings ===')
    data = load_listings()
    items = data.get('real_estate', [])
    logger.info(f'Total listings: {len(items)}')

    logger.info('=== Step 2: Clear local /static/ URL references ===')
    fix_local_urls(data)

    logger.info('=== Step 3: Remove downloaded local files ===')
    remove_local_files()

    logger.info('=== Step 4: Fetch og:image URLs from source channels ===')
    fetched = fetch_og_photos(data)

    data2 = load_listings()
    items2 = data2.get('real_estate', [])
    with_photos = sum(1 for x in items2 if x.get('image_url'))
    logger.info(f'=== DONE === {fetched} new photo URLs | Total with photos: {with_photos}/{len(items2)}')


if __name__ == '__main__':
    main()
