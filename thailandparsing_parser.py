import os
import json
import re
import time
import logging
import html as hlib
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get('VIETNAMPARSING_BOT_TOKEN', '')
SOURCE_CHANNEL = 'thailandparsing'
LISTINGS_FILE = 'listings_thailand.json'

USD_TO_THB = 34
EUR_TO_THB = 37

CITY_MAP = {
    'Бангкок': [
        'bangkok', 'бангкок', 'bang kok', 'bangkoc',
        'sukhumvit', 'silom', 'sathorn', 'asok', 'nana', 'ekkamai',
        'thonglor', 'ari', 'mo chit', 'lat phrao', 'bang na', 'onnut',
        'on nut', 'ratchada', 'huai khwang', 'din daeng', 'chatuchak',
        'phrom phong', 'udom suk', 'bearing', 'samrong',
    ],
    'Пхукет': [
        'phuket', 'пхукет', 'patong', 'kata', 'karon', 'rawai',
        'chalong', 'bang tao', 'bangtao', 'laguna', 'kamala', 'surin',
        'mai khao', 'nai harn', 'naiharn', 'cherng talay', 'ao po',
        'cape yamu', 'layan',
    ],
    'Паттайя': [
        'pattaya', 'паттайя', 'pattaia', 'jomtien', 'джомтьен',
        'naklua', 'pratumnak', 'bang saray', 'bang saen', 'nong prue',
        'east pattaya', 'north pattaya', 'south pattaya', 'central pattaya',
    ],
    'Самуи': [
        'samui', 'самуи', 'ko samui', 'koh samui', 'chaweng', 'lamai',
        'bophut', 'мае нам', 'mae nam', 'choeng mon', 'nathon',
    ],
    'Чиангмай': [
        'chiang mai', 'чиангмай', 'chiangmai', 'chang mai',
        'nimman', 'nimmanhaemin', 'old city', 'hang dong',
        'san kamphaeng', 'san sai', 'doi saket',
    ],
    'Краби': [
        'krabi', 'краби', 'ao nang', 'railay', 'koh lanta', 'ko lanta',
    ],
    'Хуахин': [
        'hua hin', 'хуахин', 'huahin', 'cha am', 'ча-ам',
    ],
    'Чианграй': [
        'chiang rai', 'чианграй', 'chiangrai',
    ],
    'Удон Тхани': [
        'udon thani', 'удон тхани', 'udonthani',
    ],
}

LISTING_TYPE_RENT = [
    'аренд', 'rent', 'for rent', 'сдам', 'сдаю', 'сдается', 'сдаётся',
    'снять', 'краткосроч', 'долгосроч', 'посуточно', 'available',
    'lease', 'per month', 'per night', '/month', '/mo', '/night',
    'monthly', 'ราคาเช่า', 'เช่า',
]

LISTING_TYPE_SALE = [
    'продаж', 'продам', 'продается', 'продаётся', 'продаю', 'for sale',
    'купить', 'покупка', 'buy', 'purchase', 'selling', 'ราคาขาย', 'ขาย',
]

SPAM_KEYWORDS = [
    'casino', 'forex', 'crypto trading', 'заработок онлайн', 'пассивный доход',
    'бинарные опционы', 'click here', 'sign up now', 'register now',
    'advertising', 'binary options', 'invest', 'инвестиции в крипт',
    'обмен валют', 'обменник', 'курс обмена', 'лучший курс', 'exchange rate',
    'currency exchange', 'money exchange', 'обменяю валют',
    # Gambling / casino spam
    'джекпот', 'jackpot', 'slot', 'ставки онлайн', 'играю здесь',
    'казино онлайн', 'wild casino', 'crypto casino',
    # Scam-group promos (not real estate)
    'создали группу мошенники', 'добавляем аккаунты мошенников',
    'мошенники пишут вам в лс',
    # Off-topic ads in real estate channels
    'доставка одноразовых',
]

