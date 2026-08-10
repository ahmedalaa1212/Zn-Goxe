import os
import threading
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

from admin_app import app, database

BOT_TOKEN = os.environ.get("BOT_TOKEN")

# جلب رابط الموقع وإضافة مسار /admin لضمان فتح لوحة التحكم بدلاً من واجهة المستخدم
BASE_URL = os.environ.get("WEB_URL", "https://admin-zn-production.up.railway.app/").strip().rstrip('/')
ADMIN_WEBAPP_URL = BASE_URL if BASE_URL.endswith('/admin') else f"{BASE_URL}/admin"

ADMIN_ID = os.environ.get("ADMIN_ID", "5102387551")

bot = telebot.TeleBot(BOT_TOKEN) if BOT_TOKEN else None

def is_user_authorized(user_id):
    """فحص حي ومباشر لصلاحيات دخول بوت الأدمن"""
    if not user_id:
        return False
    user_id_str = str(user_id)
    if user_id_str == str(ADMIN_ID):
        return True
    try:
        if hasattr(database, 'db') and database.db:
            mod_doc = database.db.collection('moderators').document(user_id_str).get()
            return mod_doc.exists
    except Exception as e:
        print(f"⚠️ Error checking moderator status: {e}")
    return False

if bot:
    @bot.message_handler(commands=['start'])
    def send_welcome(message):
        user_id = message.from_user.id
        
        if not is_user_authorized(user_id):
            bot.reply_to(message, "⛔ عذراً، هذا البوت مخصص للإدارة والمشرفين المصرح لهم فقط.")
            return

        markup = InlineKeyboardMarkup()
        # توجيه الـ WebApp مباشرة لرابط لوحة الأدمن
        webapp = WebAppInfo(url=ADMIN_WEBAPP_URL)
        btn = InlineKeyboardButton(text="💻 فتح لوحة التحكم", web_app=webapp)
        markup.add(btn)

        bot.send_message(
            message.chat.id,
            "👑 **أهلاً بك يا مدير!**\n\nتم التحقق من صلاحياتك بنجاح، اضغط لفتح لوحة التحكم:",
            reply_markup=markup,
            parse_mode="Markdown"
        )

    @bot.message_handler(func=lambda message: True)
    def handle_all_messages(message):
        user_id = message.from_user.id
        if not is_user_authorized(user_id):
            bot.reply_to(message, "⛔ عذراً، البوت مخصص للإدارة والمشرفين المصرح لهم فقط.")
            return
        
        bot.reply_to(message, "ℹ️ يرجى استخدام زر 'فتح لوحة التحكم' لإدارة المنظومة.")

    @bot.callback_query_handler(func=lambda call: True)
    def handle_callback_query(call):
        user_id = call.from_user.id
        if not is_user_authorized(user_id):
            bot.answer_callback_query(call.id, "⛔ عذراً، البوت مخصص للإدارة فقط.", show_alert=True)
            return

# --- تشغيل البوت تلقائياً في الخلفية (Thread) عند استدعاء الملف بواسطة Gunicorn ---
def start_bot_polling():
    if bot:
        print("🤖 بوت أزرار الأدمن قيد التشغيل عبر Background Thread...")
        try:
            bot.infinity_polling(skip_pending=True)
        except Exception as e:
            print(f"⚠️ Error in bot polling: {e}")

if bot:
    bot_thread = threading.Thread(target=start_bot_polling, daemon=True)
    bot_thread.start()

def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

if __name__ == "__main__":
    run_web_server()
