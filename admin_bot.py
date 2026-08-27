import os
import sys
import time
import threading
import requests
from flask import Flask, jsonify
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

# ضمان إضافة المسار الرئيسي للمشروع لمنع أخطاء الاستيراد
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
    
    # 👑 1. الأدمن الرئيسي له سلطة مطلقة مباشرة
    if user_id_str == str(ADMIN_ID):
        return True
        
    # 🛡️ 2. التحقق من قاعدة البيانات للمشرفين المعتمدين
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
        if not is_user_authorized(user_id):
            bot.answer_callback_query(call.id, "⛔ ليس لديك صلاحية لاتخاذ هذا القرار!", show_alert=True)
            return

        cb_data = call.data
        if cb_data.startswith("approve_tx_"):
            tx_id = cb_data.replace("approve_tx_", "")
            action = "approve"
        else:
            tx_id = cb_data.replace("reject_tx_", "")
            action = "reject"

        bot.answer_callback_query(call.id, "⏳ جاري تنفيذ الطلب...", show_alert=False)

        # استدعاء دالة تنفيذ القرار من ملف withdraw_api
        try:
            from wallet.withdraw.withdraw_api import execute_admin_decision
            success, result_msg = execute_admin_decision(tx_id, action)
            
            bot.answer_callback_query(call.id, result_msg, show_alert=True)
            
            if success:
                orig_text = call.message.text or call.message.caption or ""
                decision_badge = "\n\n✅ <b>تمت الموافقة والتحويل بنجاح!</b>" if action == "approve" else "\n\n❌ <b>تم رفض الطلب وإعادة الرصيد للمستخدم.</b>"
                
                bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text=orig_text + decision_badge,
                    parse_mode="HTML",
                    reply_markup=None
                )
        except Exception as exec_err:
            print(f"❌ خطأ عند تنفيذ قرار الأدمن: {exec_err}")
            bot.answer_callback_query(call.id, f"⚠️ حدث خطأ أثناء المعالجة: {str(exec_err)}", show_alert=True)

    except Exception as e:
        print(f"❌ خطأ في معالج الأزرار التفاعلية: {e}")
        try:
            bot.answer_callback_query(call.id, "حدث خطأ غير متوقع.", show_alert=True)
        except Exception:
            pass

@bot.message_handler(commands=['start'])
def send_welcome(message):
    try:
        user_id = message.from_user.id
        first_name = message.from_user.first_name or "المستخدم"
        user_id_str = str(user_id).strip()
        
        print(f"🔍 [Admin Bot Check] Received /start from User ID: {user_id_str}")
        
        if not is_user_authorized(user_id):
            unauthorized_msg = (
                f"⛔ <b>تنبيه أمني مشدد | Access Denied</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"⚠️ <b>عذراً {first_name}، محاولة دخول غير مصرح بها!</b>\n\n"
                f"🆔 المعرف الخاص بك: <code>{user_id_str}</code>\n"
                f"🔒 هذا البوت مخصص حصرياً للمالك والمشرفين المعتمدين في منصة <b>ZN Goxe</b>.\n\n"
                f"<i>تم تسجيل محاولة الوصول في سجلات الأمان.</i>"
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
            f"✨ <b>تم التحقق من صلاحياتك الأمنية بنجاح!</b>\n"
            f"يمكنك الآن التحكم بجميع إعدادات الألعاب، العمولات، الأرباح والمشرفين عبر فتح لوحة التحكم المرفقة."
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
        user_id_str = str(user_id).strip()

        if not is_user_authorized(user_id):
            bot.reply_to(
                message, 
                "⛔ <b>وصول مرفوض:</b> لا تملك صلاحية لاستخدام أوامر هذا البوت.",
                parse_mode="HTML"
            )
            return
        
        markup = InlineKeyboardMarkup()
        webapp = WebAppInfo(url=ADMIN_WEBAPP_URL)
        btn = InlineKeyboardButton(text="💻 فتح لوحة التحكم ⚡", web_app=webapp)
        markup.add(btn)

        bot.reply_to(
            message, 
            "ℹ️ <b>يرجى الضغط على الزر أدناه للوصول المباشر إلى لوحة الإدارة:</b>",
            reply_markup=markup,
            parse_mode="HTML"
        )
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

def run_bot_worker():
    """تشغيل الاستماع لرسائل تلجرام في خلفية النظام"""
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
# 4. تشغيل البوت تلقائياً عند تحميل السيرفر
# ==========================================
bot_thread = threading.Thread(target=run_bot_worker, daemon=True)
bot_thread.start()

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
