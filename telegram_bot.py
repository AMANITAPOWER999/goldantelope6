import os
import asyncio
import requests
import json

BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')

def get_webapp_url():
    domains = os.environ.get('REPLIT_DOMAINS', '')
    if domains:
        return f"https://{domains.split(',')[0]}"
    return "https://goldantelope-asia.replit.app"

def send_message(chat_id, text, reply_markup=None):
    url = f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage'
    data = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'HTML'
    }
    if reply_markup:
        data['reply_markup'] = json.dumps(reply_markup)
    return requests.post(url, data=data).json()

def set_bot_commands():
    url = f'https://api.telegram.org/bot{BOT_TOKEN}/setMyCommands'
    commands = [
        {"command": "start", "description": "Запустить бота"},
        {"command": "app", "description": "Открыть мини-приложение"},
        {"command": "thailand", "description": "Каналы Тайланда"},
        {"command": "vietnam", "description": "Каналы Вьетнама"},
        {"command": "help", "description": "Помощь"}
    ]
    data = {'commands': json.dumps(commands)}
    return requests.post(url, data=data).json()

def set_menu_button():
    url = f'https://api.telegram.org/bot{BOT_TOKEN}/setChatMenuButton'
    webapp_url = get_webapp_url()
    menu_button = {
        "type": "web_app",
        "text": "Открыть",
        "web_app": {"url": webapp_url}
    }
    data = {'menu_button': json.dumps(menu_button)}
    return requests.post(url, data=data).json()

def handle_start(chat_id, user_name):
    webapp_url = get_webapp_url()
    name = user_name or "друг"

    text = f'''👋 <b>Добро пожаловать, {name}!</b>
<b>Chào mừng bạn đến với Goldantelope ASIA!</b>

━━━━━━━━━━━━━━━━━━━━
🇷🇺 <b>GOLDANTELOPE ASIA</b> — ваш гид по Вьетнаму и Таиланду

Мы собрали тысячи актуальных предложений в одном месте:

🏠 <b>Недвижимость</b> — более 3000 объектов аренды и покупки
   📍 Нячанг, Дананг, Хошимин, Ханой, Фукуок
   📍 Бангкок, Пхукет, Паттайя, Самуи

🍽 <b>Рестораны</b> — 350+ заведений в городах Таиланда и Вьетнама

🎯 <b>Экскурсии и развлечения</b> — лучшие туры и активности

🛵 <b>Транспорт</b> — аренда байков, авто, трансферы

💱 <b>Обмен валют</b> — актуальные курсы VND и THB

🏥 <b>Медицина, визы, детям</b> — все сервисы для жизни за рубежом

━━━━━━━━━━━━━━━━━━━━
🇻🇳 <b>GOLDANTELOPE ASIA</b> — hướng dẫn du lịch và cuộc sống tại Việt Nam & Thái Lan

🏠 <b>Bất động sản</b> — hơn 3000 bất động sản cho thuê và mua bán
   📍 Nha Trang, Đà Nẵng, TP.HCM, Hà Nội, Phú Quốc
   📍 Bangkok, Phuket, Pattaya, Koh Samui

🍽 <b>Nhà hàng</b> — 350+ địa điểm ẩm thực tại Thái Lan và Việt Nam

🎯 <b>Tour & Giải trí</b> — các tour và hoạt động tốt nhất

🛵 <b>Phương tiện</b> — thuê xe máy, ô tô, xe đưa đón

💱 <b>Đổi tiền</b> — tỷ giá VND và THB cập nhật

🏥 <b>Y tế, thị thực, trẻ em</b> — đầy đủ dịch vụ cho cuộc sống ở nước ngoài

━━━━━━━━━━━━━━━━━━━━
👇 Нажмите кнопку ниже / Nhấn nút bên dưới:'''

    keyboard = {
        "inline_keyboard": [
            [{"text": "🌏 Открыть портал / Mở cổng thông tin", "web_app": {"url": webapp_url}}],
            [
                {"text": "🇻🇳 Вьетнам", "callback_data": "country_vietnam"},
                {"text": "🇹🇭 Таиланд", "callback_data": "country_thailand"}
            ]
        ]
    }

    return send_message(chat_id, text, keyboard)

def handle_app(chat_id):
    webapp_url = get_webapp_url()
    
    text = "🚀 Нажмите кнопку, чтобы открыть мини-приложение:"
    
    keyboard = {
        "inline_keyboard": [
            [{"text": "📱 Открыть Goldantelope ASIA", "web_app": {"url": webapp_url}}]
        ]
    }
    
    return send_message(chat_id, text, keyboard)

def setup_bot():
    print("Setting up bot...")
    
    result1 = set_bot_commands()
    print(f"Commands: {result1}")
    
    result2 = set_menu_button()
    print(f"Menu button: {result2}")
    
    print(f"Web App URL: {get_webapp_url()}")
    print("Bot setup complete!")

if __name__ == "__main__":
    setup_bot()
