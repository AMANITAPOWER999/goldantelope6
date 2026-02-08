from flask import Flask, render_template, jsonify, request, Response
from datetime import datetime, timedelta
import json
import os
import time
import requests
import re
import hashlib
from pathlib import Path
import threading

# Lock for file operations to prevent race conditions
file_lock = threading.Lock()

# Data cache to prevent heavy disk I/O
data_cache = {}
DATA_CACHE_TTL = 30 # Cache data for 30 seconds

GOOGLE_AI_API_KEY = os.environ.get('GOOGLE_AI_API_KEY', '')
translation_cache = {}

app = Flask(__name__, static_folder='static', static_url_path='/static')
app.secret_key = os.environ.get("SESSION_SECRET")

online_users = {}
ONLINE_TIMEOUT = 60
BASE_ONLINE = 287

TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')

def send_telegram_notification(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        }
        response = requests.post(url, data=data, timeout=10)
        return response.status_code == 200
    except Exception as e:
        print(f"Telegram notification error: {e}")
        return False

def send_telegram_message(chat_id, message, reply_markup=None):
    if not TELEGRAM_BOT_TOKEN:
        return False
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML"
        }
        if reply_markup:
            data["reply_markup"] = json.dumps(reply_markup)
        response = requests.post(url, data=data, timeout=10)
        return response.status_code == 200
    except Exception as e:
        print(f"Telegram message error: {e}")
        return False

WELCOME_MESSAGE = """🌏 Крупнейший русскоязычный гид, он же сервис-хаб, телеграмм объявлений в Юго-Восточной Азии.

<b>Наши страны:</b>
🇻🇳 Вьетнам (5,800+ объявлений)
🇹🇭 Таиланд (2,400+ объявлений)
🇮🇳 Индия (1,200+ объявлений)
🇮🇩 Индонезия (800+ объявлений)

<b>Категории:</b>
🏠 Недвижимость - аренда и продажа
🍽️ Рестораны и кафе
🧳 Экскурсии и туры
🏍️ Транспорт - байки, авто, яхты
🎮 Развлечения
💱 Обмен валют
🛍️ Барахолка
🏥 Медицина
📰 Новости
💬 Чат сообщества

В нашем мини приложении вы можете добавить объявление или услугу!
"""

# Данные хранятся в JSON файле по странам
DATA_FILE = "listings_data.json"

def create_empty_data():
    return {
        "restaurants": [],
        "tours": [],
        "transport": [],
        "real_estate": [],
        "money_exchange": [],
        "entertainment": [],
        "marketplace": [],
        "visas": [],
        "news": [],
        "medicine": [],
        "kids": [],
        "chat": []
    }

def load_data(country='vietnam'):
    now = time.time()
    if country in data_cache and now - data_cache[country]['time'] < DATA_CACHE_TTL:
        return data_cache[country]['data']
    
    country_file = f"listings_{country}.json"
    result = create_empty_data()
    
    if os.path.exists(country_file):
        try:
            with open(country_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, dict):
                    result = data
                else:
                    # Если данные в файле - список, распределяем по категориям
                    category_map = {
                        'bikes': 'transport',
                        'real_estate': 'real_estate',
                        'exchange': 'money_exchange',
                        'money_exchange': 'money_exchange',
                        'food': 'restaurants',
                        'restaurants': 'restaurants'
                    }
                    for item in data:
                        if not isinstance(item, dict): continue
                        cat = item.get('category', 'chat')
                        mapped_cat = category_map.get(cat, cat)
                        if mapped_cat in result:
                            result[mapped_cat].append(item)
        except Exception as e:
            print(f"Error loading country file {country_file}: {e}")
    
    elif os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                all_data = json.load(f)
                if country in all_data:
                    result = all_data[country]
        except Exception as e:
            print(f"Error loading DATA_FILE for {country}: {e}")
            
    data_cache[country] = {'data': result, 'time': now}
    return result

def load_all_data():
    now = time.time()
    if 'all' in data_cache and now - data_cache['all']['time'] < DATA_CACHE_TTL:
        return data_cache['all']['data']
        
    result = {
        'vietnam': create_empty_data(),
        'thailand': create_empty_data(),
        'india': create_empty_data(),
        'indonesia': create_empty_data()
    }
    
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                result = json.load(f)
        except Exception as e:
            print(f"Error loading DATA_FILE: {e}")
            # Try to recover from country files if DATA_FILE is corrupted
            for country in result.keys():
                result[country] = load_data(country)
            
    data_cache['all'] = {'data': result, 'time': now}
    return result

def save_data(country='vietnam', data=None):
    if not data or not isinstance(data, dict):
        return
    
    with file_lock:
        # Инвалидируем кэш
        if country in data_cache:
            del data_cache[country]
        if 'all' in data_cache:
            del data_cache['all']
            
        # Сохраняем в файл страны
        country_file = f"listings_{country}.json"
        try:
            with open(country_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Error saving country file {country_file}: {e}")
        
        # Синхронизируем с общим файлом listings_data.json
        try:
            # Load current all_data without using load_all_data to avoid recursion or stale cache
            all_data = {}
            if os.path.exists(DATA_FILE):
                with open(DATA_FILE, 'r', encoding='utf-8') as f:
                    all_data = json.load(f)
            
            all_data[country] = data
            with open(DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(all_data, f, ensure_ascii=False, indent=2)
            
            # Update cache
            data_cache['all'] = {'data': all_data, 'time': time.time()}
            data_cache[country] = {'data': data, 'time': time.time()}
        except Exception as e:
            print(f"Error syncing with listings_data.json: {e}")

@app.errorhandler(500)
def handle_500(e):
    return jsonify({'error': 'Internal Server Error', 'message': str(e)}), 500

@app.errorhandler(404)
def handle_404(e):
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Not Found', 'message': 'API route not found'}), 404
    return render_template('dashboard.html')

@app.route('/')
def index():
    return render_template('dashboard.html')

@app.route('/api/translate', methods=['POST'])
def translate_text():
    if not GOOGLE_AI_API_KEY:
        return jsonify({'error': 'API key not configured'}), 500
    
    data = request.get_json()
    texts = data.get('texts', [])
    target_lang = data.get('lang', 'en')
    
    if not texts:
        return jsonify({'translations': []})
    
    lang_names = {'en': 'English', 'vi': 'Vietnamese', 'ru': 'Russian'}
    target_name = lang_names.get(target_lang, 'English')
    
    results = []
    texts_to_translate = []
    cache_keys = []
    
    for text in texts[:50]:
        cache_key = hashlib.md5(f"{text}:{target_lang}".encode()).hexdigest()
        if cache_key in translation_cache:
            results.append(translation_cache[cache_key])
        else:
            results.append(None)
            texts_to_translate.append(text)
            cache_keys.append(cache_key)
    
    if texts_to_translate:
        try:
            combined_text = "\n---SEPARATOR---\n".join(texts_to_translate)
            prompt = f"Translate the following Russian text(s) to {target_name}. Keep the same format, preserve emojis and special characters. If there are multiple texts separated by ---SEPARATOR---, keep the separator in output. Only output translations, no explanations:\n\n{combined_text}"
            
            api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GOOGLE_AI_API_KEY}"
            response = requests.post(api_url, json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0.3, "maxOutputTokens": 8000}
            }, timeout=30)
            
            if response.status_code == 200:
                result = response.json()
                translated = result.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '')
                translated_parts = translated.split("---SEPARATOR---")
                
                idx = 0
                for i, r in enumerate(results):
                    if r is None and idx < len(translated_parts):
                        clean_text = translated_parts[idx].strip()
                        results[i] = clean_text
                        if idx < len(cache_keys):
                            translation_cache[cache_keys[idx]] = clean_text
                        idx += 1
        except Exception as e:
            print(f"Translation error: {e}")
            for i, r in enumerate(results):
                if r is None:
                    results[i] = texts[i] if i < len(texts) else ""
    
    for i, r in enumerate(results):
        if r is None:
            results[i] = texts[i] if i < len(texts) else ""
    
    return jsonify({'translations': results})

@app.route('/api/ping')
def ping():
    user_id = request.args.get('uid', request.remote_addr)
    online_users[user_id] = time.time()
    now = time.time()
    active = sum(1 for t in online_users.values() if now - t < ONLINE_TIMEOUT)
    return jsonify({'online': active})

@app.route('/api/online')
def get_online():
    now = time.time()
    active = sum(1 for t in online_users.values() if now - t < ONLINE_TIMEOUT)
    return jsonify({'online': active})

weather_cache = {}
WEATHER_CACHE_TTL = 3600

@app.route('/api/weather')
def get_weather():
    city = request.args.get('city', 'Ho Chi Minh')
    cache_key = city.lower()
    now = time.time()
    
    if cache_key in weather_cache:
        cached = weather_cache[cache_key]
        if now - cached['time'] < WEATHER_CACHE_TTL:
            return jsonify({'temp': cached['temp'], 'cached': True})
    
    try:
        response = requests.get(f'https://wttr.in/{city}?format=%t&m', timeout=5, headers={'User-Agent': 'curl/7.68.0'})
        if response.status_code == 200:
            temp = response.text.strip().replace('+', '')
            weather_cache[cache_key] = {'temp': temp, 'time': now}
            return jsonify({'temp': temp, 'cached': False})
    except Exception as e:
        print(f"Weather error: {e}")
    
    if cache_key in weather_cache:
        return jsonify({'temp': weather_cache[cache_key]['temp'], 'cached': True})
    
    return jsonify({'temp': '--°C', 'error': True})

@app.route('/api/telegram-webhook', methods=['POST'])
def telegram_webhook():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'ok': True})
        
        message = data.get('message', {})
        text = message.get('text', '')
        chat_id = message.get('chat', {}).get('id')
        
        if chat_id and text:
            if text == '/start':
                webapp_url = f"https://{os.environ.get('REPLIT_DEV_DOMAIN', 'dea72e19-5d41-40be-9b77-95eb5ddef5a0-00-8g466fi5xkhi.spock.replit.dev')}"
                keyboard = {
                    "inline_keyboard": [
                        [{"text": "🚀 Открыть мини приложение", "web_app": {"url": webapp_url}}],
                        [{"text": "🇹🇭 Тайланд", "callback_data": "country_thailand"}, 
                         {"text": "🇻🇳 Вьетнам", "callback_data": "country_vietnam"}],
                        [{"text": "🇮🇳 Индия", "callback_data": "country_india"}, 
                         {"text": "🇮🇩 Индонезия", "callback_data": "country_indonesia"}]
                    ]
                }
                send_telegram_message(chat_id, WELCOME_MESSAGE, keyboard)
            elif text == '/help':
                help_text = """<b>Команды бота:</b>

/start - Приветствие и информация о портале
/help - Список команд
/contact - Контакты для связи
/categories - Список категорий"""
                send_telegram_message(chat_id, help_text)
            elif text == '/contact':
                contact_text = """<b>Контакты GoldAntelope ASIA:</b>

✈️ Telegram: @radimiralubvi

Мы всегда рады помочь!"""
                send_telegram_message(chat_id, contact_text)
            elif text == '/categories':
                categories_text = """<b>Категории объявлений:</b>

🏠 Недвижимость
🍽️ Рестораны
🧳 Экскурсии
🏍️ Транспорт
👶 Дети
💱 Обмен валют
🛍️ Барахолка
🏥 Медицина
📰 Новости
💬 Чат"""
                send_telegram_message(chat_id, categories_text)
        
        return jsonify({'ok': True})
    except Exception as e:
        print(f"Webhook error: {e}")
        return jsonify({'ok': True})

@app.route('/api/set-telegram-webhook')
def set_telegram_webhook():
    if not TELEGRAM_BOT_TOKEN:
        return jsonify({'error': 'Bot token not configured'})
    
    domain = os.environ.get('REPLIT_DEV_DOMAIN', '')
    if not domain:
        return jsonify({'error': 'Domain not found'})
    
    webhook_url = f"https://{domain}/api/telegram-webhook"
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/setWebhook"
    
    try:
        response = requests.post(url, data={"url": webhook_url}, timeout=10)
        return jsonify(response.json())
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/api/groups-stats')
def groups_stats():
    """Статистика по группам: охват, онлайн, объявления"""
    country = request.args.get('country', 'thailand')
    data = load_data(country)

    
    # Подсчет объявлений по категориям
    listings_count = {}
    for cat, items in data.items():
        if cat != 'chat':
            listings_count[cat] = len(items)
    
    # Загружаем статистику групп для конкретной страны
    stats_file = f'groups_stats_{country}.json'
    groups = []
    updated = None
    
    # ЗАЩИТА: Не загружаем статистику если файл не существует или пуст для этой страны
    if os.path.exists(stats_file):
        with open(stats_file, 'r', encoding='utf-8') as f:
            stats_data = json.load(f)
            groups = stats_data.get('groups', [])
            updated = stats_data.get('updated')
            
            # Если для этой страны нет данных, НЕ показываем данные от других стран
            if not groups and country != 'thailand':
                # Возвращаем пустой результат вместо fallback на другую страну
                return jsonify({
                    'updated': datetime.now().isoformat(),
                    'categories': {},
                    'groups': [],
                    'total_participants': 0,
                    'total_online': 0,
                    'message': f'Статистика по {country} еще собирается...'
                })
    
    # Агрегируем по категориям
    category_stats = {}
    for g in groups:
        cat = g.get('category', 'Другое')
        if cat not in category_stats:
            category_stats[cat] = {'participants': 0, 'online': 0, 'groups': 0, 'listings': 0}
        category_stats[cat]['participants'] += g.get('participants', 0)
        category_stats[cat]['online'] += g.get('online', 0)
        category_stats[cat]['groups'] += 1
    
    # Добавляем количество объявлений
    cat_key_map = {
        'Недвижимость': 'real_estate',
        'Чат': 'chat',
        'Рестораны': 'restaurants',
        'Дети': 'entertainment',
        'Барахолка': 'marketplace',
        'Новости': 'news',
        'Визаран': 'visas',
        'Экскурсии': 'tours',
        'Обмен денег': 'money_exchange',
        'Транспорт': 'transport',
        'Медицина': 'medicine'
    }
    
    for cat_name, cat_key in cat_key_map.items():
        if cat_name in category_stats:
            category_stats[cat_name]['listings'] = listings_count.get(cat_key, 0)
    
    return jsonify({
        'updated': updated,
        'categories': category_stats,
        'groups': groups,
        'total_participants': sum(g.get('participants', 0) for g in groups),
        'total_online': sum(g.get('online', 0) for g in groups)
    })

def load_ads_channels(country):
    """Загрузить рекламные каналы"""
    filename = f'ads_channels_{country}.json'
    if os.path.exists(filename):
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {'channels': []}

def save_ads_channels(country, data):
    """Сохранить рекламные каналы"""
    filename = f'ads_channels_{country}.json'
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

@app.route('/api/ads-channels')
def get_ads_channels():
    """Получить список одобренных рекламных каналов"""
    country = request.args.get('country', 'vietnam')
    show_pending = request.args.get('pending', '') == '1'
    city_filter = request.args.get('city', '')
    data = load_ads_channels(country)
    
    if show_pending:
        # Для админа - показать ожидающие модерации
        pending = [ch for ch in data.get('channels', []) if not ch.get('approved', False)]
        return jsonify({'channels': pending})
    else:
        # Для пользователей - только одобренные
        approved = [ch for ch in data.get('channels', []) if ch.get('approved', False)]
        # Фильтр по городу
        if city_filter:
            approved = [ch for ch in approved if ch.get('city', '') == city_filter]
        return jsonify({'channels': approved})

