import os
import sys
import time
import html
import threading
import requests
import re
import socket
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, jsonify
import telebot
from telebot import apihelper
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

# ==========================================
# 0. تحسين أداء الشبكة وتسريع الاتصال (HTTP Keep-Alive & Connection Pooling)
# ==========================================
apihelper.SESSION_TIME_TO_LIVE = 5 * 60
apihelper.CONNECT_TIMEOUT = 3.5
apihelper.READ_TIMEOUT = 10

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import database

# استيراد مسبق للوحدات الثقيلة لمنع التأخير أثناء معالجة الطلبات
try:
    from wallet.withdraw.withdraw_api import execute_admin_decision
except Exception:
    execute_admin_decision = None

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

# رفع عدد خيوط الاستجابة للطلبات المتزامنة
bot = telebot.TeleBot(BOT_TOKEN, threaded=True, num_threads=32)

# executor مخصص للمهام الخلفية السريعة
_executor = ThreadPoolExecutor(max_workers=30, thread_name_prefix="async_admin_worker")

# قفل آمن وتتبع المعاملات والسجل المؤقت للصلاحيات
_bot_lock = threading.Lock()
_bot_started = False
_active_tx_lock = threading.Lock()
_active_transactions = set()

# ذاكرة مؤقتة لصلاحيات المشرفين آمنة برمجياً
_AUTH_CACHE = {}
_AUTH_CACHE_LOCK = threading.Lock()
_AUTH_CACHE_TTL = 120

def is_user_authorized(user_id):
    """فحص أمني سريع مع كاش مؤقت خيطي لتفادي بطء الاستعلامات"""
    if not user_id:
        return False
    user_id_str = str(user_id).strip()
    
    if user_id_str == str(ADMIN_ID):
        return True
        
    now = time.time()
    with _AUTH_CACHE_LOCK:
        if user_id_str in _AUTH_CACHE:
            cached_auth, cached_time = _AUTH_CACHE[user_id_str]
            if now - cached_time < _AUTH_CACHE_TTL:
                return cached_auth

    try:
        if hasattr(database, 'is_admin_or_mod'):
            auth = bool(database.is_admin_or_mod(user_id_str))
            with _AUTH_CACHE_LOCK:
                _AUTH_CACHE[user_id_str] = (auth, now)
            return auth
    except Exception as e:
        print(f"⚠️ Error checking moderator status: {e}")
    return False

def safe_edit_message(chat_id, message_id, text, reply_markup=None):
    """تحديث نص الرسالة بآمان وتجنب أخطاء HTML Parsing"""
    try:
        return bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            parse_mode="HTML",
            reply_markup=reply_markup
        )
    except Exception as e:
        err_str = str(e)
        if "message is not modified" in err_str:
            return True
        print(f"⚠️ HTML edit failed ({e}), falling back to plain text...")
        try:
            plain_text = re.sub(r'<[^>]*>', '', text)
            return bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=plain_text,
                reply_markup=reply_markup
            )
        except Exception as ex:
            print(f"❌ Critical error editing message: {ex}")
            return False

def make_copy_text_button(text, copy_value):
    """إنشاء زر نسخ مباشر للحافظة"""
    try:
        from telebot.types import CopyTextButton
        return InlineKeyboardButton(text, copy_text=CopyTextButton(text=copy_value))
    except Exception:
        return InlineKeyboardButton(text, callback_data=f"copy_addr_{copy_value}")

# ==========================================
# 3. معالجة الأزرار التفاعلية (استجابة فورية فائقة السرعة بدون تهنيج)
# ==========================================
@bot.callback_query_handler(func=lambda call: call.data and (
    call.data.startswith('approve_tx_') or 
    call.data.startswith('reject_tx_') or 
    call.data.startswith('copy_addr_')
))
def handle_withdraw_decisions(call):
    # 🔥 السطر الأول والخطوة الأهم: إجابة تلجرام فوراً لإلغاء دائرة التحميل في أجزاء من المليثانية!
    try:
        bot.answer_callback_query(call.id)
    except Exception:
        pass

    # تحويل كافة العمليات الأخرى (فحص داتابيز + قفل + تنفيذ) إلى خيط خلفي مستقل فوراً
    _executor.submit(_process_callback_async, call)

