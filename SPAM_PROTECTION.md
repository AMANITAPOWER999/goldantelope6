# Защита от спама и промо-объявлений

## Активная фильтрация

Все парсеры (Chat Parser, Additional Parser, Channel Parser) теперь отклоняют:

### 1. Промо-объявления о торговле:
- deriv.com
- synthetic indices
- trading account
- round-the-clock trading
- forex trading
- crypto trading

### 2. Как это работает:
```python
def is_spam(text):
    spam_keywords = [
        'deriv.com', 'synthetic indices', 'trading account',
        'round-the-clock trading', 'forex', 'crypto trading'
    ]
    return any(keyword in text.lower() for keyword in spam_keywords)
```

### 3. Результат:
✅ 4 спам-объявления удалены из Индонезии
✅ Новый спам автоматически отклоняется
✅ Только реальный контент на дашборде

## История удаления спама:
- **14.12.2025** и **10.11.2025**: Удалены 4 промо-объявления о Deriv trading из @indonesia_chat
- Осталось: **801 настоящее объявление** в Индонезии

