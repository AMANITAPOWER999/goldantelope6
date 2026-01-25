# Goldantelope ASIA - Workflows Configuration

## Текущие Workflows:

### 1. Chat Parser (каждую минуту)
- **Файл:** chat_parser.py
- **Команда:** while true; do python chat_parser.py; sleep 60; done
- **Функция:** Собирает новые сообщения из чатов всех 4 стран
- **Статус:** RUNNING ✅

### 2. Telegram Parser Dashboard (основной сервер)
- **Файл:** app.py
- **Команда:** python app.py
- **Функция:** Flask дашборд на порте 5000
- **Статус:** RUNNING ✅

### 3. Auto Parser (периодический, основной парсер)
- **Файл:** channel_parser.py
- **Команда:** python3 channel_parser.py && sleep 600
- **Функция:** Собирает объявления из Telegram каналов
- **Статус:** FAILED (Rate limit от Telegram - подождать 21 час)
- **Примечание:** Используется одна сессия (goldantelope_user)

### 4. Additional Parser (новый - дополнительный)
- **Файл:** additional_parser.py (новый)
- **Команда:** while true; do python additional_parser.py; sleep 300; done
- **Функция:** Собирает данные из дополнительных каналов параллельно
- **Статус:** ГОТОВ К ЗАПУСКУ
- **Примечание:** Использует отдельную сессию (goldantelope_additional)

## Преимущества:
✅ Auto Parser и Additional Parser работают с разными сессиями
✅ Можно обойти rate limit параллельной работой
✅ Больше данных, меньше конфликтов
✅ Auto Parser перезагружается каждые 10 минут, Additional каждые 5 минут