SPAM_REGEX_PATTERNS = [
    re.compile(r'(выиграл|выигра\w+).{0,60}(здесь|сейчас|тут|казин|casino)', re.IGNORECASE),
    re.compile(r'САМЫЙ ЛУЧШИЙ КАЗ', re.IGNORECASE),
    re.compile(r'НАШИ ПАРТНЕРЫ.{0,50}ВЕСЬ ТАИЛАНД', re.IGNORECASE | re.DOTALL),
    re.compile(r'АВТО И МОТО ТАИЛАНД.{0,200}МОШЕННИК', re.IGNORECASE | re.DOTALL),
    re.compile(r'ВНИМАНИЕ МОШЕННИКИ(?!.{0,300}(аренд|продаж|квартир|недвижим|апартамент|villa))', re.IGNORECASE | re.DOTALL),
]

SKIP_LINE_PREFIXES_TH = re.compile(
    r'^(?:источник|source|описание|цена|price|адрес|address|тип|type|город|city|available|'
    r'расположение|location|контакт|contact|telegram|whatsapp|ссылка|link|https?://|ราคา|ที่อยู่)',
    re.IGNORECASE
)


def format_price_thb(amount_thb: int) -> str:
    s = str(int(amount_thb))
    groups = []
    while len(s) > 3:
        groups.insert(0, s[-3:])
        s = s[:-3]
    if s:
        groups.insert(0, s)
    return ' '.join(groups) + ' THB'


def parse_number_from_str(s: str) -> float:
    s = s.strip()
    s = re.sub(r'[,\s]', '', s)
    # Handle dot-separator for millions (e.g. 2.5M)
    if re.match(r'^\d+\.\d+$', s):
        return float(s)
    s = s.replace('.', '').replace(',', '')
    try:
        return float(s)
    except ValueError:
        return 0.0


def _is_year(n: float) -> bool:
    """Return True if n looks like a calendar year (2000–2040), not a price."""
    return 2000 <= n <= 2040


def extract_price(text: str) -> tuple[int, str]:
    # Strip URLs first so post IDs in t.me/channel/123456 aren't parsed as prices
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r't\.me/\S+', '', text)
    text_upper = text.upper()

    # Handle "X млн/миллион бат/baht" patterns first (before standard patterns)
    mln_baht_patterns = [
        r'(\d+[.,]?\d*)\s*(?:МЛН|МИЛЛИОН|MLN|MILLION)\s*(?:БАТ|БАТА|БАТОВ|BAHT|THB)',
        r'(?:ОТ|ДО|ЦЕНА|СТОИМОСТЬ|PRICE)[:\s]*(\d+[.,]?\d*)\s*(?:МЛН|МИЛЛИОН)\s*(?:БАТ|BAHT|THB)',
        r'(\d+[.,]?\d*)\s*(?:МЛН|МИЛЛИОН)\s*(?:БАТ|BAHT|THB)',
    ]
    for pat in mln_baht_patterns:
        m = re.search(pat, text_upper)
        if m:
            raw = m.group(1).replace(',', '.')
            try:
                num = float(raw) * 1_000_000
                if 100_000 <= num <= 500_000_000:
                    return int(num), format_price_thb(int(num))
            except Exception:
                pass

    # THB patterns — explicit currency marker required or strong price context
    # Minimum 1 000 THB (~$30) to exclude years (2025, 2026, etc.)
    thb_patterns = [
        # Explicit THB/baht/บาท marker
        (r'(\d[\d\s.,]*\d|\d)\s*(?:baht|thb|บาท)', 'THB'),
        (r'(?:thb|baht|฿|บาท)\s*(\d[\d\s.,]*)', 'THB'),
        (r'฿\s*(\d[\d\s.,]*)', 'THB'),
        (r'(\d[\d\s.,]*)\s*฿', 'THB'),
        # Price keyword + number (with or without explicit THB)
        (r'PRICE[:\s]+(\d[\d\s.,]+)', 'THB'),
        (r'RENT[:\s]+(\d[\d\s.,]+)', 'THB'),
        (r'ราคา[:\s]*(\d[\d\s.,]*)', 'THB'),
        # Russian price keywords (common in this channel)
        (r'(?:ЦЕНА|СТОИМОСТЬ|АРЕНДА|ПРОДАЖА)[^\d]{0,10}(\d[\d\s.,]+)', 'THB'),
        (r'(\d[\d\s.,]+)\s*(?:БАТ|БАТА|БАТОВ|BAHT)\b', 'THB'),
        # Large standalone number >= 10 000 with optional THB (likely real estate price)
        # MUST be >= 10 000 to exclude years
        (r'\b(\d[\d\s.,]{4,})\s*(?:thb|baht|฿|บาท)\b', 'THB'),
    ]
    for pat, _ in thb_patterns:
        m = re.search(pat, text_upper)
        if m:
            raw = m.group(1).replace(' ', '').replace(',', '')
            try:
                num = parse_number_from_str(raw)
                if 1_000 <= num <= 500_000_000 and not _is_year(num):
                    return int(num), format_price_thb(int(num))
            except Exception:
                pass

    # USD patterns
    usd_pat = [
        r'\$\s*(\d[\d\s.,]*)',
        r'(\d[\d\s.,]*)\s*(?:USD|\$)',
        r'USD\s*(\d[\d\s.,]*)',
    ]
    for pat in usd_pat:
        m = re.search(pat, text_upper)
        if m:
            raw = m.group(1).replace(' ', '').replace(',', '')
            try:
                num = parse_number_from_str(raw)
                if 10 <= num <= 10_000_000 and not _is_year(num):
                    thb = int(num * USD_TO_THB)
                    return thb, format_price_thb(thb)
            except Exception:
                pass

    # EUR patterns
    eur_pat = [
        r'€\s*(\d[\d\s.,]*)',
        r'(\d[\d\s.,]*)\s*(?:EUR|€)',
        r'EUR\s*(\d[\d\s.,]*)',
    ]
    for pat in eur_pat:
        m = re.search(pat, text_upper)
        if m:
            raw = m.group(1).replace(' ', '').replace(',', '')
            try:
                num = parse_number_from_str(raw)
                if 10 <= num <= 10_000_000 and not _is_year(num):
                    thb = int(num * EUR_TO_THB)
                    return thb, format_price_thb(thb)
            except Exception:
                pass

    return 0, ''


