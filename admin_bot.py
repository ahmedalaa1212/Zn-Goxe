import os
import sys
import time
import threading
import requests
from flask import Flask, jsonify
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import database

# ==========================================
# 1. إعداد خادم Web خفيف لإبقاء Railway نشطاً (Online)
# ==========================================
app = Flask(__name__)

@app.route('/')
@app.route('/health')
def health_check():
    return jsonify({"status": "online", "bot": "Bot admin ZN Goxe"}), 200

# ==========================================
# 2. جلب متغيرات البيئة وإعداد البوت
# ==========================================
BOT_TOKEN = os.environ.get("ADMIN_BOT_TOKEN") or os.environ.get("BOT_TOKEN")
ADMIN_ID = os.environ.get("ADMIN_ID", "5102387551").strip()

BASE_URL = os.environ.get("WEB_URL", "https://admin-zn-production.up.railway.app").strip().rstrip('/')
ADMIN_WEBAPP_URL = BASE_URL if BASE_URL.endswith('/admin') else f"{BASE_URL}/admin"

if not BOT_TOKEN:
    print("❌ خطأ قاتل: لم يتم العثور على ADMIN_BOT_TOKEN في متغيرات البيئة!")
    sys.exit(1)

bot = telebot.TeleBot(BOT_TOKEN)

def is_user_authorized(user_id):
    """فحص أمني دقيق وصارم لصلاحيات المستخدم"""
    if not user_id:
        return False
    user_id_str = str(user_id).strip()
    
    if user_id_str == str(ADMIN_ID):
        return True
        
    try:
        if hasattr(database, 'is_admin_or_mod'):
            return database.is_admin_or_mod(user_id_str)
    except Exception as e:
        print(f"⚠️ Error checking moderator status: {e}")
    return False

# ==========================================
# 3. معالجة الأزرار التفاعلية (Approval / Rejection)
# ==========================================
@bot.callback_query_handler(func=lambda call: call.data and (call.data.startswith('approve_tx_') or call.data.startswith('reject_tx_')))
def handle_withdraw_decisions(call):
    try:
        user_id = call.from_user.id
        cb_id = call.id
        cb_data = call.data

        # 1. الرد الفوري على تلجرام لإلغاء حالة التحميل (Spinning) فوراً
        try:
            bot.answer_callback_query(cb_id, "⏳ جاري تنفيذ الطلب...", show_alert=False)
        except Exception as e:
            print(f"⚠️ answer_callback_query error: {e}")

        # 2. التحقق من الصلاحية
        if not is_user_authorized(user_id):
            try:
                bot.send_message(call.message.chat.id, f"⛔ عذراً، ليس لديك صلاحية لاتخاذ هذا القرار!")
            except Exception:
                pass
            return

        action = "approve" if cb_data.startswith("approve_tx_") else "reject"
        tx_id = cb_data.replace("approve_tx_", "").replace("reject_tx_", "").strip()

        # 3. تشغيل المعالجة والتحويل في Thread خلفي لمنع تجميد البوت
        def process_in_background():
            try:
                from wallet.withdraw.withdraw_api import execute_admin_decision
                success, result_msg = execute_admin_decision(tx_id, action)

                orig_text = call.message.text or call.message.caption or ""
                
                if success:
                    status_badge = "\n\n✅ <b>تمت الموافقة والتحويل بنجاح!</b>" if action == "approve" else "\n\n❌ <b>تم رفض الطلب وإعادة الرصيد للمستخدم.</b>"
                    final_text = orig_text + status_badge
                else:
                    final_text = orig_text + f"\n\n⚠️ <b>تنبيه:</b> {result_msg}"

                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text=final_text,
                    parse_mode="HTML",
                    reply_markup=None
                )
            except Exception as exec_err:
                print(f"❌ خطأ عند تنفيذ قرار الأدمن: {exec_err}")
                try:
                    bot.send_message(call.message.chat.id, f"⚠️ حدث خطأ أثناء المعالجة: {str(exec_err)}")
                except Exception:
                    pass

        threading.Thread(target=process_in_background, daemon=True).start()

    except Exception as e:
        print(f"❌ خطأ في معالج الأزرار التفاعلية: {e}")

