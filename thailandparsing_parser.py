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


def extract_price(text: str) -> tuple[int, str]:
    text_upper = text.upper()

    # THB patterns first
    thb_patterns = [
        r'(\d[\d\s.,]*\d|\d)\s*(?:baht|thb|บาท)',
        r'(?:thb|baht|฿|บาท)\s*(\d[\d\s.,]*)',
        r'฿\s*(\d[\d\s.,]*)',
        r'(\d[\d\s.,]*)\s*฿',
        r'PRICE[:\s]*(\d[\d\s.,]*)\s*(?:thb|baht|฿)?',
        r'RENT[:\s]*(\d[\d\s.,]*)\s*(?:thb|baht|฿)?',
        r'ราคา[:\s]*(\d[\d\s.,]*)',
        r'(\d{4,})\s*(?:thb|baht)?',
    ]
    for pat in thb_patterns:
        m = re.search(pat, text_upper)
        if m:
            raw = m.group(1).replace(' ', '').replace(',', '')
            try:
                num = parse_number_from_str(raw)
                if 100 <= num <= 500_000_000:
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
                if 10 <= num <= 10_000_000:
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
                if 10 <= num <= 10_000_000:
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
        clean = re.sub(r'[#*_]', '', line).strip()
        if len(clean) > 5:
            return clean[:120]
    fallback = re.sub(
        r'(?:источник|source|описание|цена|адрес|город|available)[:\s]*\S+\s*\n?',
        '', text, flags=re.IGNORECASE
    ).strip()
    return (fallback[:100] if fallback else text[:100])


def extract_images_from_update(update: dict) -> list:
    post = update.get('message') or update.get('channel_post') or {}
    photos = []
    if post.get('photo'):
        # Take largest version
        best = max(post['photo'], key=lambda p: p.get('file_size', 0))
        file_id = best.get('file_id', '')
        if file_id and BOT_TOKEN:
            try:
                import requests as req
                r = req.get(
                    f'https://api.telegram.org/bot{BOT_TOKEN}/getFile',
                    params={'file_id': file_id}, timeout=8
                )
                if r.ok:
                    path = r.json().get('result', {}).get('file_path', '')
                    if path:
                        url = f'https://api.telegram.org/file/bot{BOT_TOKEN}/{path}'
                        photos.append(url)
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
    if is_spam(text):
        return None

    msg_id = post.get('message_id', 0)
    item_id = f'thailand_{msg_id}'
    price_val, price_display = extract_price(text)
    city = detect_city(text)
    listing_type = detect_listing_type(text)
    title = extract_title_th(text)
    source = extract_source(text)
    photos = extract_images_from_update(update)

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
        'photos': photos,
        'image_url': photos[0] if photos else '',
        'all_images': photos,
        'date': date_str,
        'source': 'telegram',
        'channel': SOURCE_CHANNEL,
    }


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