@app.route('/api/ads-channels/add', methods=['POST'])
def add_ads_channel():
    """Добавить канал для рекламы"""
    try:
        req = request.json
        country = req.get('country', 'vietnam')
        name = req.get('name', '').strip()
        category = req.get('category', 'chat')
        members = int(req.get('members', 0))
        price = int(req.get('price', 30))
        contact = req.get('contact', '').strip()
        
        if not name or not contact:
            return jsonify({'success': False, 'error': 'Укажите название и контакт'})
        
        data = load_ads_channels(country)
        
        # Проверяем дубликаты
        for ch in data['channels']:
            if ch['name'].lower() == name.lower():
                return jsonify({'success': False, 'error': 'Канал уже добавлен'})
        
        city = req.get('city', '').strip()
        
        new_channel = {
            'id': f'ad_{int(time.time())}',
            'name': name,
            'category': category,
            'city': city,
            'members': members,
            'price': price,
            'contact': contact,
            'added': datetime.now().isoformat(),
            'approved': False
        }
        
        data['channels'].append(new_channel)
        save_ads_channels(country, data)
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/admin/ads-channels/approve', methods=['POST'])
def approve_ads_channel():
    """Одобрить или отклонить канал"""
    try:
        req = request.json
        admin_key = req.get('password', '')
        expected_key = os.environ.get('ADMIN_KEY', 'goldantelope2025')
        
        if admin_key != expected_key:
            return jsonify({'success': False, 'error': 'Неверный пароль'})
        
        country = req.get('country', 'vietnam')
        channel_id = req.get('channel_id', '')
        action = req.get('action', 'approve')  # approve или reject
        
        data = load_ads_channels(country)
        
        if action == 'reject':
            # Удаляем канал
            data['channels'] = [ch for ch in data['channels'] if ch['id'] != channel_id]
            save_ads_channels(country, data)
            return jsonify({'success': True, 'message': 'Канал отклонён'})
        else:
            # Одобряем канал
            for ch in data['channels']:
                if ch['id'] == channel_id:
                    ch['approved'] = True
                    save_ads_channels(country, data)
                    return jsonify({'success': True, 'message': 'Канал одобрен'})
            
            return jsonify({'success': False, 'error': 'Канал не найден'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/admin/ads-channels/delete', methods=['POST'])
def delete_ads_channel():
    """Удалить рекламный канал"""
    try:
        req = request.json
        admin_key = req.get('password', '')
        expected_key = os.environ.get('ADMIN_KEY', 'goldantelope2025')
        
        if admin_key != expected_key:
            return jsonify({'success': False, 'error': 'Неверный пароль'})
        
        country = req.get('country', 'vietnam')
        channel_id = req.get('channel_id', '')
        
        data = load_ads_channels(country)
        original_count = len(data['channels'])
        data['channels'] = [ch for ch in data['channels'] if ch['id'] != channel_id]
        
        if len(data['channels']) < original_count:
            save_ads_channels(country, data)
            return jsonify({'success': True, 'message': 'Канал удалён'})
        else:
            return jsonify({'success': False, 'error': 'Канал не найден'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/admin/ads-channels/edit', methods=['POST'])
def edit_ads_channel():
    """Редактировать рекламный канал"""
    try:
        req = request.json
        admin_key = req.get('password', '')
        expected_key = os.environ.get('ADMIN_KEY', 'goldantelope2025')
        
        if admin_key != expected_key:
            return jsonify({'success': False, 'error': 'Неверный пароль'})
        
        country = req.get('country', 'vietnam')
        channel_id = req.get('channel_id', '')
        new_data = req.get('data', {})
        
        data = load_ads_channels(country)
        
        for ch in data['channels']:
            if ch['id'] == channel_id:
                if 'name' in new_data:
                    ch['name'] = new_data['name']
                if 'category' in new_data:
                    ch['category'] = new_data['category']
                if 'members' in new_data:
                    ch['members'] = int(new_data['members'])
                if 'price' in new_data:
                    ch['price'] = float(new_data['price'])
                if 'contact' in new_data:
                    ch['contact'] = new_data['contact']
                if 'city' in new_data:
                    ch['city'] = new_data['city']
                
                save_ads_channels(country, data)
                return jsonify({'success': True, 'message': 'Канал обновлён'})
        
        return jsonify({'success': False, 'error': 'Канал не найден'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/status')
def status():
    country = request.args.get('country', 'vietnam')
    data = load_data(country)

    total_items = sum(len(v) for v in data.values())
    total_listings = sum(len(v) for k, v in data.items() if k != 'chat')
    
    # Количество людей на портале по странам
    online_counts = {
        'vietnam': 342,
        'thailand': 287,
        'india': 156,
        'indonesia': 419
    }
    
    return jsonify({
        'parser_status': 'connected',
        'total_items': total_items,
        'total_listings': total_listings,
        'categories': {k: len(v) for k, v in data.items()},
        'last_update': datetime.now().isoformat(),
        'channels_active': 0,
        'country': country,
        'online_count': online_counts.get(country, 100)
    })

@app.route('/api/city-counts/<category>')
def get_city_counts(category):
    country = request.args.get('country', 'vietnam')
    data = load_data(country)

    
    category_aliases = {
        'exchange': 'money_exchange',
        'money_exchange': 'money_exchange',
        'bikes': 'transport',
        'realestate': 'real_estate'
    }
    category = category_aliases.get(category, category)
    
    if category not in data:
        return jsonify({})
    
    listings = data[category]
    listings = [x for x in listings if not x.get('hidden', False)]
    
    # Расширенный маппинг всех вариантов названий городов
    city_name_mapping = {
        # Нячанг
        'Nha Trang': 'Нячанг', 'nha trang': 'Нячанг', 'nhatrang': 'Нячанг', 'nha_trang': 'Нячанг', 'Нячанг': 'Нячанг', 'нячанг': 'Нячанг',
        # Хошимин
        'Saigon': 'Хошимин', 'Ho Chi Minh': 'Хошимин', 'saigon': 'Хошимин', 'hcm': 'Хошимин', 'ho_chi_minh': 'Хошимин', 'Хошимин': 'Хошимин', 'хошимин': 'Хошимин', 'Сайгон': 'Хошимин', 'сайгон': 'Хошимин', 'HCM': 'Хошимин', 'Ho chi minh': 'Хошимин',
        # Дананг
        'Da Nang': 'Дананг', 'danang': 'Дананг', 'da_nang': 'Дананг', 'Danang': 'Дананг', 'Дананг': 'Дананг', 'дананг': 'Дананг', 'Da nang': 'Дананг',
        # Ханой
        'Hanoi': 'Ханой', 'hanoi': 'Ханой', 'Ha Noi': 'Ханой', 'ha_noi': 'Ханой', 'Ханой': 'Ханой', 'ханой': 'Ханой',
        # Фукуок
        'Phu Quoc': 'Фукуок', 'phuquoc': 'Фукуок', 'phu_quoc': 'Фукуок', 'Phuquoc': 'Фукуок', 'Фукуок': 'Фукуок', 'фукуок': 'Фукуок', 'Phu quoc': 'Фукуок',
        # Фантьет
        'Phan Thiet': 'Фантьет', 'phanthiet': 'Фантьет', 'phan_thiet': 'Фантьет', 'Phanthiet': 'Фантьет', 'Фантьет': 'Фантьет', 'фантьет': 'Фантьет',
        # Муйне
        'Mui Ne': 'Муйне', 'muine': 'Муйне', 'mui_ne': 'Муйне', 'Muine': 'Муйне', 'Муйне': 'Муйне', 'муйне': 'Муйне',
        # Камрань
        'Cam Ranh': 'Камрань', 'camranh': 'Камрань', 'cam_ranh': 'Камрань', 'Camranh': 'Камрань', 'Камрань': 'Камрань', 'камрань': 'Камрань',
        # Далат
        'Da Lat': 'Далат', 'dalat': 'Далат', 'da_lat': 'Далат', 'Dalat': 'Далат', 'Далат': 'Далат', 'далат': 'Далат',
        # Хойан
        'Hoi An': 'Хойан', 'hoian': 'Хойан', 'hoi_an': 'Хойан', 'Hoian': 'Хойан', 'Хойан': 'Хойан', 'хойан': 'Хойан'
    }
    
    # Ключевые слова для поиска в тексте
    city_keywords = {
        'Нячанг': ['нячанг', 'nha trang', 'nhatrang', 'nha_trang'],
        'Хошимин': ['хошимин', 'сайгон', 'saigon', 'ho chi minh', 'hcm', 'ho_chi_minh'],
        'Дананг': ['дананг', 'da nang', 'danang', 'da_nang'],
        'Ханой': ['ханой', 'hanoi', 'ha_noi'],
        'Фукуок': ['фукуок', 'phu quoc', 'phuquoc', 'phu_quoc'],
        'Фантьет': ['фантьет', 'phan thiet', 'phanthiet', 'phan_thiet'],
        'Муйне': ['муйне', 'mui ne', 'muine', 'mui_ne'],
        'Камрань': ['камрань', 'cam ranh', 'camranh', 'cam_ranh'],
        'Далат': ['далат', 'da lat', 'dalat', 'da_lat'],
        'Хойан': ['хойан', 'hoi an', 'hoian', 'hoi_an']
    }
    
    cities = ['Нячанг', 'Хошимин', 'Ханой', 'Фукуок', 'Фантьет', 'Муйне', 'Дананг', 'Камрань', 'Далат', 'Хойан']
    counts = {city: 0 for city in cities}
    
    for item in listings:
        item_city = str(item.get('city', '') or item.get('location', '')).lower()
        search_text = f"{item.get('title', '')} {item.get('description', '')} {item_city}".lower()
        
        # Ищем совпадение в тексте для ВСЕХ городов (объявление может относиться к нескольким городам)
        for city_name, keywords in city_keywords.items():
            if any(kw in search_text or kw in item_city for kw in keywords):
                counts[city_name] += 1
                # НЕ используем break - считаем для всех упомянутых городов
    
    return jsonify(counts)

@app.route('/api/medicine-type-counts')
def get_medicine_type_counts():
    country = request.args.get('country', 'vietnam')
    data = load_data(country)
    
    if 'medicine' not in data:
        return jsonify({})
    
    listings = data['medicine']
    listings = [x for x in listings if not x.get('hidden', False)]
    
    type_mapping = {
        'pharmacy': 'questions',
        'doctor': 'doctors', 
        'massage': 'clinics',
        'insurance': 'insurance',
        'directions': 'directions',
        'clinic': 'clinics',
        'hospital': 'clinics',
        'questions': 'questions',
        'clinics': 'clinics',
        'doctors': 'doctors',
        'dentist': 'directions',
        'lab': 'directions',
        'therapy': 'directions',
        'вопросы': 'questions',
        'клиники': 'clinics',
        'врачи': 'doctors',
        'страховка': 'insurance',
        'направления': 'directions'
    }
    
    counts = {'questions': 0, 'clinics': 0, 'doctors': 0, 'insurance': 0, 'directions': 0}
    
    for item in listings:
        med_type = str(item.get('medicine_type', '')).lower()
        mapped_type = type_mapping.get(med_type, 'questions')
        counts[mapped_type] = counts.get(mapped_type, 0) + 1
    
    return jsonify(counts)

@app.route('/api/kids-type-counts')
def get_kids_type_counts():
    country = request.args.get('country', 'vietnam')
    data = load_data(country)
    
    if 'kids' not in data:
        return jsonify({})
    
    listings = data['kids']
    listings = [x for x in listings if not x.get('hidden', False)]
    
    counts = {'events': 0, 'nannies': 0, 'schools': 0, 'products': 0}
    
    for item in listings:
        kids_type = str(item.get('kids_type', '') or item.get('kids_category', '')).lower().strip()
        if kids_type in counts:
            counts[kids_type] += 1
        else:
            # Маппинг русских названий
            type_map = {
                'школы': 'schools',
                'школа': 'schools',
                'детские сады': 'products',
                'детский сад': 'products',
                'садик': 'products',
                'мероприятия': 'events',
                'мероприятие': 'events',
                'няни': 'nannies',
                'няня': 'nannies',
                'товары': 'products'
            }
            mapped = type_map.get(kids_type, 'schools')
            counts[mapped] = counts.get(mapped, 0) + 1
    
    return jsonify(counts)

@app.route('/api/listings/<category>')
def get_listings(category):
    country = request.args.get('country', 'vietnam')
    data = load_data(country)
    
    # Handle subcategories for Vietnam marketplace and exchange - return listings by default
    # Subcategory info moved to separate endpoint


    
    

    
    
    category_aliases = {
        'exchange': 'money_exchange',
        'money_exchange': 'money_exchange',
        'bikes': 'transport',
        'realestate': 'real_estate',
        'settings': 'kids',
        'stats': 'restaurants'
    }
    
    if category == 'admin':
        all_listings = []
        for cat_name, cat_data in data.items():
            if isinstance(cat_data, list):
                for item in cat_data:
                    item_copy = item.copy()
                    item_copy['_category'] = cat_name
                    all_listings.append(item_copy)
        show_hidden = request.args.get('show_hidden', '0') == '1'
        if not show_hidden:
            all_listings = [x for x in all_listings if not x.get('hidden', False)]
        return jsonify(all_listings)
    
    category = category_aliases.get(category, category)
    
    if category not in data:
        return jsonify([])
    
    listings = data[category]
    
    # Фильтры
    filters = request.args
    
    # Фильтруем скрытые объявления (если не запрошено show_hidden=1)
    # Для Нячанга показываем все объявления включая скрытые
    show_hidden = request.args.get('show_hidden', '0') == '1'
    realestate_city = request.args.get('realestate_city', '')
    if show_hidden or (category == 'real_estate' and realestate_city == 'nhatrang'):
        filtered = listings  # Показываем все включая скрытые
    else:
        filtered = [x for x in listings if not x.get('hidden', False)]
    
    subcategory = request.args.get('subcategory')
    if subcategory:
        # Для marketplace используем поле marketplace_category
        if category == 'marketplace':
            filtered = [x for x in filtered if x.get('marketplace_category') == subcategory]
        else:
            filtered = [x for x in filtered if x.get('subcategory') == subcategory]
    
    # Маппинг русских названий городов на английские
    city_name_mapping = {
        'Нячанг': 'Nha Trang',
        'Хошимин': 'Saigon',
        'Сайгон': 'Saigon',
        'Saigon': 'Saigon',
        'Ho Chi Minh': 'Saigon',
        'Дананг': 'Da Nang',
        'Ханой': 'Hanoi',
        'Фукуок': 'Phu Quoc',
        'Фантьет': 'Phan Thiet',
        'Муйне': 'Mui Ne',
        'Камрань': 'Cam Ranh',
        'Далат': 'Da Lat',
        'Хойан': 'Hoi An'
    }
    
    # Универсальный фильтр по городу для категорий, где он есть (restaurants, tours, entertainment, marketplace, visas)
    if category in ['restaurants', 'tours', 'entertainment', 'marketplace', 'visas']:
        if 'city' in filters and filters['city']:
            city_filter = filters['city']
            
            # Расширенный маппинг с подчёркиваниями и всеми вариантами
            city_keywords_map = {
                'Нячанг': ['нячанг', 'nha trang', 'nhatrang', 'nha_trang'],
                'Хошимин': ['хошимин', 'сайгон', 'saigon', 'ho chi minh', 'hcm', 'ho_chi_minh', 'hochiminh'],
                'Дананг': ['дананг', 'da nang', 'danang', 'da_nang'],
                'Ханой': ['ханой', 'hanoi', 'ha_noi'],
                'Фукуок': ['фукуок', 'phu quoc', 'phuquoc', 'phu_quoc'],
                'Фантьет': ['фантьет', 'phan thiet', 'phanthiet', 'phan_thiet'],
                'Муйне': ['муйне', 'mui ne', 'muine', 'mui_ne'],
                'Камрань': ['камрань', 'cam ranh', 'camranh', 'cam_ranh'],
                'Далат': ['далат', 'da lat', 'dalat', 'da_lat'],
                'Хойан': ['хойан', 'hoi an', 'hoian', 'hoi_an']
            }
            
            targets = city_keywords_map.get(city_filter, [city_filter.lower()])
            
            def matches_city(item):
                item_city = str(item.get('city', '')).lower()
                item_location = str(item.get('location', '')).lower()
                search_text = f"{item.get('title', '')} {item.get('description', '')}".lower()
                
                # Если город не указан, считаем что подходит для всех городов (показываем всё)
                if not item_city and not item_location:
                    return True

                # Проверяем поля city и location
                for t in targets:
                    if t in item_city or t in item_location:
                        return True
                # Проверяем в тексте
                for t in targets:
                    if t in search_text:
                        return True
                return False
            
            filtered = [x for x in filtered if matches_city(x)]
            print(f"DEBUG: Category {category}, City Filter {city_filter}, Targets {targets}, Found {len(filtered)} items")
    
    # Фильтр по типу для категории "kids" (Для детей)
    if category == 'kids':
        if 'kids_type' in filters and filters['kids_type']:
            kids_type = filters['kids_type']
            # Маппинг категорий: products = Детский сад
            type_mapping = {
                'products': 'Детский сад',
                'schools': 'schools',
                'events': 'events',
                'nannies': 'nannies'
            }
            mapped_type = type_mapping.get(kids_type, kids_type)
            
            # Фильтруем только по точному совпадению kids_type
            filtered = [x for x in filtered if x.get('kids_type') == mapped_type or x.get('kids_type') == kids_type]
        
        # Фильтр по городу для kids
        if 'city' in filters and filters['city']:
            city_filter = filters['city'].lower()
            city_mapping = {
                'nha trang': ['nha trang', 'nhatrang', 'нячанг'],
                'da nang': ['da nang', 'danang', 'дананг'],
                'phu quoc': ['phu quoc', 'phuquoc', 'фукуок'],
                'ho chi minh': ['ho chi minh', 'hochiminh', 'hcm', 'хошимин', 'сайгон']
            }
            targets = city_mapping.get(city_filter, [city_filter])
            filtered = [x for x in filtered if any(t in str(x.get('city', '')).lower() for t in targets)]
        
        # Фильтр по возрасту для kids
        if 'max_age' in filters and filters['max_age']:
            try:
                max_age = int(filters['max_age'])
                def check_age(item):
                    age_str = str(item.get('age', ''))
                    # Извлекаем числа из строки возраста
                    numbers = re.findall(r'\d+', age_str)
                    if numbers:
                        # Берём минимальный возраст из диапазона
                        min_item_age = min(int(n) for n in numbers)
                        return min_item_age <= max_age
                    return True  # Если возраст не указан, показываем
                filtered = [x for x in filtered if check_age(x)]
            except ValueError:
                pass
    
    # Фильтры для визарана
    if category == 'visas':
        # Фильтр по направлению (Камбоджа/Лаос) - используем параметр destination
        if 'destination' in filters and filters['destination']:
            dest_filter = filters['destination'].lower()
            # Маппинг русских названий на английские
            dest_mapping = {
                'камбоджа': ['cambodia', 'камбодж', 'кампучия'],
                'лаос': ['laos', 'лаос'],
                'малайзия': ['malaysia', 'малайзия'],
                'непал': ['nepal', 'непал'],
                'шри-ланка': ['sri lanka', 'srilanka', 'шри-ланка', 'шриланка'],
                'сингапур': ['singapore', 'сингапур']
            }
            targets = dest_mapping.get(dest_filter, [dest_filter])
            filtered = [x for x in filtered if 
                any(t in str(x.get('destination', '')).lower() for t in targets) or
                any(t in str(x.get('title', '')).lower() for t in targets) or
                any(t in str(x.get('description', '')).lower() for t in targets)]
        
        # Фильтр по гражданству (россия/казахстан)
        if 'nationality' in filters and filters['nationality']:
            nationality = filters['nationality'].lower()
            citizenship_mapping = {
                'russia': ['российское', 'россия', 'рф', 'russia', 'russian'],
                'kazakhstan': ['казахское', 'казахстан', 'kz', 'kazakhstan'],
                'belarus': ['белорусское', 'беларусь', 'беларуси', 'belarus', 'belarusian'],
                'ukraine': ['украинское', 'украина', 'украины', 'ukraine', 'ukrainian']
            }
            nationality_keywords = {
                'russia': ['росси', 'россиян', 'рф', 'russia', 'russian', 'для русских', 'для рф', 'российск'],
                'kazakhstan': ['казах', 'казакстан', 'kz', 'kazakhstan', 'для казахов', 'кз', 'казахск'],
                'belarus': ['белорус', 'беларус', 'belarus', 'belarusian', 'для белорусов', 'рб'],
                'ukraine': ['украин', 'ukraine', 'ukrainian', 'для украинцев', 'ua']
            }
            citizenship_values = citizenship_mapping.get(nationality, [])
            keywords = nationality_keywords.get(nationality, [])
            
            def matches_nationality(item):
                citizen = item.get('citizenship', '').lower()
                if citizen and citizen in citizenship_values:
                    return True
                text = (item.get('description', '') + ' ' + item.get('title', '')).lower()
                return any(kw in text for kw in keywords)
            
            filtered = [x for x in filtered if matches_nationality(x)]
        
        # Фильтр по сроку (45 / 90 дней)
        if 'days' in filters and filters['days']:
            days = filters['days']
            filtered = [x for x in filtered if days in (x.get('description', '') + ' ' + x.get('title', ''))]

    # Фильтры для фотосессии (news)
    if category == 'news':
        if 'city' in filters and filters['city']:
            city_filter = filters['city'].lower()
            filtered = [x for x in filtered if city_filter in str(x.get('city', '')).lower() or city_filter in str(x.get('title', '')).lower() or city_filter in str(x.get('description', '')).lower()]

    # Фильтры для обмена денег
    if category == 'money_exchange':
        if 'city' in filters and filters['city']:
            city_filter = filters['city']
            city_keywords_map = {
                'Нячанг': ['нячанг', 'nha trang', 'nhatrang', 'nha_trang'],
                'Хошимин': ['хошимин', 'сайгон', 'saigon', 'ho chi minh', 'hcm', 'ho_chi_minh'],
                'Дананг': ['дананг', 'da nang', 'danang', 'da_nang'],
                'Фукуок': ['фукуок', 'phu quoc', 'phuquoc', 'phu_quoc'],
            }
            targets = city_keywords_map.get(city_filter, [city_filter.lower()])
            
            def matches_city(item):
                search_text = f"{item.get('city', '')} {item.get('title', '')} {item.get('description', '')} {item.get('address', '')}".lower()
                return any(t in search_text for t in targets)
            
            filtered = [x for x in filtered if matches_city(x)]

    # Фильтры для медицины
    if category == 'medicine':
        if 'city' in filters and filters['city']:
            city_filter = filters['city'].lower()
            filtered = [x for x in filtered if city_filter in str(x.get('city', '')).lower() or city_filter in str(x.get('title', '')).lower() or city_filter in str(x.get('description', '')).lower()]
        
        # Фильтр по типу медицины (questions, clinics, doctors, insurance, directions)
        if 'medicine_type' in filters and filters['medicine_type']:
            medicine_type = filters['medicine_type']
            # Маппинг типов кнопок на реальные значения в данных
            type_values_map = {
                'questions': ['questions', 'pharmacy'],
                'clinics': ['clinics', 'clinic', 'hospital', 'massage'],
                'doctors': ['doctors', 'doctor'],
                'insurance': ['insurance'],
                'directions': ['directions', 'dentist', 'lab', 'therapy']
            }
            type_keywords = {
                'questions': ['вопрос', 'помоги', 'подскаж', 'где найти', 'посоветуй', 'кто знает', '?'],
                'clinics': ['клиник', 'госпиталь', 'больниц', 'hospital', 'clinic', 'медцентр'],
                'doctors': ['врач', 'доктор', 'doctor', 'терапевт', 'стоматолог', 'специалист', 'медик'],
                'insurance': ['страхов', 'insurance', 'полис', 'policy'],
                'directions': ['направлен', 'специализац', 'услуг', 'обследован', 'анализ', 'аптек', 'массаж', 'pharmacy', 'massage']
            }
            allowed_values = type_values_map.get(medicine_type, [medicine_type])
            keywords = type_keywords.get(medicine_type, [])
            
            def matches_medicine_type(item):
                item_type = item.get('medicine_type', '').lower()
                if item_type in allowed_values:
                    return True
                if keywords:
                    text = (item.get('description', '') + ' ' + item.get('title', '')).lower()
                    return any(kw in text for kw in keywords)
                return False
            
            filtered = [x for x in filtered if matches_medicine_type(x)]

    if category == 'transport':
        # Фильтр по типу транспорта (bikes, cars, yachts, bicycles)
        if 'transport_type' in filters and filters['transport_type']:
            transport_type = filters['transport_type']
            filtered = [x for x in filtered if x.get('transport_type') == transport_type]
        
        # Фильтр по городу для transport
        if 'city' in filters and filters['city']:
            city_filter = filters['city']
            
            # Расширенный маппинг с русскими ключами
            city_keywords_map = {
                'Нячанг': ['нячанг', 'nha trang', 'nhatrang', 'nha_trang'],
                'Хошимин': ['хошимин', 'сайгон', 'saigon', 'ho chi minh', 'hcm', 'ho_chi_minh', 'hochiminh'],
                'Дананг': ['дананг', 'da nang', 'danang', 'da_nang'],
                'Ханой': ['ханой', 'hanoi', 'ha_noi'],
                'Фукуок': ['фукуок', 'phu quoc', 'phuquoc', 'phu_quoc'],
                'Фантьет': ['фантьет', 'phan thiet', 'phanthiet', 'phan_thiet'],
                'Муйне': ['муйне', 'mui ne', 'muine', 'mui_ne'],
                'Камрань': ['камрань', 'cam ranh', 'camranh', 'cam_ranh'],
                'Далат': ['далат', 'da lat', 'dalat', 'da_lat'],
                'Хойан': ['хойан', 'hoi an', 'hoian', 'hoi_an']
            }
            
            targets = city_keywords_map.get(city_filter, [city_filter.lower()])
            
            def matches_city(item):
                item_city = str(item.get('city', '')).lower()
                item_location = str(item.get('location', '')).lower()
                search_text = f"{item.get('title', '')} {item.get('description', '')}".lower()
                
                for t in targets:
                    if t in item_city or t in item_location or t in search_text:
                        return True
                return False
            
            filtered = [x for x in filtered if matches_city(x)]
        
        # Фильтр по типу (sale, rent)
        if 'type' in filters and filters['type']:
            type_filter = filters['type'].lower()
            if type_filter == 'sale':
                keywords = ['продаж', 'куплю', 'продам', 'цена', '$', '₫', 'доллар']
                filtered = [x for x in filtered if any(kw in x.get('description', '').lower() for kw in keywords)]
            elif type_filter == 'rent':
                keywords = ['аренд', 'сдам', 'сдаю', 'наём', 'прокат', 'почасово']
                filtered = [x for x in filtered if any(kw in x.get('description', '').lower() for kw in keywords)]
        
        if 'model' in filters and filters['model']:
            filtered = [x for x in filtered if filters['model'].lower() in (x.get('model') or '').lower()]
        if 'year' in filters and filters['year']:
            filtered = [x for x in filtered if str(x.get('year', '')) == filters['year']]
        if 'price_min' in filters and 'price_max' in filters and filters['price_min'] and filters['price_max']:
            try:
                min_p, max_p = float(filters['price_min']), float(filters['price_max'])
                filtered = [x for x in filtered if min_p <= x.get('price', 0) <= max_p]
            except:
                pass
    
    elif category == 'real_estate':
        if 'realestate_city' in filters and filters['realestate_city']:
            city_filter = filters['realestate_city'].lower()
            city_mapping = {
                'nhatrang': ['nhatrang', 'nha trang', 'нячанг'],
                'danang': ['danang', 'da nang', 'дананг'],
                'hochiminh': ['hochiminh', 'ho chi minh', 'hcm', 'хошимин', 'сайгон'],
                'hanoi': ['hanoi', 'ha noi', 'ханой'],
                'phuquoc': ['phuquoc', 'phu quoc', 'фукуок'],
                'dalat': ['dalat', 'da lat', 'далат']
            }
            targets = city_mapping.get(city_filter, [city_filter])
            filtered = [x for x in filtered if any(t in str(x.get('city', '')).lower() or t in str(x.get('city_ru', '')).lower() for t in targets)]
        
        if 'listing_type' in filters and filters['listing_type']:
            type_filter = filters['listing_type']
            filtered = [x for x in filtered if type_filter in (x.get('listing_type') or '')]
        
        if 'source_group' in filters and filters['source_group']:
            group_filter = filters['source_group']
            filtered = [x for x in filtered if x.get('source_group') == group_filter or x.get('contact_name') == group_filter or group_filter in ' '.join(x.get('photos', [])) or group_filter in (x.get('photo_url') or '')]
        
        def get_price_int(item):
            # Сначала пробуем поле price
            price = item.get('price')
            if price is not None:
                if isinstance(price, (int, float)) and price > 0:
                    return int(price)
                try:
                    price_str = str(price).lower()
                    multiplier = 1
                    if 'млн' in price_str or 'mln' in price_str or 'миллион' in price_str:
                        multiplier = 1000000
                    price_str = price_str.replace(',', '.')
                    cleaned = re.sub(r'[^\d.]', '', price_str)
                    parts = cleaned.split('.')
                    if len(parts) > 2:
                        cleaned = parts[0] + '.' + ''.join(parts[1:])
                    if cleaned:
                        val = int(float(cleaned) * multiplier)
                        if val > 0:
                            return val
                except:
                    pass
            
            # Если поле price пустое или 0, извлекаем из описания
            desc = (item.get('description') or '').lower()
            
            # Ищем паттерны: "7,5 миллион", "7.5 млн", "Цена: 7 500 000"
            patterns = [
                r'(\d+[,.]?\d*)\s*(?:миллион|млн|mln)',  # 7,5 миллион
                r'цена[:\s]*(\d[\d\s]*)\s*(?:vnd|донг|₫)?',  # Цена: 7 500 000
                r'(\d[\d\s]{2,})\s*(?:vnd|донг|₫)',  # 7 500 000 VND
            ]
            
            for pattern in patterns:
                match = re.search(pattern, desc)
                if match:
                    price_str = match.group(1).replace(' ', '').replace(',', '.')
                    try:
                        val = float(price_str)
                        # Если число маленькое и паттерн с млн/миллион
                        if val < 1000 and 'млн' in pattern or 'миллион' in pattern:
                            val = val * 1000000
                        elif val < 100:
                            val = val * 1000000
                        return int(val)
                    except:
                        pass
            
            return 0

        # Price filtering
        if 'price_max' in filters and filters['price_max']:
            try:
                max_p = int(filters['price_max'])
                filtered = [x for x in filtered if 0 < get_price_int(x) <= max_p]
            except:
                pass
        
        if 'price_min' in filters and filters['price_min']:
            try:
                min_p = int(filters['price_min'])
                filtered = [x for x in filtered if get_price_int(x) >= min_p]
            except:
                pass
        
        sort_type = filters.get('sort')
        if sort_type == 'price_desc':
            filtered.sort(key=get_price_int, reverse=True)
        elif sort_type == 'price_asc':
            # Sort items with price > 0 first, then by price
            filtered.sort(key=lambda x: (get_price_int(x) == 0, get_price_int(x)))
        else:
            filtered.sort(key=lambda x: x.get('date', x.get('added_at', '1970-01-01')) or '1970-01-01', reverse=True)
        
        # Обновляем URL для фото из Telegram
        for item in filtered:
            if item.get('telegram_file_id'):
                fresh_url = get_telegram_photo_url(item['telegram_file_id'])
                if fresh_url:
                    item['image_url'] = fresh_url
        return jsonify(filtered)
    
    # Сортировка по дате - новые сверху
    filtered.sort(key=lambda x: x.get('date', x.get('added_at', '1970-01-01')) or '1970-01-01', reverse=True)
    
    # Обновляем URL для фото из Telegram (генерируем свежие ссылки)
    for item in filtered:
        if item.get('telegram_file_id'):
            fresh_url = get_telegram_photo_url(item['telegram_file_id'])
            if fresh_url:
                item['image_url'] = fresh_url
    
    return jsonify(filtered)

@app.route('/api/add-listing', methods=['POST'])
def add_listing():
    country = request.json.get('country', 'vietnam')
    data = load_data(country)

    listing = request.json
    
    category = listing.get('category')
    if category and category in data:
        listing['added_at'] = datetime.now().isoformat()
        data[category].append(listing)
        save_data(country, data)
        return jsonify({'success': True, 'message': 'Объявление добавлено'})
    
    return jsonify({'error': 'Invalid category'}), 400

import shutil
from werkzeug.utils import secure_filename
import requests

BUNNY_STORAGE_ZONE = os.environ.get('BUNNY_CDN_STORAGE_ZONE', 'storage.bunnycdn.com')
BUNNY_STORAGE_NAME = os.environ.get('BUNNY_CDN_STORAGE_NAME', 'goldantelope')
BUNNY_API_KEY = os.environ.get('BUNNY_CDN_API_KEY', 'c88e0b0b-d63c-4a45-8b3d1819830a-c07a-4ddb')

def upload_to_bunny(local_path, filename):
    url = f"https://{BUNNY_STORAGE_ZONE}/{BUNNY_STORAGE_NAME}/{filename}"
    headers = {
        "AccessKey": BUNNY_API_KEY,
        "Content-Type": "application/octet-stream",
    }
    try:
        with open(local_path, "rb") as f:
            response = requests.put(url, data=f, headers=headers)
            return response.status_code == 201
    except Exception as e:
        print(f"BunnyCDN Upload Error: {e}")
        return False

BANNER_CONFIG_FILE = "banner_config.json"
UPLOAD_FOLDER = 'static/images/banners'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def load_banner_config():
    if os.path.exists(BANNER_CONFIG_FILE):
        with open(BANNER_CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
            # Миграция старого формата в новый (web/mobile)
            migrated = False
            for country in config:
                if isinstance(config[country], list):
                    # Старый формат - мигрируем
                    config[country] = {
                        'web': config[country],
                        'mobile': []
                    }
                    migrated = True
            if migrated:
                save_banner_config(config)
            return config
    return {
        'vietnam': {'web': [], 'mobile': []},
        'thailand': {'web': [], 'mobile': []},
        'india': {'web': [], 'mobile': []},
        'indonesia': {'web': [], 'mobile': []}
    }

def save_banner_config(config):
    with open(BANNER_CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

@app.route('/api/banners')
def get_banners():
    return jsonify(load_banner_config())

@app.route('/api/admin/upload-banner', methods=['POST'])
def admin_upload_banner():
    password = request.form.get('password', '')
    country = request.form.get('country', 'vietnam')
    banner_type = request.form.get('banner_type', 'web')  # web or mobile
    is_valid, admin_country = check_admin_password(password, country)
    if not is_valid:
        return jsonify({'error': 'Unauthorized'}), 401
    if admin_country != 'all' and admin_country != country:
        return jsonify({'error': 'No access to this country'}), 403
    if 'file' not in request.files:
        return jsonify({'error': 'No file'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    
    if file:
        filename = secure_filename(f"{country}_{banner_type}_{int(time.time())}_{file.filename}")
        file_path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(file_path)
        
        # Загружаем в BunnyCDN
        upload_to_bunny(file_path, filename)
        
        url = f'/static/images/banners/{filename}'
        config = load_banner_config()
        if country not in config:
            config[country] = {'web': [], 'mobile': []}
        if banner_type not in config[country]:
            config[country][banner_type] = []
        config[country][banner_type].append(url)
        save_banner_config(config)
        
        return jsonify({'success': True, 'url': url})
    
    return jsonify({'error': 'Unknown error'}), 500

@app.route('/api/admin/delete-banner', methods=['POST'])
def admin_delete_banner():
    password = request.json.get('password', '')
    country = request.json.get('country')
    url = request.json.get('url')
    banner_type = request.json.get('banner_type', 'web')  # web or mobile
    is_valid, admin_country = check_admin_password(password, country)
    if not is_valid:
        return jsonify({'error': 'Unauthorized'}), 401
    if admin_country != 'all' and admin_country != country:
        return jsonify({'error': 'No access to this country'}), 403
    
    config = load_banner_config()
    if country in config and banner_type in config[country] and url in config[country][banner_type]:
        config[country][banner_type].remove(url)
        save_banner_config(config)
        return jsonify({'success': True})
    return jsonify({'error': 'Banner not found'}), 404

@app.route('/api/admin/reorder-banners', methods=['POST'])
def admin_reorder_banners():
    password = request.json.get('password', '')
    country = request.json.get('country')
    urls = request.json.get('urls')
    banner_type = request.json.get('banner_type', 'web')  # web or mobile
    is_valid, admin_country = check_admin_password(password, country)
    if not is_valid:
        return jsonify({'error': 'Unauthorized'}), 401
    if admin_country != 'all' and admin_country != country:
        return jsonify({'error': 'No access to this country'}), 403
    
    config = load_banner_config()
    if country in config:
        if banner_type not in config[country]:
            config[country][banner_type] = []
        config[country][banner_type] = urls
        save_banner_config(config)
        return jsonify({'success': True})
    return jsonify({'error': 'Country not found'}), 404

ADMIN_PASSWORDS = {
    'vietnam': 'BB888888!',
    'thailand': 'OO888888!',
    'india': 'GG666666!',
    'indonesia': 'XX111111!'
}

SUPER_ADMIN_PASSWORD = 'DD888888!'

def check_admin_password(password, country=None):
    """Check if password is valid for the given country or any country"""
    # Супер-админ имеет доступ ко всем странам
    if password == SUPER_ADMIN_PASSWORD:
        return True, 'all'
    
    if country and country in ADMIN_PASSWORDS:
        return password == ADMIN_PASSWORDS[country], country
    for c, pwd in ADMIN_PASSWORDS.items():
        if password == pwd:
            return True, c
    return False, None

@app.route('/api/admin/auth', methods=['POST'])
def admin_auth():
    password = request.json.get('password', '')
    country = request.json.get('country')
    
    is_valid, admin_country = check_admin_password(password, country)
    
    if is_valid:
        return jsonify({'success': True, 'authenticated': True, 'country': admin_country})
    return jsonify({'success': False, 'error': 'Invalid password'}), 401

@app.route('/api/admin/delete-listing', methods=['POST'])
def admin_delete():
    password = request.json.get('password', '')
    country = request.json.get('country', 'vietnam')
    
    is_valid, admin_country = check_admin_password(password, country)
    if not is_valid:
        return jsonify({'error': 'Unauthorized'}), 401
    if admin_country != 'all' and admin_country != country:
        return jsonify({'error': 'No access to this country'}), 403
    category = request.json.get('category')
    listing_id = request.json.get('listing_id')
    
    # Маппинг категорий
    category_map = {'exchange': 'money_exchange', 'realestate': 'real_estate'}
    category = category_map.get(category, category)
    
    data = load_data(country)

    
    if category in data:
        data[category] = [x for x in data[category] if x.get('id') != listing_id]
        save_data(country, data)
        return jsonify({'success': True, 'message': f'Объявление {listing_id} удалено'})
    
    return jsonify({'error': 'Category not found'}), 404

@app.route('/api/admin/move-listing', methods=['POST'])
def admin_move():
    password = request.json.get('password', '')
    country = request.json.get('country', 'vietnam')
    
    is_valid, admin_country = check_admin_password(password, country)
    if not is_valid:
        return jsonify({'error': 'Unauthorized'}), 401
    if admin_country != 'all' and admin_country != country:
        return jsonify({'error': 'No access to this country'}), 403
    from_category = request.json.get('from_category')
    to_category = request.json.get('to_category')
    listing_id = request.json.get('listing_id')
    
    data = load_data(country)

    
    if from_category not in data or to_category not in data:
        return jsonify({'error': 'Invalid category'}), 404
    
    # Найти объявление
    listing = None
    if from_category in data:
        for i, item in enumerate(data[from_category]):
            if item.get('id') == listing_id:
                listing = data[from_category].pop(i)
                break
    
    if not listing:
        return jsonify({'success': False, 'error': 'Listing not found'}), 404
    
    # Обновить категорию и переместить
    listing['category'] = to_category
    if to_category not in data:
        data[to_category] = []
    data[to_category].insert(0, listing)
    save_data(country, data)
    
    return jsonify({'success': True, 'message': f'Объявление перемещено в {to_category}'})

@app.route('/api/admin/toggle-visibility', methods=['POST'])
def admin_toggle_visibility():
    """Скрыть/показать объявление"""
    password = request.json.get('password', '')
    country = request.json.get('country', 'vietnam')
    
    is_valid, admin_country = check_admin_password(password, country)
    if not is_valid:
        return jsonify({'error': 'Unauthorized'}), 401
    if admin_country != 'all' and admin_country != country:
        return jsonify({'error': 'No access to this country'}), 403
    category = request.json.get('category')
    listing_id = request.json.get('listing_id')
    
    # Маппинг категорий (exchange -> money_exchange)
    category_map = {'exchange': 'money_exchange', 'realestate': 'real_estate'}
    category = category_map.get(category, category)
    
    data = load_data(country)

    
    if category not in data:
        return jsonify({'error': 'Category not found'}), 404
    
    for item in data[category]:
        if item.get('id') == listing_id:
            current = item.get('hidden', False)
            item['hidden'] = not current
            save_data(country, data)
            status = 'скрыто' if item['hidden'] else 'видимо'
            return jsonify({'success': True, 'hidden': item['hidden'], 'message': f'Объявление {status}'})
    
    return jsonify({'error': 'Listing not found'}), 404

@app.route('/api/admin/bulk-hide', methods=['POST'])
def admin_bulk_hide():
    """Массовое скрытие объявлений по контакту"""
    password = request.json.get('password', '')
    country = request.json.get('country', 'vietnam')
    
    is_valid, admin_country = check_admin_password(password, country)
    if not is_valid:
        return jsonify({'error': 'Unauthorized'}), 401
    if admin_country != 'all' and admin_country != country:
        return jsonify({'error': 'No access to this country'}), 403
    category = request.json.get('category')
    contact_name = request.json.get('contact_name')
    hide = request.json.get('hide', True)
    
    data = load_data(country)

    count = 0
    
    if category and category in data:
        categories = [category]
    else:
        categories = data.keys()
    
    for cat in categories:
        if cat in data:
            for item in data[cat]:
                cn = (item.get('contact_name') or item.get('contact') or '').lower()
                if contact_name.lower() in cn:
                    item['hidden'] = hide
                    count += 1
    
    save_data(country, data)
    action = 'скрыто' if hide else 'показано'
    return jsonify({'success': True, 'count': count, 'message': f'{count} объявлений {action}'})

@app.route('/api/admin/edit-listing', methods=['POST'])
def admin_edit():
    password = request.json.get('password', '')
    country = request.json.get('country', 'vietnam')
    
    is_valid, admin_country = check_admin_password(password, country)
    if not is_valid:
        return jsonify({'error': 'Unauthorized'}), 401
    if admin_country != 'all' and admin_country != country:
        return jsonify({'error': 'No access to this country'}), 403
    category = request.json.get('category')
    listing_id = request.json.get('listing_id')
    updates = request.json.get('updates', {})
    
    # Маппинг категорий (exchange -> money_exchange)
    category_map = {'exchange': 'money_exchange', 'realestate': 'real_estate'}
    category = category_map.get(category, category)
    
    data = load_data(country)

    
    if category not in data:
        return jsonify({'error': 'Category not found'}), 404
    
    for item in data[category]:
        if item.get('id') == listing_id:
            if 'title' in updates:
                item['title'] = updates['title']
            if 'description' in updates:
                item['description'] = updates['description']
            if 'price' in updates:
                try:
                    item['price'] = int(updates['price']) if updates['price'] else 0
                except:
                    item['price'] = 0
            if 'rooms' in updates:
                item['rooms'] = updates['rooms'] if updates['rooms'] else None
            if 'area' in updates:
                try:
                    item['area'] = float(updates['area']) if updates['area'] else None
                except:
                    item['area'] = None
            if 'date' in updates:
                item['date'] = updates['date'] if updates['date'] else None
            if 'whatsapp' in updates:
                item['whatsapp'] = updates['whatsapp'] if updates['whatsapp'] else None
            if 'telegram' in updates:
                item['telegram'] = updates['telegram'] if updates['telegram'] else None
            if 'contact_name' in updates:
                item['contact_name'] = updates['contact_name'] if updates['contact_name'] else None
            if 'listing_type' in updates:
                item['listing_type'] = updates['listing_type'] if updates['listing_type'] else None
            if 'city' in updates:
                item['city'] = updates['city'] if updates['city'] else None
            if 'google_maps' in updates:
                item['google_maps'] = updates['google_maps'] if updates['google_maps'] else None
            if 'google_rating' in updates:
                item['google_rating'] = updates['google_rating'] if updates['google_rating'] else None
            if 'kitchen' in updates:
                item['kitchen'] = updates['kitchen'] if updates['kitchen'] else None
            if 'restaurant_type' in updates:
                item['restaurant_type'] = updates['restaurant_type'] if updates['restaurant_type'] else None
            if 'price_category' in updates:
                item['price_category'] = updates['price_category'] if updates['price_category'] else None
            if 'kids_age' in updates:
                item['kids_age'] = updates['kids_age'] if updates['kids_age'] else None
                item['age'] = updates['kids_age'] if updates['kids_age'] else None
            if 'kids_category' in updates:
                item['kids_category'] = updates['kids_category'] if updates['kids_category'] else None
            if 'kids_type' in updates:
                item['kids_type'] = updates['kids_type'] if updates['kids_type'] else None
            if 'currency_pairs' in updates:
                item['currency_pairs'] = updates['currency_pairs'] if updates['currency_pairs'] else None
            if 'image_url' in updates and updates['image_url']:
                image_url = updates['image_url']
                if image_url.startswith('data:'):
                    try:
                        import base64
                        header, b64_data = image_url.split(',', 1)
                        image_data = base64.b64decode(b64_data)
                        caption = f"📷 {item.get('title', 'Объявление')}"
                        file_id = send_photo_to_channel(image_data, caption)
                        if file_id:
                            item['telegram_file_id'] = file_id
                            item['telegram_photo'] = True
                            fresh_url = get_telegram_photo_url(file_id)
                            if fresh_url:
                                item['image_url'] = fresh_url
                    except Exception as e:
                        print(f"Error uploading new photo: {e}")
                        item['image_url'] = image_url
                else:
                    item['image_url'] = image_url
            
            save_data(country, data)
            return jsonify({'success': True, 'message': 'Объявление обновлено'})
    
    return jsonify({'error': 'Listing not found'}), 404

@app.route('/api/admin/update-listing-with-photo', methods=['POST'])
def admin_update_listing_with_photo():
    password = request.form.get('password', '')
    country = request.form.get('country', 'vietnam')
    
    is_valid, admin_country = check_admin_password(password, country)
    if not is_valid:
        return jsonify({'error': 'Unauthorized'}), 401
    if admin_country != 'all' and admin_country != country:
        return jsonify({'error': 'No access to this country'}), 403
    category = request.form.get('category')
    listing_id = request.form.get('listing_id')
    
    category_map = {'exchange': 'money_exchange', 'realestate': 'real_estate'}
    category = category_map.get(category, category)
    
    data = load_data(country)
    
    if category not in data:
        return jsonify({'error': 'Category not found'}), 404
    
    for item in data[category]:
        if item.get('id') == listing_id:
            if request.form.get('title'):
                item['title'] = request.form.get('title')
            if request.form.get('description'):
                item['description'] = request.form.get('description')
            if request.form.get('city'):
                item['city'] = request.form.get('city')
            if request.form.get('currency_pairs'):
                item['currency_pairs'] = request.form.get('currency_pairs')
            if request.form.get('marketplace_category'):
                item['marketplace_category'] = request.form.get('marketplace_category')
            if request.form.get('destination'):
                item['destination'] = request.form.get('destination')
            if request.form.get('photo_type'):
                item['photo_type'] = request.form.get('photo_type')
            if request.form.get('medicine_type'):
                item['medicine_type'] = request.form.get('medicine_type')
            if request.form.get('kids_age'):
                item['kids_age'] = request.form.get('kids_age')
            if request.form.get('kids_category'):
                item['kids_category'] = request.form.get('kids_category')
            if request.form.get('contact_name'):
                item['contact_name'] = request.form.get('contact_name')
            if request.form.get('whatsapp'):
                item['whatsapp'] = request.form.get('whatsapp')
            if request.form.get('telegram'):
                item['telegram'] = request.form.get('telegram')
            
            # Additional category-specific fields
            if request.form.get('price'):
                item['price'] = request.form.get('price')
            if request.form.get('location'):
                item['location'] = request.form.get('location')
            if request.form.get('days'):
                item['days'] = request.form.get('days')
            if request.form.get('engine'):
                item['engine'] = request.form.get('engine')
            if request.form.get('year'):
                item['year'] = request.form.get('year')
            if request.form.get('transport_type'):
                item['transport_type'] = request.form.get('transport_type')
            if request.form.get('kitchen'):
                item['kitchen'] = request.form.get('kitchen')
            if request.form.get('google_maps'):
                item['google_maps'] = request.form.get('google_maps')
            if request.form.get('google_rating'):
                item['google_rating'] = request.form.get('google_rating')
            if request.form.get('restaurant_type'):
                item['restaurant_type'] = request.form.get('restaurant_type')
            if request.form.get('property_type'):
                item['property_type'] = request.form.get('property_type')
            if request.form.get('rooms'):
                item['rooms'] = request.form.get('rooms')
            if request.form.get('area'):
                item['area'] = request.form.get('area')
            if request.form.get('listing_type'):
                item['listing_type'] = request.form.get('listing_type')
            
            # Handle single photo (backwards compatibility)
            photo = request.files.get('photo')
            if photo and photo.filename:
                try:
                    image_data = photo.read()
                    caption = f"📷 {item.get('title', 'Объявление')}"
                    file_id = send_photo_to_channel(image_data, caption)
                    if file_id:
                        item['telegram_file_id'] = file_id
                        item['telegram_photo'] = True
                        fresh_url = get_telegram_photo_url(file_id)
                        if fresh_url:
                            item['image_url'] = fresh_url
                except Exception as e:
                    print(f"Error uploading photo: {e}")
            
            # Handle 4 photos (photo_0, photo_1, photo_2, photo_3)
            photo_fields = ['image_url', 'image_url_2', 'image_url_3', 'image_url_4']
            for i in range(4):
                photo_file = request.files.get(f'photo_{i}')
                if photo_file and photo_file.filename:
                    try:
                        image_data = photo_file.read()
                        print(f"DEBUG: Processing photo_{i}, size={len(image_data)} bytes")
                        caption = f"📷 {item.get('title', 'Объявление')} - фото {i+1}"
                        file_id = send_photo_to_channel(image_data, caption)
                        print(f"DEBUG: photo_{i} uploaded, file_id={file_id[:50] if file_id else 'None'}...")
                        if file_id:
                            fresh_url = get_telegram_photo_url(file_id)
                            print(f"DEBUG: photo_{i} fresh_url={fresh_url}")
                            if fresh_url:
                                old_url = item.get(photo_fields[i])
                                item[photo_fields[i]] = fresh_url
                                print(f"DEBUG: Updated {photo_fields[i]}: {old_url} -> {fresh_url}")
                                if i == 0:
                                    item['telegram_file_id'] = file_id
                                    item['telegram_photo'] = True
                            else:
                                print(f"DEBUG: fresh_url is empty/None for photo_{i}")
                    except Exception as e:
                        print(f"Error uploading photo_{i}: {e}")
            
            save_data(country, data)
            return jsonify({'success': True, 'message': 'Объявление обновлено'})
    
    return jsonify({'error': 'Listing not found'}), 404

@app.route('/api/admin/get-listing', methods=['POST'])
def admin_get_listing():
    password = request.json.get('password', '')
    country = request.json.get('country', 'vietnam')
    
    is_valid, admin_country = check_admin_password(password, country)
    if not is_valid:
        return jsonify({'error': 'Unauthorized'}), 401
    if admin_country != 'all' and admin_country != country:
        return jsonify({'error': 'No access to this country'}), 403
    category = request.json.get('category')
    listing_id = request.json.get('listing_id')
    
    # Маппинг категорий (exchange -> money_exchange)
    category_map = {'exchange': 'money_exchange', 'realestate': 'real_estate'}
    category = category_map.get(category, category)
    
    data = load_data(country)

    
    if category not in data:
        return jsonify({'error': 'Category not found'}), 404
    
    for item in data[category]:
        if item.get('id') == listing_id:
            return jsonify(item)
    
    return jsonify({'error': 'Listing not found'}), 404

def load_pending_listings(country='vietnam'):
    pending_file = f"pending_{country}.json"
    if os.path.exists(pending_file):
        with open(pending_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_pending_listings(country, listings):
    pending_file = f"pending_{country}.json"
    with open(pending_file, 'w', encoding='utf-8') as f:
        json.dump(listings, f, ensure_ascii=False, indent=2)

@app.route('/api/submit-listing', methods=['POST'])
def submit_listing():
    try:
        captcha_answer = request.form.get('captcha_answer', '')
        captcha_token = request.form.get('captcha_token', '')
        
        if captcha_token:
            expected = captcha_storage.get(captcha_token)
            if not expected or captcha_answer != expected:
                return jsonify({'error': 'Неверная капча'}), 400
            if captcha_token in captcha_storage:
                del captcha_storage[captcha_token]
        
        country = request.form.get('country', 'vietnam')
        category = request.form.get('category', 'other')
        title = request.form.get('title', '')
        description = request.form.get('description', '')
        price = request.form.get('price', '')
        city = request.form.get('city', '')
        whatsapp = request.form.get('whatsapp', '')
        telegram = request.form.get('telegram', '')
        
        rooms = request.form.get('rooms', '')
        area = request.form.get('area', '')
        location = request.form.get('location', '')
        listing_type = request.form.get('listing_type', '')
        contact_name = request.form.get('contact_name', '')
        
        if not title or not description:
            return jsonify({'error': 'Заполните название и описание'}), 400
        
        if not telegram:
            return jsonify({'error': 'Заполните Telegram контакт'}), 400
        
        images = []
        photos = request.files.getlist('photos')
        if photos:
            for i, file in enumerate(photos):
                if file and file.filename:
                    import base64
                    file_data = file.read()
                    if len(file_data) > 1024 * 1024:
                        return jsonify({'error': f'Фото {i+1} превышает 1 МБ'}), 400
                    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else 'jpg'
                    data_url = f"data:image/{ext};base64,{base64.b64encode(file_data).decode()}"
                    images.append(data_url)
        
        if not images:
            for i in range(4):
                file = request.files.get(f'photo_{i}')
                if file and file.filename:
                    import base64
                    file_data = file.read()
                    if len(file_data) > 1024 * 1024:
                        return jsonify({'error': f'Фото {i+1} превышает 1 МБ'}), 400
                    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else 'jpg'
                    data_url = f"data:image/{ext};base64,{base64.b64encode(file_data).decode()}"
                    images.append(data_url)
        
        listing_id = f"pending_{category}_{country}_{int(time.time())}_{len(load_pending_listings(country))}"
        
        new_listing = {
            'id': listing_id,
            'title': title,
            'description': description,
            'price': int(price) if price.isdigit() else price if price else 0,
            'city': city if city else None,
            'whatsapp': whatsapp,
            'telegram': telegram,
            'category': category,
            'image_url': images[0] if images else None,
            'all_images': images if len(images) > 1 else None,
            'date': datetime.now().isoformat(),
            'status': 'pending'
        }
        
        if rooms:
            new_listing['rooms'] = rooms
        if area:
            new_listing['area'] = float(area) if area else None
        if location:
            new_listing['location'] = location
        if listing_type:
            new_listing['listing_type'] = listing_type
        if contact_name:
            new_listing['contact_name'] = contact_name
        
        if category == 'money_exchange':
            new_listing['pairs'] = request.form.get('pairs', '')
            new_listing['address'] = request.form.get('address', '')
        elif category == 'visas':
            new_listing['destination'] = request.form.get('destination', '')
            new_listing['citizenship'] = request.form.get('citizenship', '')
        elif category == 'marketplace':
            new_listing['marketplace_category'] = request.form.get('marketplace_category', '')
        elif category == 'photosession' or category == 'news':
            new_listing['photo_type'] = request.form.get('photo_type', '')
        elif category == 'medicine':
            new_listing['medicine_type'] = request.form.get('medicine_type', '')
        
        pending = load_pending_listings(country)
        pending.append(new_listing)
        save_pending_listings(country, pending)
        
        category_names = {
            'money_exchange': 'Обмен денег',
            'kids': 'Для детей',
            'marketplace': 'Барахолка',
            'visas': 'Визаран',
            'photosession': 'Фотосессия',
            'news': 'Фотосессия',
            'medicine': 'Медицина',
            'real_estate': 'Недвижимость',
            'other': 'Другое'
        }
        cat_name = category_names.get(category, category)
        
        send_telegram_notification(f"<b>Новое объявление ({cat_name})</b>\n\n<b>{title}</b>\n{description[:200]}...\n\nГород: {city}\nЦена: {price}\n\n✈️ Telegram: {telegram}")
        
        return jsonify({'success': True, 'message': 'Объявление отправлено на модерацию'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/submit-restaurant', methods=['POST'])
def submit_restaurant():
    try:
        captcha_answer = request.form.get('captcha_answer', '')
        captcha_token = request.form.get('captcha_token', '')
        
        expected = captcha_storage.get(captcha_token)
        if not expected or captcha_answer != expected:
            return jsonify({'error': 'Неверная капча'}), 400
        
        if captcha_token in captcha_storage:
            del captcha_storage[captcha_token]
        
        country = request.form.get('country', 'vietnam')
        title = request.form.get('title', '')
        description = request.form.get('description', '')
        kitchen = request.form.get('kitchen', '')
        location = request.form.get('location', '')
        city = request.form.get('city', '')
        google_maps = request.form.get('google_maps', '')
        contact_name = request.form.get('contact_name', '')
        whatsapp = request.form.get('whatsapp', '')
        telegram = request.form.get('telegram', '')
        price_category = request.form.get('price_category', 'normal')
        restaurant_type = request.form.get('restaurant_type', 'ресторан')
        
        if not title or not description:
            return jsonify({'error': 'Заполните название и описание'}), 400
        
        images = []
        for i in range(4):
            file = request.files.get(f'photo_{i}')
            if file and file.filename:
                import base64
                file_data = file.read()
                if len(file_data) > 1024 * 1024:
                    return jsonify({'error': f'Фото {i+1} превышает 1 МБ'}), 400
                
                ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else 'jpg'
                data_url = f"data:image/{ext};base64,{base64.b64encode(file_data).decode()}"
                images.append(data_url)
        
        listing_id = f"pending_restaurant_{country}_{int(time.time())}_{len(load_pending_listings(country))}"
        
        new_listing = {
            'id': listing_id,
            'title': title,
            'description': description,
            'kitchen': kitchen if kitchen else None,
            'location': location if location else None,
            'city': city if city else None,
            'google_maps': google_maps if google_maps else None,
            'restaurant_type': restaurant_type if restaurant_type else 'ресторан',
            'contact_name': contact_name,
            'whatsapp': whatsapp,
            'telegram': telegram,
            'price_category': price_category,
            'category': 'restaurants',
            'image_url': images[0] if images else None,
            'all_images': images if len(images) > 1 else None,
            'date': datetime.now().isoformat(),
            'status': 'pending'
        }
        
        pending = load_pending_listings(country)
        pending.append(new_listing)
        save_pending_listings(country, pending)
        
        send_telegram_notification(f"<b>Новый ресторан</b>\n\n<b>{title}</b>\n{description[:200]}...\n\nКухня: {kitchen}\n\n✈️ Написать в Telegram: @radimiralubvi")
        
        return jsonify({'success': True, 'message': 'Ресторан отправлен на модерацию'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/submit-entertainment', methods=['POST'])
def submit_entertainment():
    try:
        captcha_answer = request.form.get('captcha_answer', '')
        captcha_token = request.form.get('captcha_token', '')
        
        expected = captcha_storage.get(captcha_token)
        if not expected or captcha_answer != expected:
            return jsonify({'error': 'Неверная капча'}), 400
        
        if captcha_token in captcha_storage:
            del captcha_storage[captcha_token]
        
        country = request.form.get('country', 'vietnam')
        title = request.form.get('title', '')
        description = request.form.get('description', '')
        feature = request.form.get('feature', '')
        location = request.form.get('location', '')
        city = request.form.get('city', '')
        contact_name = request.form.get('contact_name', '')
        whatsapp = request.form.get('whatsapp', '')
        telegram = request.form.get('telegram', '')
        capacity = request.form.get('capacity', '50')
        
        if not title or not description:
            return jsonify({'error': 'Заполните название и описание'}), 400
        
        images = []
        for i in range(4):
            file = request.files.get(f'photo_{i}')
            if file and file.filename:
                import base64
                file_data = file.read()
                if len(file_data) > 1024 * 1024:
                    return jsonify({'error': f'Фото {i+1} превышает 1 МБ'}), 400
                
                ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else 'jpg'
                data_url = f"data:image/{ext};base64,{base64.b64encode(file_data).decode()}"
                images.append(data_url)
        
        listing_id = f"pending_entertainment_{country}_{int(time.time())}_{len(load_pending_listings(country))}"
        
        new_listing = {
            'id': listing_id,
            'title': title,
            'description': description,
            'feature': feature if feature else None,
            'location': location if location else None,
            'city': city if city else None,
            'contact_name': contact_name,
            'whatsapp': whatsapp,
            'telegram': telegram,
            'capacity': capacity,
            'category': 'entertainment',
            'image_url': images[0] if images else None,
            'all_images': images if len(images) > 1 else None,
            'date': datetime.now().isoformat(),
            'status': 'pending'
        }
        
        pending = load_pending_listings(country)
        pending.append(new_listing)
        save_pending_listings(country, pending)
        
        send_telegram_notification(f"<b>Новое развлечение</b>\n\n<b>{title}</b>\n{description[:200]}...\n\nФишка: {feature}\n\n✈️ Написать в Telegram: @radimiralubvi")
        
        return jsonify({'success': True, 'message': 'Развлечение отправлено на модерацию'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/submit-tour', methods=['POST'])
def submit_tour():
    try:
        captcha_answer = request.form.get('captcha_answer', '')
        captcha_token = request.form.get('captcha_token', '')
        
        expected = captcha_storage.get(captcha_token)
        if not expected or captcha_answer != expected:
            return jsonify({'error': 'Неверная капча'}), 400
        
        if captcha_token in captcha_storage:
            del captcha_storage[captcha_token]
        
        country = request.form.get('country', 'vietnam')
        title = request.form.get('title', '')
        description = request.form.get('description', '')
        days = request.form.get('days', '1')
        price = request.form.get('price', '')
        location = request.form.get('location', '')
        city = request.form.get('city', '')
        contact_name = request.form.get('contact_name', '')
        whatsapp = request.form.get('whatsapp', '')
        telegram = request.form.get('telegram', '')
        group_size = request.form.get('group_size', '5')
        
        if not title or not description:
            return jsonify({'error': 'Заполните название и описание'}), 400
        
        images = []
        for i in range(4):
            file = request.files.get(f'photo_{i}')
            if file and file.filename:
                import base64
                file_data = file.read()
                if len(file_data) > 1024 * 1024:
                    return jsonify({'error': f'Фото {i+1} превышает 1 МБ'}), 400
                
                ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else 'jpg'
                data_url = f"data:image/{ext};base64,{base64.b64encode(file_data).decode()}"
                images.append(data_url)
        
        listing_id = f"pending_tour_{country}_{int(time.time())}_{len(load_pending_listings(country))}"
        
        new_listing = {
            'id': listing_id,
            'title': title,
            'description': description,
            'days': days,
            'price': int(price) if price.isdigit() else 0,
            'location': location if location else None,
            'city': city if city else None,
            'contact_name': contact_name,
            'whatsapp': whatsapp,
            'telegram': telegram,
            'group_size': group_size,
            'category': 'tours',
            'image_url': images[0] if images else None,
            'all_images': images if len(images) > 1 else None,
            'date': datetime.now().isoformat(),
            'status': 'pending'
        }
        
        pending = load_pending_listings(country)
        pending.append(new_listing)
        save_pending_listings(country, pending)
        
        send_telegram_notification(f"<b>Новая экскурсия</b>\n\n<b>{title}</b>\n{description[:200]}...\n\nДней: {days}, Цена: ${price}\n\n✈️ Написать в Telegram: @radimiralubvi")
        
        return jsonify({'success': True, 'message': 'Экскурсия отправлена на модерацию'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/submit-transport', methods=['POST'])
def submit_transport():
    try:
        captcha_answer = request.form.get('captcha_answer', '')
        captcha_token = request.form.get('captcha_token', '')
        
        expected = captcha_storage.get(captcha_token)
        if not expected or captcha_answer != expected:
            return jsonify({'error': 'Неверная капча'}), 400
        
        if captcha_token in captcha_storage:
            del captcha_storage[captcha_token]
        
        country = request.form.get('country', 'vietnam')
        title = request.form.get('title', '')
        description = request.form.get('description', '')
        engine = request.form.get('engine', '')
        year = request.form.get('year', '')
        price = request.form.get('price', '')
        transport_type = request.form.get('transport_type', 'bikes')
        location = request.form.get('location', '')
        city = request.form.get('city', '')
        contact_name = request.form.get('contact_name', '')
        whatsapp = request.form.get('whatsapp', '')
        telegram = request.form.get('telegram', '')
        
        if not title or not description:
            return jsonify({'error': 'Заполните название и описание'}), 400
        
        images = []
        for i in range(4):
            file = request.files.get(f'photo_{i}')
            if file and file.filename:
                import base64
                file_data = file.read()
                if len(file_data) > 1024 * 1024:
                    return jsonify({'error': f'Фото {i+1} превышает 1 МБ'}), 400
                
                ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else 'jpg'
                data_url = f"data:image/{ext};base64,{base64.b64encode(file_data).decode()}"
                images.append(data_url)
        
        listing_id = f"pending_transport_{country}_{int(time.time())}_{len(load_pending_listings(country))}"
        
        new_listing = {
            'id': listing_id,
            'title': title,
            'description': description,
            'engine': engine,
            'year': int(year) if year.isdigit() else None,
            'price': int(price) if price.isdigit() else 0,
            'transport_type': transport_type,
            'location': location if location else None,
            'city': city if city else None,
            'contact_name': contact_name,
            'whatsapp': whatsapp,
            'telegram': telegram,
            'category': 'transport',
            'image_url': images[0] if images else None,
            'all_images': images if len(images) > 1 else None,
            'date': datetime.now().isoformat(),
            'status': 'pending'
        }
        
        pending = load_pending_listings(country)
        pending.append(new_listing)
        save_pending_listings(country, pending)
        
        send_telegram_notification(f"<b>Новый транспорт</b>\n\n<b>{title}</b>\n{description[:200]}...\n\nДвигатель: {engine}cc, Год: {year}, Цена: ${price}\n\n✈️ Написать в Telegram: @radimiralubvi")
        
        return jsonify({'success': True, 'message': 'Транспорт отправлен на модерацию'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/submit-realestate', methods=['POST'])
def submit_realestate():
    try:
        captcha_answer = request.form.get('captcha_answer', '')
        captcha_token = request.form.get('captcha_token', '')
        
        expected = captcha_storage.get(captcha_token)
        if not expected or captcha_answer != expected:
            return jsonify({'error': 'Неверная капча'}), 400
        
        if captcha_token in captcha_storage:
            del captcha_storage[captcha_token]
        
        country = request.form.get('country', 'vietnam')
        title = request.form.get('title', '')
        description = request.form.get('description', '')
        realestate_type = request.form.get('realestate_type', 'apartment')
        rooms = request.form.get('rooms', '')
        area = request.form.get('area', '')
        price = request.form.get('price', '')
        city = request.form.get('city', '')
        location = request.form.get('location', '')
        google_maps = request.form.get('google_maps', '')
        contact_name = request.form.get('contact_name', '')
        whatsapp = request.form.get('whatsapp', '')
        telegram = request.form.get('telegram', '')
        
        if not title or not description:
            return jsonify({'error': 'Заполните название и описание'}), 400
        
        images = []
        for i in range(4):
            file = request.files.get(f'photo_{i}')
            if file and file.filename:
                import base64
                file_data = file.read()
                if len(file_data) > 1024 * 1024:
                    return jsonify({'error': f'Фото {i+1} превышает 1 МБ'}), 400
                
                ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else 'jpg'
                data_url = f"data:image/{ext};base64,{base64.b64encode(file_data).decode()}"
                images.append(data_url)
        
        listing_id = f"pending_realestate_{country}_{int(time.time())}_{len(load_pending_listings(country))}"
        
        new_listing = {
            'id': listing_id,
            'title': title,
            'description': description,
            'realestate_type': realestate_type,
            'rooms': rooms,
            'area': int(area) if area and area.isdigit() else None,
            'price': int(price) if price.isdigit() else 0,
            'city': city if city else None,
            'location': location if location else None,
            'google_maps': google_maps if google_maps else None,
            'contact_name': contact_name,
            'whatsapp': whatsapp,
            'telegram': telegram,
            'category': 'real_estate',
            'image_url': images[0] if images else None,
            'all_images': images if len(images) > 1 else None,
            'date': datetime.now().isoformat(),
            'status': 'pending'
        }
        
        pending = load_pending_listings(country)
        pending.append(new_listing)
        save_pending_listings(country, pending)
        
        send_telegram_notification(f"<b>Новая недвижимость</b>\n\n<b>{title}</b>\n{description[:200]}...\n\nКомнат: {rooms}, Площадь: {area}м², Цена: {price} VND\n\n✈️ Telegram: {telegram}")
        
        return jsonify({'success': True, 'message': 'Недвижимость отправлена на модерацию'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/submit-kids', methods=['POST'])
def submit_kids():
    try:
        captcha_answer = request.form.get('captcha_answer', '')
        captcha_token = request.form.get('captcha_token', '')
        
        expected = captcha_storage.get(captcha_token)
        if not expected or captcha_answer != expected:
            return jsonify({'error': 'Неверная капча'}), 400
        
        if captcha_token in captcha_storage:
            del captcha_storage[captcha_token]
        
        country = request.form.get('country', 'vietnam')
        title = request.form.get('title', '')
        kids_type = request.form.get('kids_type', 'schools')
        description = request.form.get('description', '')
        city = request.form.get('city', '')
        age = request.form.get('age', '')
        location = request.form.get('location', '')
        google_maps = request.form.get('google_maps', '')
        contact_name = request.form.get('contact_name', '')
        whatsapp = request.form.get('whatsapp', '')
        telegram = request.form.get('telegram', '')
        
        if not title or not description:
            return jsonify({'error': 'Заполните название и описание'}), 400
        
        if not city or not age:
            return jsonify({'error': 'Заполните город и возраст'}), 400
        
        images = []
        for i in range(4):
            file = request.files.get(f'photo_{i}')
            if file and file.filename:
                import base64
                file_data = file.read()
                if len(file_data) > 1024 * 1024:
                    return jsonify({'error': f'Фото {i+1} превышает 1 МБ'}), 400
                
                ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else 'jpg'
                data_url = f"data:image/{ext};base64,{base64.b64encode(file_data).decode()}"
                images.append(data_url)
        
        listing_id = f"pending_kids_{country}_{int(time.time())}_{len(load_pending_listings(country))}"
        
        new_listing = {
            'id': listing_id,
            'title': title,
            'kids_type': kids_type,
            'description': description,
            'city': city,
            'age': age,
            'location': location if location else None,
            'google_maps': google_maps if google_maps else None,
            'contact_name': contact_name,
            'whatsapp': whatsapp,
            'telegram': telegram,
            'category': 'kids',
            'image_url': images[0] if images else None,
            'all_images': images if len(images) > 1 else None,
            'date': datetime.now().isoformat(),
            'status': 'pending'
        }
        
        pending = load_pending_listings(country)
        pending.append(new_listing)
        save_pending_listings(country, pending)
        
        kids_type_labels = {'schools': 'Детские сады', 'events': 'Мероприятия', 'nannies': 'Няни и кружки'}
        send_telegram_notification(f"<b>Новое объявление для детей</b>\n\n<b>{title}</b>\nТип: {kids_type_labels.get(kids_type, kids_type)}\nГород: {city}\nВозраст: {age}\n\n{description[:200]}...\n\n✈️ @radimiralubvi")
        
        return jsonify({'success': True, 'message': 'Объявление отправлено на модерацию'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/admin/pending', methods=['POST'])
def admin_get_pending():
    password = request.json.get('password', '')
    country = request.json.get('country', 'vietnam')
    
    is_valid, admin_country = check_admin_password(password, country)
    if not is_valid:
        return jsonify({'error': 'Unauthorized'}), 401
    if admin_country != 'all' and admin_country != country:
        return jsonify({'error': 'No access to this country'}), 403
    
    pending = load_pending_listings(country)
    return jsonify(pending)

@app.route('/api/admin/moderate', methods=['POST'])
def admin_moderate():
    password = request.json.get('password', '')
    country = request.json.get('country', 'vietnam')
    
    is_valid, admin_country = check_admin_password(password, country)
    if not is_valid:
        return jsonify({'error': 'Unauthorized'}), 401
    if admin_country != 'all' and admin_country != country:
        return jsonify({'error': 'No access to this country'}), 403
    listing_id = request.json.get('listing_id')
    action = request.json.get('action')
    
    pending = load_pending_listings(country)
    listing = None
    
    for i, item in enumerate(pending):
        if item.get('id') == listing_id:
            listing = pending.pop(i)
            break
    
    if not listing:
        return jsonify({'error': 'Listing not found'}), 404
    
    save_pending_listings(country, pending)
    
    if action == 'approve':
        # Определяем категорию из объявления
        category = listing.get('category', 'real_estate')
        listing['id'] = f"{country}_{category}_{int(time.time())}"
        listing['status'] = 'approved'
        
        # Отправляем фото в Telegram канал и получаем URL
        print(f"MODERATION: Checking image_url for listing {listing.get('id')}")
        print(f"MODERATION: image_url exists: {bool(listing.get('image_url'))}")
        if listing.get('image_url'):
            try:
                import base64
                image_url = listing['image_url']
                image_data = None
                print(f"MODERATION: image_url type: {image_url[:50] if image_url else 'None'}...")
                
                # Если это base64 data URL
                if image_url.startswith('data:'):
                    print("MODERATION: Decoding base64 image...")
                    header, b64_data = image_url.split(',', 1)
                    image_data = base64.b64decode(b64_data)
                    print(f"MODERATION: Decoded {len(image_data)} bytes")
                # Если это локальный файл
                elif image_url.startswith('/static/') or image_url.startswith('static/'):
                    file_path = image_url.lstrip('/')
                    if os.path.exists(file_path):
                        with open(file_path, 'rb') as f:
                            image_data = f.read()
                # Если это внешний URL
                elif image_url.startswith('http'):
                    try:
                        resp = requests.get(image_url, timeout=30)
                        if resp.status_code == 200:
                            image_data = resp.content
                    except:
                        pass
                
                if image_data:
                    # Отправляем в Telegram канал и получаем file_id
                    caption = f"📋 {listing.get('title', 'Объявление')}\n\n{listing.get('description', '')[:500]}"
                    file_id = send_photo_to_channel(image_data, caption)
                    
                    if file_id:
                        listing['telegram_file_id'] = file_id
                        listing['telegram_photo'] = True
                        # Получаем актуальный URL для первоначального отображения
                        fresh_url = get_telegram_photo_url(file_id)
                        if fresh_url:
                            listing['image_url'] = fresh_url
            except Exception as e:
                print(f"Error uploading photo to Telegram: {e}")
        
        data = load_data(country)

        if category not in data:
            data[category] = []
        data[category].insert(0, listing)
        save_data(country, data)
        return jsonify({'success': True, 'message': f'Объявление одобрено и добавлено в {category}'})
    else:
        return jsonify({'success': True, 'message': 'Объявление отклонено'})

captcha_storage = {}

@app.route('/api/captcha')
def get_captcha():
    import random
    import uuid
    a = random.randint(1, 10)
    b = random.randint(1, 10)
    token = str(uuid.uuid4())[:8]
    captcha_storage[token] = str(a + b)
    if len(captcha_storage) > 1000:
        keys = list(captcha_storage.keys())[:500]
        for k in keys:
            del captcha_storage[k]
    return jsonify({'question': f'{a} + {b} = ?', 'token': token})

@app.route('/api/parser-config', methods=['GET', 'POST'])
def parser_config():
    country = request.args.get('country', 'vietnam')
    config_file = f'parser_config_{country}.json'
    
    if request.method == 'POST':
        config = request.json
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        return jsonify({'success': True})
    
    if os.path.exists(config_file):
        with open(config_file, 'r', encoding='utf-8') as f:
            return jsonify(json.load(f))
    
    return jsonify({
        'channels': [],
        'keywords': [],
        'auto_parse_interval': 300
    })

@app.route('/api/parse-thailand', methods=['POST'])
def parse_thailand():
    try:
        from bot_parser import run_bot_parser
        result = run_bot_parser()
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/thailand-channels')
def get_thailand_channels():
    channels_file = 'thailand_channels.json'
    if os.path.exists(channels_file):
        with open(channels_file, 'r', encoding='utf-8') as f:
            return jsonify(json.load(f))
    return jsonify({})

@app.route('/bot/webhook', methods=['POST'])
def bot_webhook():
    from telegram_bot import handle_start, handle_app, send_message
    
    data = request.json
    if not data:
        return jsonify({'ok': True})
    
    message = data.get('message', {})
    chat_id = message.get('chat', {}).get('id')
    text = message.get('text', '')
    user = message.get('from', {})
    user_name = user.get('first_name', 'друг')
    
    if not chat_id:
        return jsonify({'ok': True})
    
    if text == '/start':
        handle_start(chat_id, user_name)
    elif text == '/app':
        handle_app(chat_id)
    elif text == '/help':
        send_message(chat_id, '🦌 <b>Goldantelope ASIA</b>\n\n/start - Главное меню\n/app - Открыть приложение\n/thailand - Тайланд\n/vietnam - Вьетнам')
    elif text == '/thailand':
        send_message(chat_id, '🇹🇭 <b>Тайланд</b>\n\n70+ каналов:\n- Пхукет\n- Паттайя\n- Бангкок\n- Самуи\n\nНажмите /app чтобы открыть!')
    elif text == '/vietnam':
        send_message(chat_id, '🇻🇳 <b>Вьетнам</b>\n\nКаналы скоро будут добавлены!\n\nНажмите /app чтобы открыть!')
    elif text == '/auth':
        send_message(chat_id, '🔐 <b>Авторизация Telethon</b>\n\nКод был отправлен в приложение Telegram на номер +84342893121.\n\nНайдите сообщение от "Telegram" с 5-значным кодом и отправьте его сюда!')
    elif text and text.isdigit() and len(text) == 5:
        with open('pending_code.txt', 'w') as f:
            f.write(text)
        send_message(chat_id, f'✅ Код {text} получен! Пробую авторизацию...')
    
    return jsonify({'ok': True})

@app.route('/bot/setup', methods=['POST'])
def setup_bot_webhook():
    import requests
    bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
    domains = os.environ.get('REPLIT_DOMAINS', '')
    
    if domains:
        webhook_url = f"https://{domains.split(',')[0]}/bot/webhook"
        url = f'https://api.telegram.org/bot{bot_token}/setWebhook'
        result = requests.post(url, data={'url': webhook_url}).json()
        return jsonify(result)
    
    return jsonify({'error': 'No domain found'})

# ============ УПРАВЛЕНИЕ КАНАЛАМИ ============

def load_channels(country):
    """Загрузить каналы для страны"""
    channels_file = f'{country}_channels.json'
    if os.path.exists(channels_file):
        with open(channels_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get('channels', {})
    return {}

def save_channels(country, channels):
    """Сохранить каналы для страны"""
    channels_file = f'{country}_channels.json'
    with open(channels_file, 'w', encoding='utf-8') as f:
        json.dump({'channels': channels}, f, ensure_ascii=False, indent=2)

@app.route('/api/admin/channels', methods=['GET'])
def get_channels():
    """Получить список каналов по странам"""
    country = request.args.get('country', 'vietnam')
    channels = load_channels(country)
    return jsonify({'country': country, 'channels': channels})

@app.route('/api/admin/add-channel', methods=['POST'])
def add_channel():
    """Добавить канал"""
    password = request.json.get('password', '')
    country = request.json.get('country', 'vietnam')
    
    is_valid, admin_country = check_admin_password(password, country)
    if not is_valid:
        return jsonify({'error': 'Unauthorized'}), 401
    if admin_country != 'all' and admin_country != country:
        return jsonify({'error': 'No access to this country'}), 403
    category = request.json.get('category', 'chat')
    channel = request.json.get('channel', '').strip().replace('@', '')
    
    if not channel:
        return jsonify({'error': 'Channel name required'}), 400
    
    channels = load_channels(country)
    
    if category not in channels:
        channels[category] = []
    
    if channel in channels[category]:
        return jsonify({'error': 'Channel already exists'}), 400
    
    channels[category].append(channel)
    save_channels(country, channels)
    
    return jsonify({'success': True, 'message': f'Канал @{channel} добавлен в {category}'})

@app.route('/api/admin/remove-channel', methods=['POST'])
def remove_channel():
    """Удалить канал"""
    password = request.json.get('password', '')
    country = request.json.get('country', 'vietnam')
    
    is_valid, admin_country = check_admin_password(password, country)
    if not is_valid:
        return jsonify({'error': 'Unauthorized'}), 401
    if admin_country != 'all' and admin_country != country:
        return jsonify({'error': 'No access to this country'}), 403
    category = request.json.get('category')
    channel = request.json.get('channel')
    
    channels = load_channels(country)
    
    if category in channels and channel in channels[category]:
        channels[category].remove(channel)
        save_channels(country, channels)
        return jsonify({'success': True, 'message': f'Канал @{channel} удален'})
    
    return jsonify({'error': 'Channel not found'}), 404

@app.route('/api/bunny-image/<path:image_path>')
def bunny_image_proxy(image_path):
    """Прокси для загрузки изображений из BunnyCDN Storage"""
    import urllib.parse
    
    storage_zone = os.environ.get('BUNNY_CDN_STORAGE_ZONE', 'storage.bunnycdn.com')
    storage_name = os.environ.get('BUNNY_CDN_STORAGE_NAME', 'goldantelope')
    api_key = os.environ.get('BUNNY_CDN_API_KEY', '')
    
    # Decode the path and fetch from storage
    decoded_path = urllib.parse.unquote(image_path)
    url = f'https://{storage_zone}/{storage_name}/{decoded_path}'
    
    try:
        r = requests.get(url, headers={'AccessKey': api_key}, timeout=30)
        if r.status_code == 200:
            content_type = r.headers.get('Content-Type', 'image/jpeg')
            return Response(r.content, mimetype=content_type, headers={
                'Cache-Control': 'public, max-age=86400'
            })
        else:
            return Response('Image not found', status=404)
    except Exception as e:
        print(f"Error fetching image: {e}")
        return Response('Error fetching image', status=500)

# ============ УПРАВЛЕНИЕ ГОРОДАМИ ============

def load_cities_config(country, category):
    """Загрузить конфигурацию городов для категории"""
    cities_file = f'cities_{country}_{category}.json'
    if os.path.exists(cities_file):
        with open(cities_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_cities_config(country, category, cities):
    """Сохранить конфигурацию городов"""
    cities_file = f'cities_{country}_{category}.json'
    with open(cities_file, 'w', encoding='utf-8') as f:
        json.dump(cities, f, ensure_ascii=False, indent=2)

@app.route('/api/admin/cities', methods=['GET', 'POST'])
def get_cities():
    """Получить города для категории (требует авторизации)"""
    # Для GET запросов проверяем пароль в параметрах
    if request.method == 'GET':
        password = request.args.get('password', '')
        country = request.args.get('country', 'vietnam')
    else:
        password = request.json.get('password', '')
        country = request.json.get('country', 'vietnam')
    
    is_valid, admin_country = check_admin_password(password, country)
    if not is_valid:
        return jsonify({'error': 'Unauthorized'}), 401
    if admin_country != 'all' and admin_country != country:
        return jsonify({'error': 'No access to this country'}), 403
    
    category = request.args.get('category', 'restaurants') if request.method == 'GET' else request.json.get('category', 'restaurants')
    cities = load_cities_config(country, category)
    return jsonify({'country': country, 'category': category, 'cities': cities})

@app.route('/api/admin/add-city', methods=['POST'])
def add_city():
    """Добавить город"""
    password = request.form.get('password', '')
    country = request.form.get('country', 'vietnam')
    
    is_valid, admin_country = check_admin_password(password, country)
    if not is_valid:
        return jsonify({'error': 'Unauthorized'}), 401
    if admin_country != 'all' and admin_country != country:
        return jsonify({'error': 'No access to this country'}), 403
    category = request.form.get('category', 'restaurants')
    name = request.form.get('name', '').strip()
    
    if not name:
        return jsonify({'error': 'City name required'}), 400
    
    cities = load_cities_config(country, category)
    
    # Генерируем ID
    city_id = f"{country}_{category}_{len(cities)}_{int(time.time())}"
    
    # Обработка фото
    image_path = '/static/icons/placeholder.png'
    photo = request.files.get('photo')
    if photo and photo.filename:
        import base64
        file_data = photo.read()
        ext = photo.filename.rsplit('.', 1)[-1].lower() if '.' in photo.filename else 'jpg'
        
        # Сохраняем в static/icons/cities/
        os.makedirs('static/icons/cities', exist_ok=True)
        filename = f"{city_id}.{ext}"
        filepath = f"static/icons/cities/{filename}"
        with open(filepath, 'wb') as f:
            f.write(file_data)
        image_path = f"/static/icons/cities/{filename}"
    
    new_city = {
        'id': city_id,
        'name': name,
        'image': image_path
    }
    
    cities.append(new_city)
    save_cities_config(country, category, cities)
    
    return jsonify({'success': True, 'message': f'Город "{name}" добавлен'})

@app.route('/api/admin/update-city', methods=['POST'])
def update_city():
    """Обновить название города"""
    password = request.json.get('password', '')
    country = request.json.get('country', 'vietnam')
    
    is_valid, admin_country = check_admin_password(password, country)
    if not is_valid:
        return jsonify({'error': 'Unauthorized'}), 401
    if admin_country != 'all' and admin_country != country:
        return jsonify({'error': 'No access to this country'}), 403
    category = request.json.get('category', 'restaurants')
    city_id = request.json.get('city_id')
    name = request.json.get('name', '').strip()
    
    cities = load_cities_config(country, category)
    
    for city in cities:
        if city.get('id') == city_id:
            city['name'] = name
            save_cities_config(country, category, cities)
            return jsonify({'success': True, 'message': 'Город обновлён'})
    
    return jsonify({'error': 'City not found'}), 404

@app.route('/api/admin/update-city-photo', methods=['POST'])
def update_city_photo():
    """Обновить фото города"""
    password = request.form.get('password', '')
    country = request.form.get('country', 'vietnam')
    
    is_valid, admin_country = check_admin_password(password, country)
    if not is_valid:
        return jsonify({'error': 'Unauthorized'}), 401
    if admin_country != 'all' and admin_country != country:
        return jsonify({'error': 'No access to this country'}), 403
    category = request.form.get('category', 'restaurants')
    city_id = request.form.get('city_id')
    photo = request.files.get('photo')
    
    if not photo or not photo.filename:
        return jsonify({'error': 'Photo required'}), 400
    
    cities = load_cities_config(country, category)
    
    for city in cities:
        if city.get('id') == city_id:
            file_data = photo.read()
            ext = photo.filename.rsplit('.', 1)[-1].lower() if '.' in photo.filename else 'jpg'
            
            os.makedirs('static/icons/cities', exist_ok=True)
            filename = f"{city_id}.{ext}"
            filepath = f"static/icons/cities/{filename}"
            with open(filepath, 'wb') as f:
                f.write(file_data)
            
            city['image'] = f"/static/icons/cities/{filename}"
            save_cities_config(country, category, cities)
            return jsonify({'success': True, 'message': 'Фото обновлено'})
    
    return jsonify({'error': 'City not found'}), 404

@app.route('/api/admin/delete-city', methods=['POST'])
def delete_city():
    """Удалить город"""
    password = request.json.get('password', '')
    country = request.json.get('country', 'vietnam')
    
    is_valid, admin_country = check_admin_password(password, country)
    if not is_valid:
        return jsonify({'error': 'Unauthorized'}), 401
    if admin_country != 'all' and admin_country != country:
        return jsonify({'error': 'No access to this country'}), 403
    category = request.json.get('category', 'restaurants')
    city_id = request.json.get('city_id')
    
    cities = load_cities_config(country, category)
    
    for i, city in enumerate(cities):
        if city.get('id') == city_id:
            cities.pop(i)
            save_cities_config(country, category, cities)
            return jsonify({'success': True, 'message': 'Город удалён'})
    
    return jsonify({'error': 'City not found'}), 404

@app.route('/api/admin/edit-city-inline', methods=['POST'])
def edit_city_inline():
    """Редактировать город из основного меню (название и фото)"""
    password = request.form.get('password', '')
    country = request.form.get('country', 'vietnam')
    
    is_valid, admin_country = check_admin_password(password, country)
    if not is_valid:
        return jsonify({'error': 'Unauthorized'}), 401
    if admin_country != 'all' and admin_country != country:
        return jsonify({'error': 'No access to this country'}), 403
    section = request.form.get('section', 'restaurants')
    old_name = request.form.get('old_name', '')
    new_name = request.form.get('new_name', '')
    photo = request.files.get('photo')
    
    if not old_name or not new_name:
        return jsonify({'error': 'City names required'}), 400
    
    # Обновляем citiesByCountry в dashboard.html через JSON config
    config_file = f'city_config_{country}.json'
    config = {}
    if os.path.exists(config_file):
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
    
    # Обновляем название города в списке
    if section not in config:
        config[section] = {}
    
    section_data = config.get(section, {})
    cities_list = section_data.get('cities', [])
    
    # Ищем город и меняем название
    for i, city in enumerate(cities_list):
        if city == old_name:
            cities_list[i] = new_name
            break
    
    section_data['cities'] = cities_list
    
    # Обрабатываем фото
    if photo and photo.filename:
        file_data = photo.read()
        ext = photo.filename.rsplit('.', 1)[-1].lower() if '.' in photo.filename else 'jpg'
        
        os.makedirs(f'static/icons/cities/{country}/{section}', exist_ok=True)
        safe_name = new_name.replace(' ', '_').lower()
        filename = f"{safe_name}.{ext}"
        filepath = f"static/icons/cities/{country}/{section}/{filename}"
        with open(filepath, 'wb') as f:
            f.write(file_data)
        
        # Сохраняем URL фото
        if 'images' not in section_data:
            section_data['images'] = {}
        section_data['images'][new_name] = f"/{filepath}"
    
    config[section] = section_data
    
    with open(config_file, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    
    return jsonify({'success': True, 'message': 'Город обновлён'})

@app.route('/api/admin/move-city-position', methods=['POST'])
def move_city_position():
    """Переместить город вверх/вниз в списке"""
    password = request.json.get('password', '')
    country = request.json.get('country', 'vietnam')
    
    is_valid, admin_country = check_admin_password(password, country)
    if not is_valid:
        return jsonify({'error': 'Unauthorized'}), 401
    if admin_country != 'all' and admin_country != country:
        return jsonify({'error': 'No access to this country'}), 403
    section = request.json.get('section', 'restaurants')
    city_name = request.json.get('city_name', '')
    direction = request.json.get('direction', 0)  # -1 вверх, +1 вниз
    
    if not city_name:
        return jsonify({'error': 'City name required'}), 400
    
    config_file = f'city_config_{country}.json'
    config = {}
    if os.path.exists(config_file):
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
    
    if section not in config:
        return jsonify({'error': 'Section not found'}), 404
    
    cities_list = config[section].get('cities', [])
    
    # Находим индекс города
    try:
        idx = cities_list.index(city_name)
    except ValueError:
        return jsonify({'error': 'City not found'}), 404
    
    new_idx = idx + direction
    
    if new_idx < 0 or new_idx >= len(cities_list):
        return jsonify({'error': 'Cannot move beyond list boundaries'}), 400
    
    # Меняем местами
    cities_list[idx], cities_list[new_idx] = cities_list[new_idx], cities_list[idx]
    config[section]['cities'] = cities_list
    
    with open(config_file, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    
    return jsonify({'success': True, 'message': 'Город перемещён'})

@app.route('/api/admin/delete-city-inline', methods=['POST'])
def delete_city_inline():
    """Удалить город из основного меню"""
    password = request.json.get('password', '')
    country = request.json.get('country', 'vietnam')
    
    is_valid, admin_country = check_admin_password(password, country)
    if not is_valid:
        return jsonify({'error': 'Unauthorized'}), 401
    if admin_country != 'all' and admin_country != country:
        return jsonify({'error': 'No access to this country'}), 403
    section = request.json.get('section', 'restaurants')
    city_name = request.json.get('city_name', '')
    
    if not city_name:
        return jsonify({'error': 'City name required'}), 400
    
    config_file = f'city_config_{country}.json'
    config = {}
    if os.path.exists(config_file):
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
    
    if section not in config:
        return jsonify({'error': 'Section not found'}), 404
    
    cities_list = config[section].get('cities', [])
    
    if city_name in cities_list:
        cities_list.remove(city_name)
        config[section]['cities'] = cities_list
        
        # Удаляем фото если есть
        if 'images' in config[section] and city_name in config[section]['images']:
            del config[section]['images'][city_name]
        
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        
        return jsonify({'success': True, 'message': 'Город удалён'})
    
    return jsonify({'error': 'City not found'}), 404

# ============ РУЧНОЙ ПАРСЕР ============

@app.route('/api/admin/manual-parse', methods=['POST'])
def manual_parse():
    """Ручной парсинг канала - 100% всех сообщений"""
    password = request.json.get('password', '')
    country = request.json.get('country', 'vietnam')
    
    is_valid, admin_country = check_admin_password(password, country)
    if not is_valid:
        return jsonify({'error': 'Unauthorized'}), 401
    if admin_country != 'all' and admin_country != country:
        return jsonify({'error': 'No access to this country'}), 403
    channel = request.json.get('channel', '').strip().replace('@', '')
    category = request.json.get('category', 'chat')
    limit = request.json.get('limit', 0)  # 0 = все сообщения
    
    if not channel:
        return jsonify({'error': 'Channel name required'}), 400
    
    try:
        # Пытаемся использовать Telethon парсер
        from telethon.sync import TelegramClient
        
        api_id = os.environ.get('TELEGRAM_API_ID')
        api_hash = os.environ.get('TELEGRAM_API_HASH')
        
        if not api_id or not api_hash:
            return jsonify({'error': 'Telegram API credentials not configured'}), 400
        
        session_name = 'goldantelope_manual'
        client = TelegramClient(session_name, int(api_id), api_hash)
        
        count = 0
        log_messages = []
        
        with client:
            entity = client.get_entity(channel)
            
            # Если limit=0, загружаем ВСЕ сообщения (iter_messages без limit)
            if limit == 0 or limit >= 10000:
                messages = client.iter_messages(entity)
            else:
                messages = client.iter_messages(entity, limit=limit)
            
            data = load_data(country)

            if category not in data:
                data[category] = []
            
            existing_ids = set(item.get('telegram_link', '') for item in data[category])
            
            for msg in messages:
                if msg.text:
                    telegram_link = f"https://t.me/{channel}/{msg.id}"
                    
                    # Пропускаем дубликаты
                    if telegram_link in existing_ids:
                        continue
                    
                    # Создаём объявление
                    listing_id = f"{country}_{category}_{int(time.time())}_{count}"
                    
                    new_listing = {
                        'id': listing_id,
                        'title': msg.text[:100] if msg.text else 'Без названия',
                        'description': msg.text,
                        'date': msg.date.isoformat() if msg.date else datetime.now().isoformat(),
                        'telegram_link': telegram_link,
                        'category': category
                    }
                    
                    # Обработка фото - пересылаем в наш Telegram канал
                    if msg.photo:
                        try:
                            # Скачиваем фото во временный буфер
                            import io
                            photo_buffer = io.BytesIO()
                            client.download_media(msg.photo, file=photo_buffer)
                            photo_buffer.seek(0)
                            image_data = photo_buffer.read()
                            
                            if image_data:
                                # Отправляем в Telegram канал с полным текстом
                                caption = f"📋 {new_listing['title']}\n\n{msg.text[:900] if msg.text else ''}"
                                file_id = send_photo_to_channel(image_data, caption)
                                
                                if file_id:
                                    new_listing['telegram_file_id'] = file_id
                                    new_listing['telegram_photo'] = True
                                    # Получаем актуальный URL
                                    fresh_url = get_telegram_photo_url(file_id)
                                    if fresh_url:
                                        new_listing['image_url'] = fresh_url
                                    log_messages.append(f"[✓] Фото #{count+1} загружено в Telegram канал")
                        except Exception as photo_err:
                            log_messages.append(f"[!] Ошибка фото: {photo_err}")
                    
                    data[category].insert(0, new_listing)
                    existing_ids.add(telegram_link)
                    count += 1
                    
                    if count % 50 == 0:
                        log_messages.append(f"[{count}] Обработано {count} сообщений...")
            
            save_data(country, data)
        
        return jsonify({
            'success': True, 
            'message': f'Парсинг завершён. Добавлено {count} объявлений из канала @{channel}.',
            'count': count,
            'log': '\n'.join(log_messages[-30:])
        })
        
    except ImportError:
        return jsonify({'error': 'Telethon не установлен. Используйте Bot API.'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============ TELEGRAM КАНАЛ ДЛЯ ФОТО ============

TELEGRAM_PHOTO_CHANNEL = '-1003577636318'

def send_photo_to_channel(image_data, caption=''):
    """Отправить фото в Telegram канал и получить file_id для постоянного хранения"""
    bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
    if not bot_token:
        print("TELEGRAM: Bot token not found!")
        return None
    
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
        
        files = {'photo': ('photo.jpg', image_data, 'image/jpeg')}
        data = {
            'chat_id': TELEGRAM_PHOTO_CHANNEL,
            'caption': caption[:1024] if caption else ''
        }
        
        print(f"TELEGRAM: Sending photo to channel {TELEGRAM_PHOTO_CHANNEL}, size: {len(image_data)} bytes")
        response = requests.post(url, files=files, data=data, timeout=30)
        result = response.json()
        print(f"TELEGRAM: Response: {result}")
        
        if result.get('ok'):
            photo = result['result'].get('photo', [])
            if photo:
                largest = max(photo, key=lambda x: x.get('file_size', 0))
                file_id = largest.get('file_id')
                print(f"TELEGRAM: Photo uploaded! file_id: {file_id[:50]}...")
                return file_id
        else:
            print(f"TELEGRAM: Failed to send photo: {result.get('description', 'Unknown error')}")
        
        return None
    except Exception as e:
        print(f"TELEGRAM: Error sending photo to channel: {e}")
        return None

def get_telegram_photo_url(file_id):
    """Получить актуальный URL фото по file_id"""
    bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
    if not bot_token or not file_id:
        return None
    
    try:
        file_url = f"https://api.telegram.org/bot{bot_token}/getFile?file_id={file_id}"
        file_response = requests.get(file_url, timeout=10).json()
        
        if file_response.get('ok'):
            file_path = file_response['result'].get('file_path')
            return f"https://api.telegram.org/file/bot{bot_token}/{file_path}"
    except:
        pass
    return None

# ============ ВНУТРЕННИЙ ЧАТ С TELEGRAM АВТОРИЗАЦИЕЙ ============

CHAT_DATA_FILE = 'internal_chat.json'
CHAT_BLACKLIST_FILE = 'chat_blacklist.json'
verification_codes = {}
import random
import string

CHAT_FILES = {
    'vietnam': 'internal_chat.json',
    'thailand': 'internal_chat_thailand.json',
    'india': 'internal_chat_india.json',
    'indonesia': 'internal_chat_indonesia.json'
}

def get_chat_file(country='vietnam'):
    return CHAT_FILES.get(country, CHAT_FILES['vietnam'])

def load_chat_data(country='vietnam'):
    chat_file = get_chat_file(country)
    if os.path.exists(chat_file):
        with open(chat_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            messages = data.get('messages', [])
            three_days_ago = datetime.now() - timedelta(days=3)
            messages = [m for m in messages if datetime.fromisoformat(m.get('timestamp', '2000-01-01')) > three_days_ago]
            return {'messages': messages[-1000:], 'users': data.get('users', {})}
    return {'messages': [], 'users': {}}

def save_chat_data(data, country='vietnam'):
    chat_file = get_chat_file(country)
    three_days_ago = datetime.now() - timedelta(days=3)
    data['messages'] = [m for m in data.get('messages', []) if datetime.fromisoformat(m.get('timestamp', '2000-01-01')) > three_days_ago][-1000:]
    with open(chat_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_blacklist():
    if os.path.exists(CHAT_BLACKLIST_FILE):
        with open(CHAT_BLACKLIST_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {'users': []}

def save_blacklist(data):
    with open(CHAT_BLACKLIST_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

CHAT_USERS_FILE = 'chat_users.json'

def load_chat_users():
    if os.path.exists(CHAT_USERS_FILE):
        with open(CHAT_USERS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_chat_users(data):
    with open(CHAT_USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def find_chat_id_by_username(username):
    users = load_chat_users()
    username_lower = username.lower().replace('@', '')
    if username_lower in users:
        return users[username_lower]
    
    bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
    if not bot_token:
        return None
    
    try:
        url = f"https://api.telegram.org/bot{bot_token}/getUpdates?limit=100"
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            updates = resp.json().get('result', [])
            for upd in updates:
                msg = upd.get('message', {})
                user = msg.get('from', {})
                uname = user.get('username', '').lower()
                chat_id = msg.get('chat', {}).get('id')
                if uname and chat_id:
                    users[uname] = str(chat_id)
            save_chat_users(users)
            if username_lower in users:
                return users[username_lower]
    except Exception as e:
        print(f"Error finding chat_id: {e}")
    return None

@app.route('/api/chat/request-code', methods=['POST'])
def request_chat_code():
    data = request.json
    username = data.get('telegram_id', '').strip().replace('@', '')
    if not username:
        return jsonify({'success': False, 'error': 'Укажите ваш @username'})
    
    blacklist = load_blacklist()
    if username.lower() in [u.lower() for u in blacklist.get('users', [])]:
        return jsonify({'success': False, 'error': 'Ваш аккаунт заблокирован'})
    
    chat_id = find_chat_id_by_username(username)
    if not chat_id:
        return jsonify({'success': False, 'error': 'Сначала напишите боту @goldantelope_bot команду /start'})
    
    code = ''.join(random.choices(string.digits, k=6))
    verification_codes[username.lower()] = {'code': code, 'expires': datetime.now() + timedelta(minutes=10), 'chat_id': chat_id}
    
    message = f"🔐 Ваш код для чата GoldAntelope:\n\n<b>{code}</b>\n\nКод действителен 10 минут."
    
    try:
        bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
        if bot_token:
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            resp = requests.post(url, json={'chat_id': chat_id, 'text': message, 'parse_mode': 'HTML'}, timeout=10)
            if resp.status_code == 200 and resp.json().get('ok'):
                return jsonify({'success': True, 'message': 'Код отправлен в Telegram'})
            else:
                error_desc = resp.json().get('description', 'Ошибка отправки')
                return jsonify({'success': False, 'error': f'Ошибка Telegram: {error_desc}'})
    except Exception as e:
        print(f"Chat code error: {e}")
    
    return jsonify({'success': False, 'error': 'Не удалось отправить код'})

@app.route('/api/chat/verify-code', methods=['POST'])
def verify_chat_code():
    data = request.json
    telegram_id = data.get('telegram_id', '').strip().replace('@', '').lower()
    code = data.get('code', '').strip()
    
    if not telegram_id or not code:
        return jsonify({'success': False, 'error': 'Укажите ID и код'})
    
    stored = verification_codes.get(telegram_id)
    if not stored:
        return jsonify({'success': False, 'error': 'Сначала запросите код'})
    
    if datetime.now() > stored['expires']:
        del verification_codes[telegram_id]
        return jsonify({'success': False, 'error': 'Код истёк, запросите новый'})
    
    if stored['code'] != code:
        return jsonify({'success': False, 'error': 'Неверный код'})
    
    del verification_codes[telegram_id]
    
    session_token = ''.join(random.choices(string.ascii_letters + string.digits, k=32))
    
    for country in CHAT_FILES.keys():
        chat_data = load_chat_data(country)
        chat_data['users'][session_token] = {'telegram_id': telegram_id, 'created': datetime.now().isoformat()}
        save_chat_data(chat_data, country)
    
    return jsonify({'success': True, 'token': session_token, 'username': telegram_id})

@app.route('/api/chat/messages', methods=['GET'])
def get_chat_messages():
    country = request.args.get('country', 'vietnam')
    chat_data = load_chat_data(country)
    return jsonify({'messages': chat_data.get('messages', [])[-1000:]})

@app.route('/api/chat/send', methods=['POST'])
def send_chat_message():
    data = request.json
    username = data.get('username', 'Гость').strip()
    message = data.get('message', '').strip()
    country = data.get('country', 'vietnam')
    
    if not message:
        return jsonify({'success': False, 'error': 'Введите сообщение'})
    
    if not username:
        username = 'Гость'
    
    if len(message) > 2000:
        return jsonify({'success': False, 'error': 'Сообщение слишком длинное (макс 2000 символов)'})
    
    if len(username) > 50:
        return jsonify({'success': False, 'error': 'Ник слишком длинный'})
    
    blacklist = load_blacklist()
    if username.lower() in [u.lower() for u in blacklist.get('users', [])]:
        return jsonify({'success': False, 'error': 'Ваш аккаунт заблокирован'})
    
    chat_data = load_chat_data(country)
    
    new_message = {
        'id': f"msg_{int(time.time())}_{random.randint(1000,9999)}",
        'username': username,
        'message': message,
        'timestamp': datetime.now().isoformat()
    }
    
    chat_data['messages'].append(new_message)
    save_chat_data(chat_data, country)
    
    # Дублируем сообщение в Telegram канал
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        try:
            tg_text = f"💬 <b>{username}</b>\n{message}"
            send_telegram_notification(tg_text)
        except Exception as e:
            print(f"Error sending chat to Telegram: {e}")
    
    return jsonify({'success': True})

@app.route('/api/admin/chat-blacklist', methods=['GET', 'POST'])
def admin_chat_blacklist():
    admin_key = request.headers.get('X-Admin-Key') or request.json.get('admin_key') if request.json else None
    expected_key = os.environ.get('ADMIN_KEY', 'goldantelope2025')
    if admin_key != expected_key:
        return jsonify({'success': False, 'error': 'Неверный пароль'}), 401
    
    if request.method == 'GET':
        return jsonify(load_blacklist())
    
    data = request.json
    action = data.get('action')
    username = data.get('username', '').strip().replace('@', '').lower()
    
    if not username:
        return jsonify({'success': False, 'error': 'Укажите username'})
    
    blacklist = load_blacklist()
    
    if action == 'add':
        if username not in blacklist['users']:
            blacklist['users'].append(username)
            save_blacklist(blacklist)
        return jsonify({'success': True, 'message': f'{username} добавлен в чёрный список'})
    elif action == 'remove':
        blacklist['users'] = [u for u in blacklist['users'] if u.lower() != username]
        save_blacklist(blacklist)
        return jsonify({'success': True, 'message': f'{username} удалён из чёрного списка'})
    
    return jsonify({'success': False, 'error': 'Неизвестное действие'})

@app.route('/api/admin/chat-delete', methods=['POST'])
def admin_delete_chat_message():
    data = request.json
    admin_key = data.get('admin_key')
    expected_key = os.environ.get('ADMIN_KEY', 'goldantelope2025')
    if admin_key != expected_key:
        return jsonify({'success': False, 'error': 'Неверный пароль'}), 401
    
    msg_id = data.get('message_id')
    if not msg_id:
        return jsonify({'success': False, 'error': 'Укажите ID сообщения'})
    
    chat_data = load_chat_data()
    chat_data['messages'] = [m for m in chat_data['messages'] if m.get('id') != msg_id]
    save_chat_data(chat_data)
    
    return jsonify({'success': True, 'message': 'Сообщение удалено'})


if __name__ == '__main__':

def run_bot():
    import asyncio
    # Создаем новый цикл событий для отдельного потока
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    # Запускаем основной цикл бота (предполагаем, что client определен глобально)
    with client:
        client.run_until_disconnected()

if __name__ == '__main__':
    # Запускаем бота в фоне
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    # Запускаем Flask на порту, который дает Railway
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
