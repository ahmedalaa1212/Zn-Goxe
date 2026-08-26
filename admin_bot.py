import os
import time
import threading
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

from admin_app import app, database

BOT_TOKEN = os.environ.get("ADMIN_BOT_TOKEN") or os.environ.get("BOT_TOKEN")

BASE_URL = os.environ.get("WEB_URL", "https://admin-zn-production.up.railway.app/").strip().rstrip('/')
ADMIN_WEBAPP_URL = BASE_URL if BASE_URL.endswith('/admin') else f"{BASE_URL}/admin"

ADMIN_ID = os.environ.get("ADMIN_ID", "5102387551").strip()

bot = telebot.TeleBot(BOT_TOKEN) if BOT_TOKEN else None

def is_user_authorized(user_id):
    """فحص حي ومباشر لصلاحيات دخول بوت الأدمن"""
    if not user_id:
        return False
    user_id_str = str(user_id).strip()
    
    # 👑 الأدمن الأساسي مصرح له دائماً مطلقاً
    if user_id_str == str(ADMIN_ID):
        return True
        
    try:
        if hasattr(database, 'db') and database.db:
            mod_doc = database.db.collection('moderators').document(user_id_str).get()
            if mod_doc.exists:
                return True
        if hasattr(database, 'is_admin_or_mod'):
            return database.is_admin_or_mod(user_id_str)
    except Exception as e:
        print(f"⚠️ Error checking moderator status: {e}")
    return False

if bot:
    @bot.message_handler(commands=['start'])
    def send_welcome(message):
        try:
            user_id = message.from_user.id
            print(f"👑 [Admin Bot] Received /start from: {user_id}")
            
            if not is_user_authorized(user_id):
                bot.reply_to(message, "⛔ عذراً، هذا البوت مخصص للإدارة والمشرفين المصرح لهم فقط.")
                return

            markup = InlineKeyboardMarkup()
            webapp = WebAppInfo(url=ADMIN_WEBAPP_URL)
            btn = InlineKeyboardButton(text="💻 فتح لوحة التحكم", web_app=webapp)
            markup.add(btn)

            bot.send_message(
                message.chat.id,
                "👑 <b>أهلاً بك يا مدير!</b>\n\nتم التحقق من صلاحياتك بنجاح، اضغط الزر أدناه لفتح لوحة التحكم:",
                reply_markup=markup,
                parse_mode="HTML"
            )
        except Exception as e:
            print(f"❌ Error in admin bot /start: {e}")

    @bot.message_handler(func=lambda message: True)
    def handle_all_messages(message):
        try:
            user_id = message.from_user.id
            if not is_user_authorized(user_id):
                bot.reply_to(message, "⛔ عذراً، البوت مخصص للإدارة والمشرفين المصرح لهم فقط.")
                return
            
            markup = InlineKeyboardMarkup()
            webapp = WebAppInfo(url=ADMIN_WEBAPP_URL)
            btn = InlineKeyboardButton(text="💻 فتح لوحة التحكم", web_app=webapp)
            markup.add(btn)

            bot.reply_to(
                message, 
                "ℹ️ يرجى استخدام زر 'فتح لوحة التحكم' للإدارة:",
                reply_markup=markup,
                parse_mode="HTML"
            )
        except Exception as e:
            print(f"❌ Error in admin handle_all_messages: {e}")

    @bot.callback_query_handler(func=lambda call: True)
    def handle_callback_query(call):
        try:
            user_id = call.from_user.id
            if not is_user_authorized(user_id):
                bot.answer_callback_query(call.id, "⛔ عذراً، البوت مخصص للإدارة فقط.", show_alert=True)
                return
        except Exception as e:
            print(f"❌ Error in admin callback: {e}")

# قفل أمان لمنع تكرار خيوط Polling عند تشغيل أكثر من Worker في Gunicorn
_polling_lock = threading.Lock()
_polling_started = False

def start_bot_polling():
    global _polling_started
    with _polling_lock:
        if _polling_started:
            return
        _polling_started = True

    if bot:
        print("🤖 بوت أزرار الأدمن قيد التشغيل المباشر...")
        try:
            bot.remove_webhook(drop_pending_updates=True)
            time.sleep(1)
            bot.infinity_polling(skip_pending=True, timeout=20, long_polling_timeout=10)
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