def detect_city(text: str) -> str:
    text_l = text.lower()
    for city, keywords in CITY_MAP.items():
        for kw in keywords:
            if kw in text_l:
                return city
    return 'Тайланд'


def detect_listing_type(text: str) -> str:
    tl = text.lower()
    for kw in LISTING_TYPE_SALE:
        if kw in tl:
            return 'sale'
    for kw in LISTING_TYPE_RENT:
        if kw in tl:
            return 'rent'
    return 'rent'


def is_spam(text: str) -> bool:
    tl = text.lower()
    for kw in SPAM_KEYWORDS:
        if kw in tl:
            return True
    for pat in SPAM_REGEX_PATTERNS:
        if pat.search(text):
            return True
    return False


def extract_source(text: str) -> str:
    m = re.search(r'(?:источник|source)[:\s]*(@\S+|t\.me/\S+)', text, re.IGNORECASE)
    if m:
        src = m.group(1)
        if not src.startswith('@'):
            src = '@' + src.split('/')[-1]
        return src
    m2 = re.search(r'https?://t\.me/(\w+)', text)
    if m2:
        return '@' + m2.group(1)
    return '@' + SOURCE_CHANNEL


def extract_title_th(text: str) -> str:
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    for line in lines:
        if SKIP_LINE_PREFIXES_TH.match(line):
            continue
        # Skip lines that are just a URL
        if re.match(r'^https?://\S+$', line):
            continue
        clean = re.sub(r'[#*_]', '', line).strip()
        if len(clean) > 5:
            return clean[:120]
    # Fallback: strip link/source/price lines, use remaining text
    fallback = re.sub(
        r'(?:источник|source|описание|цена|адрес|город|available|ссылка|link)[:\s]*\S+\s*\n?',
        '', text, flags=re.IGNORECASE
    ).strip()
    fallback = re.sub(r'https?://\S+', '', fallback).strip()
    return (fallback[:100] if len(fallback) > 5 else 'Объявление о недвижимости')


def _scrape_cdn_photos(channel: str, post_id: int) -> list:
    """Scrape permanent CDN photo URLs from the public Telegram viewer."""
    if not post_id:
        return []
    try:
        import requests as req
        headers = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'}
        r = req.get(f'https://t.me/s/{channel}?before={post_id + 1}', headers=headers, timeout=10)
        if r.status_code != 200:
            return []
        html_text = r.text
        pattern = rf'data-post="{channel}/{post_id}"(.*?)(?=data-post="{channel}/\d+"|\Z)'
        block_m = re.search(pattern, html_text, re.DOTALL | re.IGNORECASE)
        block = block_m.group(0) if block_m else html_text
        imgs = re.findall(r"background-image:url\('(https://cdn[^']+)'\)", block)
        return list(dict.fromkeys(imgs))
    except Exception:
        return []