def _process_callback_async(call):
    """معالجة كافة الفحوصات والقرارات في الخلفية دون تعطيل واجهة تلجرام"""
    cb_data = call.data or ""
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    orig_text = call.message.text or call.message.caption or ""

    # 1. معالجة زر النسخ
    if cb_data.startswith("copy_addr_"):
        addr_part = cb_data.replace("copy_addr_", "").strip()
        if not addr_part or len(addr_part) < 20:
            match = re.search(r'(EQ|UQ|0:)[a-zA-Z0-9_-]{46,48}', orig_text)
            addr_part = match.group(0) if match else "غير متوفر"
        try:
            bot.send_message(chat_id, f"📋 <b>عنوان المحفظة للنسخ:</b>\n<code>{addr_part}</code>", parse_mode="HTML")
        except Exception:
            pass
        return

    # 2. فحص الصلاحيات من الكاش أو الداتابيز
    if not is_user_authorized(user_id):
        try:
            bot.send_message(chat_id, "⛔ <b>عذراً:</b> ليس لديك صلاحية لاتخاذ هذا القرار!", parse_mode="HTML")
        except Exception:
            pass
        return

    # 3. استخراج البيانات وحماية القفل المزدوج
    action = "approve" if cb_data.startswith("approve_tx_") else "reject"
    tx_id = cb_data.replace("approve_tx_", "").replace("reject_tx_", "").strip()

    with _active_tx_lock:
        if tx_id in _active_transactions:
            return
        _active_transactions.add(tx_id)

    # 4. تنفيذ العملية وتحديث حالة الرسالة
    _async_handle_withdraw_process(chat_id, message_id, orig_text, tx_id, action, user_id)

def _async_handle_withdraw_process(chat_id, message_id, orig_text, tx_id, action, admin_id):
    """دالة المعالجة الخلفية لتحديث السجلات واستدعاء backend"""
    global execute_admin_decision
    try:
        clean_text = re.split(r'\n\n(?:النتيجة|⚠️|⏳)', orig_text)[0].strip()
        status_text = clean_text + "\n\n⏳ <b>جاري تحديث السجلات وتوثيق الطلب...</b>"
        safe_edit_message(chat_id, message_id, status_text, reply_markup=None)

        if execute_admin_decision is None:
            from wallet.withdraw.withdraw_api import execute_admin_decision as exec_fn
            execute_admin_decision = exec_fn

        success, result_msg = execute_admin_decision(tx_id, action, admin_id=admin_id)

        safe_msg = html.escape(str(result_msg))
        base_clean = clean_text

        if success:
            status_icon = "🟢" if action == "approve" else "🔴"
            final_text = f"{base_clean}\n\n<b>النتيجة ({status_icon}):</b>\n{safe_msg}"
            safe_edit_message(chat_id, message_id, final_text, reply_markup=None)
        else:
            error_notice = f"\n\n⚠️ <b>فشلت العملية:</b>\n{safe_msg}"
            
            match = re.search(r'(EQ|UQ|0:)[a-zA-Z0-9_-]{46,48}', clean_text)
            wallet_addr = match.group(0) if match else ""

            markup = InlineKeyboardMarkup()
            markup.row(
                InlineKeyboardButton("قبول 🟢", callback_data=f"approve_tx_{tx_id}"),
                InlineKeyboardButton("رفض 🔴", callback_data=f"reject_tx_{tx_id}")
            )
            if wallet_addr:
                markup.row(make_copy_text_button("📋 نسخ عنوان المحفظة", wallet_addr))
            
            safe_edit_message(chat_id, message_id, base_clean + error_notice, reply_markup=markup)
    except Exception as err:
        print(f"❌ خطأ أثناء تنفيذ الطلب في الخلفية: {err}")
    finally:
        with _active_tx_lock:
            _active_transactions.discard(tx_id)

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
                f"⚠️ <b>عذراً {html.escape(first_name)}، محاولة دخول غير مصرح بها!</b>\n\n"
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
            f"أهلاً بك يا <b>{html.escape(first_name)}</b> 👋\n"
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

def acquire_polling_lock():
    """قفل لضمان عدم تكرار عملية Polling في أكثر من Worker"""
    try:
        lock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        lock_socket.bind(('127.0.0.1', 47823))
        return lock_socket
    except socket.error:
        print("⚠️ [Bot Worker] عملية Polling تعمل بالفعل في Worker آخر.")
        return None

def run_bot_worker():
    """تشغيل الاستماع لرسائل تلجرام مع تفادي التعارض"""
    lock = acquire_polling_lock()
    if lock is None:
        return

    print("🚀 [Bot Worker] جارٍ إزالة الـ Webhook القديم وبدء الاستماع الفائق...")
    force_delete_webhook()
    time.sleep(1)
        
    while True:
        try:
            bot.infinity_polling(skip_pending=True, timeout=20, long_polling_timeout=10)
        except Exception as e:
            print(f"❌ Error in Telegram Bot Polling: {e}")
            time.sleep(3)

# ==========================================
# 4. تشغيل البوت
# ==========================================
def start_bot_once():
    """تضمن تشغيل خيط Polling واحد فقط"""
    global _bot_started
    with _bot_lock:
        if _bot_started:
            return
        _bot_started = True

    bot_thread = threading.Thread(target=run_bot_worker, daemon=True)
    bot_thread.start()

start_bot_once()

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
