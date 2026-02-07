import asyncio
from telethon import TelegramClient, functions, types

# Твои данные
api_id = 28939221
api_hash = '572d45c5890c20f18705a695b0959092'
bot_token = '8058224567:AAFgF-p5mUjO_7dYTB5C-zHovIxZKqHRdK4'

async def main():
    # Заходим именно как БОТ
    client = TelegramClient('bot_admin_check', api_id, api_hash)
    await client.start(bot_token=bot_token)
    
    print("🤖 Бот успешно запущен. Проверяю группы...\n")
    
    async for dialog in client.iter_dialogs():
        if dialog.is_group or dialog.is_channel:
            # Проверяем наши права в этом чате
            try:
                permissions = await client.get_permissions(dialog.id, 'me')
                if permissions.is_admin:
                    print(f"✅ АДМИН в: {dialog.name} (ID: {dialog.id})")
                else:
                    print(f"👤 Участник (не админ) в: {dialog.name}")
            except Exception as e:
                print(f"❓ Нет доступа к информации о правах в: {dialog.name}")

    print("\nПроверка завершена!")
    await client.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