@bot.message_handler(commands=['start'])
def send_welcome(message):
    try:
        user_id = message.from_user.id
        first_name = message.from_user.first_name or "المستخدم"
        user_id_str = str(user_id).strip()
        
        if not is_user_authorized(user_id):
            unauthorized_msg = (
                f"⛔ <b>تنبيه أمني مشدد | Access Denied</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"⚠️ <b>عذراً {first_name}، محاولة دخول غير مصرح بها!</b>\n\n"
                f"🆔 المعرف الخاص بك: <code>{user_id_str}</code>\n"
                f"🔒 هذا البوت مخصص حصرياً للمالك والمشرفين المعتمدين في منصة <b>ZN Goxe</b>."
            )
            bot.reply_to(message, unauthorized_msg, parse_mode="HTML")
            return

        role_label = "👑 <b>المدير العام للنظام (Owner)</b>" if user_id_str == str(ADMIN_ID) else "🛡️ <b>مشرف معتمد (Administrator)</b>"
        
        welcome_text = (
            f"⚡ <b>مرحباً بك في لوحة القيادة العليا | ZN Goxe</b> 🔥\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"أهلاً بك يا <b>{first_name}</b> 👋\n"
            f"الرتبة: {role_label}\n"
            f"حالة الاتصال: 🟢 <b>نشط ومؤمن بالكامل</b>\n\n"
            f"✨ <b>تم التحقق من صلاحياتك الأمنية بنجاح!</b>"
        )

        markup = InlineKeyboardMarkup()
        webapp = WebAppInfo(url=ADMIN_WEBAPP_URL)
        btn = InlineKeyboardButton(text="💻 فتح لوحة التحكم الرئيسية ⚡", web_app=webapp)
        markup.add(btn)

        bot.send_message(
            message.chat.id,
            welcome_text,
            reply_markup=markup,
            parse_mode="HTML"
        )
    except Exception as e:
        print(f"❌ Error replying to /start: {e}")

@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    try:
        user_id = message.from_user.id

        if not is_user_authorized(user_id):
            bot.reply_to(message, "⛔ <b>وصول مرفوض:</b> لا تملك صلاحية لاستخدام أوامر هذا البوت.", parse_mode="HTML")
            return
        
        markup = InlineKeyboardMarkup()
        webapp = WebAppInfo(url=ADMIN_WEBAPP_URL)
        btn = InlineKeyboardButton(text="💻 فتح لوحة التحكم ⚡", web_app=webapp)
        markup.add(btn)

        bot.reply_to(message, "ℹ️ <b>يرجى الضغط على الزر أدناه للوصول المباشر إلى لوحة الإدارة:</b>", reply_markup=markup, parse_mode="HTML")
    except Exception as e:
        print(f"❌ Error handling message: {e}")

def force_delete_webhook():
    """حذف أي Webhook معلق فوراً عبر HTTP المباشر"""
    try:
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook?drop_pending_updates=true"
        res = requests.get(url, timeout=10)
        print(f"🔄 Webhook cleanup response: {res.json()}")
    except Exception as e:
        print(f"⚠️ Error resetting webhook: {e}")

BOT_STARTED = False

def run_bot_worker():
    """تشغيل الاستماع لرسائل تلجرام في خلفية النظام لمرة واحدة فقط"""
    global BOT_STARTED
    if BOT_STARTED:
        return
    BOT_STARTED = True

    print("🚀 [Bot Worker] جارٍ إزالة الـ Webhook القديم وبدء الاستماع...")
    force_delete_webhook()
    time.sleep(1)
        
    while True:
        try:
            bot.infinity_polling(skip_pending=True, timeout=20, long_polling_timeout=10)
        except Exception as e:
            print(f"❌ Error in Telegram Bot Polling: {e}")
            time.sleep(3)

# ==========================================
# 4. تشغيل البوت تلقائياً بطريقة آمنة
# ==========================================
bot_thread = threading.Thread(target=run_bot_worker, daemon=True)
bot_thread.start()

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