def extract_images_from_update(update: dict, post_id: int = 0) -> list:
    post = update.get('message') or update.get('channel_post') or {}
    # First try CDN scraping for permanent URLs
    if post_id:
        cdn = _scrape_cdn_photos(SOURCE_CHANNEL, post_id)
        if cdn:
            return cdn
    # Fallback: Bot API URL (expires, but better than nothing)
    photos = []
    if post.get('photo') and BOT_TOKEN:
        best = max(post['photo'], key=lambda p: p.get('file_size', 0))
        file_id = best.get('file_id', '')
        if file_id:
            try:
                import requests as req
                r = req.get(
                    f'https://api.telegram.org/bot{BOT_TOKEN}/getFile',
                    params={'file_id': file_id}, timeout=8
                )
                if r.ok:
                    path = r.json().get('result', {}).get('file_path', '')
                    if path:
                        photos.append(f'https://api.telegram.org/file/bot{BOT_TOKEN}/{path}')
            except Exception:
                pass
    return photos


def load_listings() -> dict:
    if os.path.exists(LISTINGS_FILE):
        try:
            with open(LISTINGS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {'real_estate': []}


def save_listings(data: dict):
    tmp = LISTINGS_FILE + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, LISTINGS_FILE)


def get_existing_ids(data: dict) -> set:
    ids = set()
    for cat, items in data.items():
        if isinstance(items, list):
            for item in items:
                if item.get('id'):
                    ids.add(item['id'])
    return ids


def process_thailand_update(update: dict) -> dict | None:
    post = update.get('message') or update.get('channel_post')
    if not post:
        return None

    chat = post.get('chat', {})
    chat_username = chat.get('username', '')
    if chat_username.lower() != SOURCE_CHANNEL.lower():
        return None

    text = post.get('text') or post.get('caption') or ''
    if not text or len(text) < 20:
        return None
    if not _has_real_content(text):
        return None
    if is_spam(text):
        return None

    msg_id = post.get('message_id', 0)
    item_id = f'thailand_{msg_id}'
    price_val, price_display = extract_price(text)
    city = detect_city(text)
    listing_type = detect_listing_type(text)
    title = extract_title_th(text)
    source = extract_source(text)
    photos = extract_images_from_update(update, post_id=msg_id)

    # Telegram link: check text for explicit link, otherwise build from msg_id
    tg_link_m = re.search(r'https?://t\.me/\S+', text)
    telegram_link = tg_link_m.group(0) if tg_link_m else (f'https://t.me/{SOURCE_CHANNEL}/{msg_id}' if msg_id else '')

    date_ts = post.get('date', 0)
    date_str = datetime.fromtimestamp(date_ts, tz=timezone.utc).isoformat() if date_ts else datetime.now(timezone.utc).isoformat()

    return {
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
        'channel': SOURCE_CHANNEL,
    }


def _clean_html(html_str: str) -> str:
    """Strip HTML tags and decode entities."""
    text = re.sub(r'<br\s*/?>', '\n', html_str, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '', text)
    text = hlib.unescape(text)
    return text.strip()


def scrape_thailand_page(before_id: int = None) -> list:
    """Scrape one page from t.me/s/thailandparsing public viewer."""
    url = f'https://t.me/s/{SOURCE_CHANNEL}'
    if before_id:
        url += f'?before={before_id}'
    try:
        import requests as req
        resp = req.get(url, timeout=15, headers={'User-Agent': 'Mozilla/5.0 (compatible; Python/3.11 parser)'})
        resp.raise_for_status()
        page = resp.text
    except Exception as e:
        logger.error(f'[TH scrape] Failed {url}: {e}')
        return []

    results = []
    blocks = re.split(r'(?=<div class="tgme_widget_message_wrap)', page)
    for block in blocks[1:]:
        post_id_m = re.search(rf'data-post="{SOURCE_CHANNEL}/(\d+)"', block, re.IGNORECASE)
        if not post_id_m:
            continue
        post_id = int(post_id_m.group(1))
        date_m = re.search(r'datetime="([^"]+)"', block)
        date_str = date_m.group(1) if date_m else datetime.now(timezone.utc).isoformat()
        text_m = re.search(r'class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', block, re.DOTALL)
        text = _clean_html(text_m.group(1)) if text_m else ''
        imgs = re.findall(r"background-image:url\('(https://cdn[^']+)'\)", block)
        imgs = list(dict.fromkeys(imgs))
        results.append({'post_id': post_id, 'date': date_str, 'text': text, 'images': imgs})
    return results


