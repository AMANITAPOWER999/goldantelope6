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
    
    text = f'''👋 <b>Добро пожаловать в Goldantelope ASIA!</b>

Ваш универсальный гид и сервис-хаб по Юго-Восточной Азии. Мы объединяем тысячи предложений в 4 странах:

🇹🇭 Таиланд | 🇮🇩 Индонезия | 🇮🇳 Индия | 🇻🇳 Вьетнам

🚀 <b>Что вы найдете в боте:</b>

• Недвижимость: более 1500 объектов (аренда и покупка).

• Транспорт: от 200 вариантов (байки, авто, яхты).

• Рестораны и Досуг: сотни локаций и авторских экскурсий.

• Сервис: визаран, обмен валют, медицина и чаты общения.

📍 <b>Популярные направления:</b> Нячанг, Дананг, Хошимин, Ханой, Фукуок и другие города региона.

Нажмите /start, чтобы начать! 👇 и нажмите <b>Открыть мини приложение</b>.'''

    keyboard = {
        "inline_keyboard": [
            [{"text": "🚀 Открыть мини приложение", "web_app": {"url": webapp_url}}],
            [{"text": "🇹🇭 Тайланд", "callback_data": "country_thailand"}, 
             {"text": "🇻🇳 Вьетнам", "callback_data": "country_vietnam"}],
            [{"text": "🇮🇳 Индия", "callback_data": "country_india"}, 
             {"text": "🇮🇩 Индонезия", "callback_data": "country_indonesia"}]
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
