import os
import json
import asyncio
import hashlib
from datetime import datetime
from telethon import TelegramClient

API_ID = int(os.environ.get('TELETHON_API_ID', 0))
API_HASH = os.environ.get('TELETHON_API_HASH', '')

# Дополнительные каналы для парсинга
ADDITIONAL_CHANNELS = {
    'vietnam': [
        'hanoi_expats', 'hcm_expats', 'vietnam_talk', 'saigon_market',
        'nha_trang_sell', 'can_tho_market', 'dalat_chat', 'vung_tau_deals',
        'phu_quoc_market', 'haiphong_talk'
    ],
    'thailand': [
        'bangkok_expats', 'phuket_sell', 'chiang_mai_market', 'pattaya_deals',
        'samui_marketplace', 'krabi_expats'
    ],
    'indonesia': [
        'bali_marketplace', 'jakarta_expats', 'yogyakarta_sell', 'surabaya_deals',
        'bandung_market', 'medan_expats'
    ],
    'india': [
        'goa_marketplace', 'delhi_deals', 'mumbai_expats', 'bangalore_market'
    ]
}

def is_english_only(text):
    """Check if text is only English"""
    if not text or len(text) < 10:
        return True
    non_english_chars = 0
    for char in text:
        if ord(char) > 127 and char not in '.,!?-…()[]{}":;/\\ @':
            non_english_chars += 1
    return non_english_chars == 0

def is_spam(text):
    """Check if text is spam/promo"""
    if not text:
        return False
    spam_keywords = [
        'deriv.com', 'synthetic indices', 'trading account',
        'round-the-clock trading', 'forex', 'crypto trading',
        'kumpulan video viral', 'full video', 'join grup', 'klik link',
        'video-info-viral', 'join sekarang',
        'rent account', 'rent linkedin', 'rent facebook', 'make money',
        'passive income', 'rent out', 'advertising account',
        'grow your business', 'promote message', 'promotion packages',
        'reach more customers', 'boost visibility', 'drive engagement',
        'anda ingin sukses', 'ubah cara berfikir', 'positive thinking',
        'salam sukses', 'mulai sebelum orang',
        'notif sms', 'hak cipta hack', 'bootloader', 'fingerprint'
    ]
    return any(keyword in text.lower() for keyword in spam_keywords)

def get_image_hash(image_data):
    """Get hash of image"""
    if not image_data:
        return None
    return hashlib.md5(image_data).hexdigest()

async def parse_additional_channels():
    """Парсер дополнительных каналов"""
    try:
        client = TelegramClient('goldantelope_additional', API_ID, API_HASH)
        await client.connect()
    except Exception as e:
        print(f"❌ Ошибка подключения: {str(e)[:100]}")
        return
    
    try:
        if not await client.is_user_authorized():
            print("❌ Сессия не авторизована!")
            return
        
        me = await client.get_me()
        print(f"✅ Авторизован как: {me.first_name}")
        
        # Парсим каждую страну
        for country, channels in ADDITIONAL_CHANNELS.items():
            listings_file = f'listings_{country}.json'
            
            # Load existing
            existing = []
            if os.path.exists(listings_file):
                try:
                    with open(listings_file, 'r', encoding='utf-8') as f:
                        existing = json.load(f)
                except:
                    pass
            
            existing_ids = {item['id'] for item in existing}
            existing_hashes = {item.get('image_hash') for item in existing if item.get('image_hash')}
            new_count = 0
            skipped_english = 0
            
            print(f"\n🌐 {country.upper()}: парсинг доп. каналов...")
            
            for channel in channels:
                try:
                    # Try to get entity
                    try:
                        entity = await client.get_entity(f"@{channel}")
                    except:
                        await asyncio.sleep(1)
                        continue
                    
                    # Get messages - менее агрессивно (только 15 сообщений)
                    messages = await client.get_messages(entity, limit=15)
                    
                    for msg in messages:
                        if not msg.text or len(msg.text) < 20:
                            continue
                        
                        if is_english_only(msg.text):
                            skipped_english += 1
                            continue
                        
                        if is_spam(msg.text):
                            continue
                        
                        item_id = f"{channel}_{msg.id}"
                        if item_id in existing_ids:
                            continue
                        
                        image_url = None
                        image_hash = None
                        has_media = False
                        
                        # Check for media
                        if msg.media:
                            has_media = True
                        
                        item = {
                            'id': item_id,
                            'category': 'chat',
                            'title': msg.text[:100],
                            'description': msg.text,
                            'date': msg.date.isoformat(),
                            'source_channel': f"@{channel}",
                            'message_id': msg.id,
                            'image_url': image_url,
                            'image_hash': image_hash,
                            'has_media': has_media,
                            'price': None
                        }
                        existing.append(item)
                        existing_ids.add(item_id)
                        new_count += 1
                    
                    if new_count > 0:
                        print(f"  ✓ @{channel}: +{new_count}")
                    
                except Exception as e:
                    error_msg = str(e)[:50]
                    if 'rate' not in error_msg.lower():
                        pass
                
                # Задержка между каналами - 2 сек (менее агрессивно)
                await asyncio.sleep(2.5)
            
            # Save updated listings
            if new_count > 0:
                with open(listings_file, 'w', encoding='utf-8') as f:
                    json.dump(existing, f, ensure_ascii=False, indent=2)
                print(f"✅ {country}: +{new_count} объявлений (всего {len(existing)})")
                if skipped_english > 0:
                    print(f"   🚫 Отклонено англ.: {skipped_english}")
            
            await asyncio.sleep(0.5)
    
    finally:
        try:
            await client.disconnect()
        except:
            pass

if __name__ == '__main__':
    print(f"🔄 Additional Parser: {datetime.now().strftime('%H:%M:%S')}")
    try:
        asyncio.run(parse_additional_channels())
    except Exception as e:
        print(f"❌ Error: {e}")
    print("\n✅ Завершено!")

