import threading
import os

# Читаем старый файл
with open('app.py', 'r') as f:
    lines = f.readlines()

# Убираем старый запуск Flask в конце
new_lines = []
for line in lines:
    if "app.run(" not in line:
        new_lines.append(line)

# Добавляем новую логику запуска
footer = """
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
"""

with open('app.py', 'w') as f:
    f.writelines(new_lines)
    f.write(footer)
