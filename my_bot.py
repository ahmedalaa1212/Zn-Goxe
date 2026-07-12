import os
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

# Railway هتقرأ التوكن من الـ Variables اللي ضفناها
API_TOKEN = os.getenv('API_TOKEN')

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    # الرابط اللي إنت جبته من GitHub Pages
    game_url = "https://ahmedalaa1212.github.io/Zn-Goxe/"
    
    # تعريف الزرار اللي بيفتح اللعبة
    web_app = WebAppInfo(url=game_url)
    button = InlineKeyboardButton(text="🎮 افتح اللعبة", web_app=web_app)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[button]])

    await message.answer("أهلاً بك! اضغط على الزر أدناه لفتح اللعبة:", reply_markup=keyboard)

async def main():
    print("البوت بدأ العمل بنجاح...")
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
