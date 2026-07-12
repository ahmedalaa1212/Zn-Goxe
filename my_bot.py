import os
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart

# Railway هتقرأ التوكن من الـ Variables اللي هنضيفها
API_TOKEN = os.getenv('API_TOKEN')

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    await message.answer("أهلاً! البوت شغال على Railway بنجاح.")

async def main():
    print("البوت بدأ العمل...")
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
