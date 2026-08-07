import os
import threading
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

# استيراد تطبيق الفلاسك وقواعد البيانات الموحدة من admin_app
from admin_app import app, database

BOT_TOKEN = os.environ.get("BOT_TOKEN")
WEBAPP_URL = os.environ.get("WEB_URL", "https://admin-zn-production.up.railway.app/").strip().rstrip('/')
ADMIN_ID = os.environ.get("ADMIN_ID", "5102387551")

bot = telebot.TeleBot(BOT_TOKEN) if BOT_TOKEN else None

def is_user_authorized(user_id):
    """فحص صلاحيات دخول بوت الأدمن"""
    user_id_str = str(user_id)
    if user_id_str == str(ADMIN_ID):
        return True
    try:
        if hasattr(database, 'db') and database.db:
            return database.db.collection('moderators').document(user_id_str).get().exists
    except Exception as e:
        print(f"⚠️ Error checking moderator status: {e}")
    return False

if bot:
    @bot.message_handler(commands=['start'])
    def send_welcome(message):
        user_id = message.from_user.id
        
        if not is_user_authorized(user_id):
            bot.reply_to(message, "⛔ عذراً، هذا البوت مخصص للأدمن والمشرفين المصرح لهم فقط.")
            return

        markup = InlineKeyboardMarkup()
        webapp = WebAppInfo(url=WEBAPP_URL)
        btn = InlineKeyboardButton(text="💻 فتح لوحة التحكم", web_app=webapp)
        markup.add(btn)

        bot.send_message(
            message.chat.id,
            "👑 **أهلاً بك يا مدير!**\n\nتم التحقق من صلاحياتك بنجاح، اضغط لفتح لوحة التحكم:",
            reply_markup=markup,
            parse_mode="Markdown"
        )

def run_web_server():
    """تشغيل سيرفر الفلاسك الموحد داخل Thread مستقل"""
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

if __name__ == "__main__":
    print("🌐 جاري تشغيل سيرفر الويب الموحد للوحة التحكم...")
    threading.Thread(target=run_web_server, daemon=True).start()
    
    if bot:
        print("🤖 بوت أزرار الأدمن قيد التشغيل...")
        bot.infinity_polling()
    else:
        print("⚠️ لم يتم العثور على BOT_TOKEN، يعمل سيرفر الويب فقط.")
