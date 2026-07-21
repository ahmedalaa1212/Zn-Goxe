import os
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from flask import Flask, send_from_directory
import threading

# ==========================================
# 1. إعداد المتغيرات
# ==========================================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
WEBAPP_URL = "https://admin-zn-production.up.railway.app/" 
ADMIN_ID = "5102387551" # ⚠️ ضع الـ ID الخاص بك

# ==========================================
# 2. إعداد سيرفر الويب (لوحة التحكم)
# ==========================================
app = Flask(__name__, static_folder='.')

@app.route('/')
def home():
    # تم تغيير الاسم هنا إلى admin.html
    return send_from_directory('.', 'admin.html')

@app.route('/<path:filename>')
def serve_files(filename):
    return send_from_directory('.', filename)

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# ==========================================
# 3. إعداد بوت التليجرام
# ==========================================
bot = telebot.TeleBot(BOT_TOKEN)

@bot.message_handler(commands=['start'])
def send_welcome(message):
    if str(message.from_user.id) != str(ADMIN_ID):
        bot.reply_to(message, "⛔ عذراً، هذا البوت مخصص للأدمن فقط.")
        return

    markup = InlineKeyboardMarkup()
    webapp = WebAppInfo(url=WEBAPP_URL)
    btn = InlineKeyboardButton(text="💻 فتح لوحة التحكم", web_app=webapp)
    markup.add(btn)

    bot.send_message(
        message.chat.id,
        "👑 **أهلاً بك يا مدير!**\n\nاضغط لفتح لوحة التحكم الخاصة بك:",
        reply_markup=markup,
        parse_mode="Markdown"
    )

if __name__ == "__main__":
    print("🌐 جاري تشغيل سيرفر الويب...")
    threading.Thread(target=run_web_server).start()
    
    print("🤖 بوت الأدمن قيد التشغيل...")
    bot.infinity_polling()