def _has_real_content(text: str) -> bool:
    """Return True if text has meaningful content beyond Источник/Ссылка metadata."""
    meta_re = re.compile(r'^(источник|ссылка|link|source)\s*:', re.IGNORECASE)
    main_lines = [l.strip() for l in text.split('\n') if l.strip() and not meta_re.match(l.strip())]
    return len(' '.join(main_lines)) >= 15


def build_listing_from_scraped(msg: dict) -> dict | None:
    """Build a listing dict from a scraped Thailand page message."""
    text = msg.get('text', '')
    if not text or len(text) < 20:
        return None
    if not _has_real_content(text):
        return None
    if is_spam(text):
        return None

    post_id = msg['post_id']
    item_id = f'thailand_{post_id}'
    price_val, price_display = extract_price(text)
    city = detect_city(text)
    listing_type = detect_listing_type(text)
    title = extract_title_th(text)
    source = extract_source(text)
    photos = msg.get('images', [])
    telegram_link = f'https://t.me/{SOURCE_CHANNEL}/{post_id}'

    return {
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
        'date': msg.get('date', datetime.now(timezone.utc).isoformat()),
        'source': 'telegram',
        'channel': SOURCE_CHANNEL,
    }


def fetch_all_thailand(max_pages: int = 60) -> int:
    """Scrape ALL available posts from t.me/s/thailandparsing and save to JSON."""
    logger.info(f'[TH] Starting full fetch from t.me/s/{SOURCE_CHANNEL} (max {max_pages} pages)...')
    data = load_listings()
    existing_ids = get_existing_ids(data)
    if 'real_estate' not in data:
        data['real_estate'] = []

    all_msgs = []
    before_id = None
    pages = 0

    while pages < max_pages:
        page_msgs = scrape_thailand_page(before_id=before_id)
        if not page_msgs:
            break
        all_msgs.extend(page_msgs)
        pages += 1
        oldest = min(m['post_id'] for m in page_msgs)
        before_id = oldest
        logger.info(f'[TH] Page {pages}: got {len(page_msgs)} posts (oldest id: {oldest})')
        if len(page_msgs) < 3:
            break
        time.sleep(1.2)

    logger.info(f'[TH] Scraped {len(all_msgs)} posts across {pages} pages. Processing...')

    new_count = 0
    # Process newest-first (all_msgs is newest-first already)
    for msg in all_msgs:
        item = build_listing_from_scraped(msg)
        if not item:
            continue
        if item['id'] in existing_ids:
            continue
        data['real_estate'].insert(0, item)
        existing_ids.add(item['id'])
        new_count += 1

    if new_count > 0:
        save_listings(data)

    # Sort all by date descending
    data = load_listings()
    data['real_estate'].sort(key=lambda x: x.get('date', ''), reverse=True)
    save_listings(data)

    logger.info(f'[TH] Full fetch complete. Added {new_count} new listings. Total: {len(data.get("real_estate", []))}')
    return new_count


def add_thailand_listings(updates: list) -> int:
    if not updates:
        return 0
    data = load_listings()
    existing_ids = get_existing_ids(data)
    new_count = 0
    for upd in updates:
        item = process_thailand_update(upd)
        if not item:
            continue
        if item['id'] in existing_ids:
            continue
        if 'real_estate' not in data:
            data['real_estate'] = []
        data['real_estate'].insert(0, item)
        existing_ids.add(item['id'])
        new_count += 1
        logger.info(f"[TH] New: [{item['city']}] {item['title'][:60]} | {item['price_display']}")
    if new_count > 0:
        save_listings(data)
    return new_count
