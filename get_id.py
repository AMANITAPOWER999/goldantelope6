import asyncio
from telethon import TelegramClient

api_id = 28939221
api_hash = '572d45c5890c20f18705a695b0959092'
bot_token = '8058224567:AAFgF-p5mUjO_7dYTB5C-zHovIxZKqHRdK4'

async def main():
    client = TelegramClient('check_ids', api_id, api_hash)
    await client.start(bot_token=bot_token)
    
    async for dialog in client.iter_dialogs():
        print(f"Имя: {dialog.name:30} | ID: {dialog.id}")

if __name__ == '__main__':
    asyncio.run(main())
