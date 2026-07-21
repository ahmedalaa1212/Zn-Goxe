import os
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from flask import Flask, render_template
import threading

# ==========================================
# 1. إعداد المتغيرات
# ==========================================
BOT_TOKEN = os.environ.get("BOT_TOKEN")

# رابط السيرفر بتاعك على Railway (اللي ظاهر في صورتك التالتة)
WEBAPP_URL = "https://admin-zn-production.up.railway.app/" 

# ⚠️ هام جداً: ضع الـ Telegram ID الخاص بك هنا
ADMIN_ID = "5102387551"

# ==========================================
# 2. إعداد سيرفر الويب (لوحة التحكم)
# ==========================================
app = Flask(__name__)

@app.route('/')
def home():
    # هذا الأمر يقوم بفتح ملف الـ HTML الخاص بلوحة التحكم
    return render_template('admin.html')

def run_web_server():
    # تشغيل السيرفر على البورت الذي يحدده Railway (افتراضياً 8080)
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# ==========================================
# 3. إعداد بوت التليجرام
# ==========================================
bot = telebot.TeleBot(BOT_TOKEN)

@bot.message_handler(commands=['start'])
def send_welcome(message):
    # التحقق من أن المستخدم هو الأدمن
    if str(message.from_user.id) != str(ADMIN_ID):
        bot.reply_to(message, "⛔ عذراً، هذا البوت مخصص للأدمن فقط.")
        return

    # إنشاء زر الويب (Mini App)
    markup = InlineKeyboardMarkup()
    webapp = WebAppInfo(url=WEBAPP_URL)
    btn = InlineKeyboardButton(text="💻 فتح لوحة التحكم", web_app=webapp)
    markup.add(btn)

    bot.send_message(
        message.chat.id,
        "👑 **أهلاً بك يا مدير!**\n\nاضغط على الزر بالأسفل لفتح لوحة تحكم اللعبة:",
        reply_markup=markup,
        parse_mode="Markdown"
    )

# ==========================================
# 4. تشغيل السيرفر والبوت معاً
# ==========================================
if __name__ == "__main__":
    print("🌐 جاري تشغيل سيرفر الويب...")
    # تشغيل Flask في مسار (Thread) منفصل
    threading.Thread(target=run_web_server).start()
    
    print("🤖 بوت الأدمن قيد التشغيل الآن...")
    bot.infinity_polling()
