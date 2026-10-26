# -*- coding: utf-8 -*-
import os
import sys
import re
import html
import time
import socket
import threading
import requests
from concurrent.futures import ThreadPoolExecutor

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from flask import Flask, jsonify, send_from_directory, request
from flask_cors import CORS

import database
from core.security import get_authenticated_user

try:
    from wallet.withdraw.withdraw_api import execute_admin_decision
except Exception:
    execute_admin_decision = None

app = Flask(__name__, static_folder='.', static_url_path='')

CORS(app, resources={
    r"/api/*": {
        "origins": "*",
        "allow_headers": [
            "Content-Type",
            "Authorization",
            "X-Init-Data",
            "X-Telegram-Init-Data",
            "X-Device-Id",
            "X-Device-Fingerprint"
        ]
    }
})

WEB_URL = os.environ.get('WEB_URL', 'https://admin-zn-production.up.railway.app').strip().rstrip('/')
ADMIN_ID = os.environ.get("ADMIN_ID", "5102387551").strip()
ADMIN_BOT_TOKEN = os.environ.get("ADMIN_BOT_TOKEN") or os.environ.get("BOT_TOKEN")

# ذاكرة مؤقتة لصلاحيات المشرفين لتسريع الاستجابة ومنع الضغط على قاعدة البيانات
_AUTH_CACHE = {}
_AUTH_CACHE_LOCK = threading.Lock()
_AUTH_CACHE_TTL = 120

_active_tx_lock = threading.Lock()
_active_transactions = set()
_bot_executor = ThreadPoolExecutor(max_workers=20, thread_name_prefix="admin_app_bot_worker")


def is_admin_authorized(telegram_id):
    """فحص موحد مع كاش آمن: الأدمن الرئيسي له السلطة المطلقة دائماً"""
    if not telegram_id:
        return False

    user_id_str = str(telegram_id).strip()
    if user_id_str == str(ADMIN_ID):
        return True

    now = time.time()
    with _AUTH_CACHE_LOCK:
        if user_id_str in _AUTH_CACHE:
            cached_val, cached_ts = _AUTH_CACHE[user_id_str]
            if now - cached_ts < _AUTH_CACHE_TTL:
                return cached_val

    try:
        auth = bool(database.is_admin_or_mod(user_id_str))
        with _AUTH_CACHE_LOCK:
            _AUTH_CACHE[user_id_str] = (auth, now)
        return auth
    except Exception as e:
        print(f"⚠️ Error checking admin status: {e}")
        return False


# ==========================================
# 🤖 تشغيل بوت الأدمن في الخلفية (يدعم لوحة الإدارة + أزرار قبول ورفض السحب اليدوي)
# ==========================================
admin_bot = None
if ADMIN_BOT_TOKEN:
    import telebot
    from telebot import apihelper
    from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

    apihelper.SESSION_TIME_TO_LIVE = 5 * 60
    apihelper.CONNECT_TIMEOUT = 3.5
    apihelper.READ_TIMEOUT = 10

    admin_bot = telebot.TeleBot(ADMIN_BOT_TOKEN, threaded=True, num_threads=24)

    def _safe_edit_bot_message(chat_id, message_id, text, reply_markup=None):
        try:
            return admin_bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                parse_mode="HTML",
                reply_markup=reply_markup
            )
        except Exception as e:
            if "message is not modified" in str(e):
                return True
            try:
                plain_text = re.sub(r'<[^>]*>', '', text)
                return admin_bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=plain_text,
                    reply_markup=reply_markup
                )
            except Exception:
                return False

    def _make_copy_button(text, copy_value, tx_id=""):
        try:
            from telebot.types import CopyTextButton
            return InlineKeyboardButton(text, copy_text=CopyTextButton(text=str(copy_value)))
        except Exception:
            safe_cb = f"copy_addr_{tx_id or str(copy_value)[:32]}"
            return InlineKeyboardButton(text, callback_data=safe_cb[:64])

    @admin_bot.callback_query_handler(func=lambda call: call.data and (
        call.data.startswith('approve_tx_') or
        call.data.startswith('reject_tx_') or
        call.data.startswith('copy_addr_')
    ))
    def handle_admin_withdraw_callbacks(call):
        try:
            admin_bot.answer_callback_query(call.id)
        except Exception:
            pass
        _bot_executor.submit(_process_admin_callback_async, call)

    def _process_admin_callback_async(call):
        global execute_admin_decision
        cb_data = call.data or ""
        user_id = call.from_user.id
        chat_id = call.message.chat.id
        message_id = call.message.message_id
        orig_text = call.message.text or call.message.caption or ""

        if cb_data.startswith("copy_addr_"):
            match = re.search(r'(EQ|UQ|0:)[a-zA-Z0-9_-]{46,66}', orig_text)
            addr_part = match.group(0) if match else cb_data.replace("copy_addr_", "").strip()
            if not addr_part:
                addr_part = "غير متوفر"
            try:
                admin_bot.send_message(
                    chat_id,
                    f"📋 <b>عنوان المحفظة للنسخ المباشر:</b>\n<code>{html.escape(addr_part)}</code>",
                    parse_mode="HTML"
                )
            except Exception:
                pass
            return

        if not is_admin_authorized(user_id):
            try:
                admin_bot.send_message(chat_id, "⛔ <b>عذراً:</b> ليس لديك صلاحية لاتخاذ هذا القرار!", parse_mode="HTML")
            except Exception:
                pass
            return

        action = "approve" if cb_data.startswith("approve_tx_") else "reject"
        tx_id = cb_data.replace("approve_tx_", "").replace("reject_tx_", "").strip()

        with _active_tx_lock:
            if tx_id in _active_transactions:
                return
            _active_transactions.add(tx_id)

        try:
            clean_text = re.split(r'\n\n(?:النتيجة|⚠️|⏳)', orig_text)[0].strip()
            status_text = clean_text + "\n\n⏳ <b>جاري تحديث السجلات وتوثيق الطلب...</b>"
            _safe_edit_bot_message(chat_id, message_id, status_text, reply_markup=None)

            if execute_admin_decision is None:
                from wallet.withdraw.withdraw_api import execute_admin_decision as exec_fn
                execute_admin_decision = exec_fn

            success, result_msg = execute_admin_decision(tx_id, action, admin_id=user_id)
            safe_msg = html.escape(str(result_msg))

            if success:
                status_icon = "🟢" if action == "approve" else "🔴"
                final_text = f"{clean_text}\n\n<b>النتيجة ({status_icon}):</b>\n{safe_msg}"
                _safe_edit_bot_message(chat_id, message_id, final_text, reply_markup=None)
            else:
                error_notice = f"\n\n⚠️ <b>فشلت العملية:</b>\n{safe_msg}"
                match = re.search(r'(EQ|UQ|0:)[a-zA-Z0-9_-]{46,66}', clean_text)
                wallet_addr = match.group(0) if match else ""

                markup = InlineKeyboardMarkup()
                markup.row(
                    InlineKeyboardButton("قبول 🟢", callback_data=f"approve_tx_{tx_id}"),
                    InlineKeyboardButton("رفض 🔴", callback_data=f"reject_tx_{tx_id}")
                )
                if wallet_addr:
                    markup.row(_make_copy_button("📋 نسخ عنوان المحفظة", wallet_addr, tx_id=tx_id))

                _safe_edit_bot_message(chat_id, message_id, clean_text + error_notice, reply_markup=markup)
        except Exception as err:
            print(f"❌ خطأ أثناء معالجة قرار السحب في admin_app: {err}")
        finally:
            with _active_tx_lock:
                _active_transactions.discard(tx_id)

    @admin_bot.message_handler(commands=['start'])
    def send_welcome(message):
        try:
            user_id = message.from_user.id
            first_name = html.escape(message.from_user.first_name or "المستخدم")
            user_id_str = str(user_id).strip()

            print(f"🔍 [Admin Bot Check] Received /start from User ID: {user_id_str}")

            if not is_admin_authorized(user_id_str):
                unauthorized_msg = (
                    f"⛔ <b>تنبيه أمني مشدد | Access Denied</b>\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"⚠️ <b>عذراً {first_name}، محاولة دخول غير مصرح بها!</b>\n\n"
                    f"🆔 المعرف الخاص بك: <code>{user_id_str}</code>\n"
                    f"🔒 هذا البوت مخصص حصرياً للمالك والمشرفين المعتمدين في منصة <b>ZN Goxe</b>.\n\n"
                    f"<i>تم تسجيل محاولة الوصول في سجلات الأمان.</i>"
                )
                admin_bot.reply_to(message, unauthorized_msg, parse_mode="HTML")
                return

            role_label = "👑 <b>المدير العام للنظام (Owner)</b>" if user_id_str == str(ADMIN_ID) else "🛡️ <b>مشرف معتمد (Administrator)</b>"

            welcome_text = (
                f"⚡ <b>مرحباً بك في لوحة القيادة العليا | ZN Goxe</b> 🔥\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"أهلاً بك يا <b>{first_name}</b> 👋\n"
                f"الرتبة: {role_label}\n"
                f"حالة الاتصال: 🟢 <b>نشط ومؤمن بالكامل</b>\n\n"
                f"✨ <b>تم التحقق من صلاحياتك الأمنية بنجاح!</b>\n"
                f"يمكنك الآن متابعة تحليلات المستخدمين والتفاعل، إدارة نظام الحظر والأمان، والمشرفين عبر فتح لوحة التحكم المرفقة."
            )

            ADMIN_WEBAPP_URL = WEB_URL if WEB_URL.endswith('/admin') else f"{WEB_URL}/admin"

            markup = InlineKeyboardMarkup()
            webapp = WebAppInfo(url=ADMIN_WEBAPP_URL)
            btn = InlineKeyboardButton(text="💻 فتح لوحة التحكم الرئيسية ⚡", web_app=webapp)
            markup.add(btn)

            admin_bot.send_message(
                message.chat.id,
                welcome_text,
                reply_markup=markup,
                parse_mode="HTML"
            )
        except Exception as e:
            print(f"❌ Error replying to /start: {e}")

    @admin_bot.message_handler(func=lambda message: True)
    def handle_all_messages(message):
        try:
            user_id = message.from_user.id
            user_id_str = str(user_id).strip()

            if not is_admin_authorized(user_id_str):
                admin_bot.reply_to(
                    message,
                    "⛔ <b>وصول مرفوض:</b> لا تملك صلاحية لاستخدام أوامر هذا البوت.",
                    parse_mode="HTML"
                )
                return

            ADMIN_WEBAPP_URL = WEB_URL if WEB_URL.endswith('/admin') else f"{WEB_URL}/admin"

            markup = InlineKeyboardMarkup()
            webapp = WebAppInfo(url=ADMIN_WEBAPP_URL)
            btn = InlineKeyboardButton(text="💻 فتح لوحة التحكم ⚡", web_app=webapp)
            markup.add(btn)

            admin_bot.reply_to(
                message,
                "ℹ️ <b>يرجى الضغط على الزر أدناه للوصول المباشر إلى لوحة الإدارة:</b>",
                reply_markup=markup,
                parse_mode="HTML"
            )
        except Exception as e:
            print(f"❌ Error handling message: {e}")

    def force_delete_webhook():
        try:
            url = f"https://api.telegram.org/bot{ADMIN_BOT_TOKEN}/deleteWebhook?drop_pending_updates=true"
            res = requests.get(url, timeout=10)
            print(f"🔄 Webhook cleanup response: {res.json()}")
        except Exception as e:
            print(f"⚠️ Error resetting webhook: {e}")

    def acquire_polling_lock():
        """قفل مشترك لمنع تعارض Polling إذا كان admin_bot.py يعمل في نفس الحاوية"""
        try:
            lock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            lock_socket.bind(('127.0.0.1', 47823))
            return lock_socket
        except socket.error:
            print("⚠️ [Admin App Bot] عملية Polling تعمل بالفعل في Worker آخر.")
            return None

    def run_bot_worker():
        lock = acquire_polling_lock()
        if lock is None:
            return
        print("🚀 [Admin Bot Worker] جارٍ إزالة الـ Webhook القديم وبدء الاستماع...")
        force_delete_webhook()
        time.sleep(1)
        while True:
            try:
                admin_bot.infinity_polling(skip_pending=True, timeout=20, long_polling_timeout=10)
            except Exception as e:
                print(f"❌ Error in Admin Telegram Bot Polling: {e}")
                time.sleep(3)

    bot_thread = threading.Thread(target=run_bot_worker, daemon=True)
    bot_thread.start()

# ==========================================
# تسجيل المسارات (Blueprints)
# ==========================================

try:
    from users.users_api import users_bp
    app.register_blueprint(users_bp)
except Exception as e:
    print(f"⚠️ لم يتم تحميل module users: {e}")

try:
    from super_admin.super_admin_api import super_admin_bp
    app.register_blueprint(super_admin_bp, url_prefix='/api/super-admin')
except Exception as e:
    print(f"⚠️ لم يتم تحميل module super_admin: {e}")

try:
    from addons.addons_api import addons_bp
    app.register_blueprint(addons_bp)
except Exception as e:
    print(f"⚠️ لم يتم تحميل module addons: {e}")

try:
    from farm.farm_api import farm_bp
    app.register_blueprint(farm_bp, url_prefix='/api/farm')
except Exception as e:
    print(f"⚠️ لم يتم تحميل module farm: {e}")

try:
    from settings.settings_api import settings_bp
    app.register_blueprint(settings_bp, url_prefix='/api/settings')
except Exception as e:
    print(f"⚠️ لم يتم تحميل module settings: {e}")

try:
    try:
        from friends.friends_api import friends_bp
    except ImportError:
        from friends.friends_api import friends_api as friends_bp
    app.register_blueprint(friends_bp, url_prefix='/api/friends')
except Exception as e:
    print(f"⚠️ لم يتم تحميل module friends: {e}")

try:
    from games.games_api import games_bp
    app.register_blueprint(games_bp, url_prefix='/api/games')
except Exception as e:
    print(f"⚠️ لم يتم تحميل module games: {e}")

try:
    from tasks.tasks_api import tasks_bp
    app.register_blueprint(tasks_bp, url_prefix='/api/tasks')
except Exception as e:
    print(f"⚠️ لم يتم تحميل module tasks: {e}")

try:
    from shop.shop_api import shop_bp
    app.register_blueprint(shop_bp, url_prefix='/api/shop')
except Exception as e:
    print(f"⚠️ لم يتم تحميل module shop: {e}")

try:
    from wallet.wallet_api import wallet_bp
    app.register_blueprint(wallet_bp, url_prefix='/api/wallet')
except Exception as e:
    print(f"⚠️ لم يتم تحميل module wallet: {e}")

try:
    from support.support_api import support_bp
    app.register_blueprint(support_bp, url_prefix='/api/support')
except Exception as e:
    print(f"⚠️ لم يتم تحميل module support: {e}")

try:
    try:
        from admin_chat.admin_chat_api import admin_chat_bp
    except ImportError:
        from admin_chat.admin_chat_api import admin_chat_api as admin_chat_bp
    app.register_blueprint(admin_chat_bp, url_prefix='/api/admin-chat')
except Exception as e:
    print(f"⚠️ لم يتم تحميل module admin_chat: {e}")

# ==========================================
# مسارات إدارة الداشبورد والحماية العامة
# ==========================================

@app.route('/health')
def health_check():
    return jsonify({"status": "online", "bot": "Bot admin ZN Goxe"}), 200


@app.route('/api/verify_admin', methods=['POST'])
def verify_admin_access():
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=True)
    if not success:
        return error_res

    if is_admin_authorized(telegram_id):
        role = "المدير العام (Owner)" if str(telegram_id).strip() == str(ADMIN_ID) else "مشرف معتمد"
        return jsonify({"success": True, "message": "تم التحقق بنجاح", "role": role}), 200

    return jsonify({"success": False, "error": "عذراً، البوت مخصص للإدارة والمشرفين فقط!"}), 403


@app.route('/api/admin/withdraw/decision', methods=['POST'])
def admin_withdraw_decision_api():
    """مسار إضافي مؤمن لاتخاذ قرار القبول/الرفض مباشرة من لوحة التحكم إن لزم الأمر"""
    global execute_admin_decision
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=True)
    if not success:
        return error_res

    if not is_admin_authorized(telegram_id):
        return jsonify({"success": False, "error": "غير مصرح لك باتخاذ قرارات السحب"}), 403

    data = request.get_json(silent=True) or {}
    tx_id = str(data.get("tx_id", "")).strip()
    action = str(data.get("action", "")).strip().lower()

    if not tx_id or action not in ("approve", "reject"):
        return jsonify({"success": False, "error": "بيانات القرار غير مكتملة"}), 400

    if execute_admin_decision is None:
        from wallet.withdraw.withdraw_api import execute_admin_decision as exec_fn
        execute_admin_decision = exec_fn

    ok, msg = execute_admin_decision(tx_id, action, admin_id=telegram_id)
    return jsonify({"success": ok, "message": msg}), (200 if ok else 400)


@app.route('/api/admin/dashboard-stats', methods=['GET'])
def admin_dashboard_stats():
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=False)
    if not success:
        return error_res

    if not is_admin_authorized(telegram_id):
        return jsonify({"success": False, "error": "غير مصرح لك للوصول للإدارة"}), 403

    try:
        if hasattr(database, 'get_system_global_analytics'):
            res = database.get_system_global_analytics()
        else:
            res = database.get_admin_dashboard_stats()
        return jsonify({"success": True, "stats": res}), 200
    except Exception as e:
        print(f"❌ Error fetching dashboard stats: {e}")
        return jsonify({"success": False, "error": "خطأ أثناء جلب إحصائيات اللوحة"}), 500


@app.route('/api/moderators', methods=['GET', 'POST'])
@app.route('/api/moderators/<mod_id>', methods=['DELETE'])
def admin_moderators_manager(mod_id=None):
    is_post = (request.method in ['POST', 'DELETE'])
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=is_post)
    if not success:
        return error_res

    if not is_admin_authorized(telegram_id):
        return jsonify({"success": False, "error": "غير مصرح لك للوصول للإدارة"}), 403

    if request.method == 'GET':
        mods = database.get_moderators()
        return jsonify({"success": True, "moderators": mods}), 200

    elif request.method == 'POST':
        if str(telegram_id).strip() != str(ADMIN_ID):
            return jsonify({"success": False, "error": "عذراً، إضافة المشرفين مخصصة للمالك الرئيسي فقط!"}), 403

        data = request.get_json(silent=True) or {}
        m_id = data.get("id")
        m_name = data.get("name")
        perms = data.get("permissions", {})
        added_by = data.get("addedBy", "المدير العام")

        if not m_id or not m_name:
            return jsonify({"success": False, "error": "بيانات المشرف ناقصة"}), 400

        ok = database.add_moderator(m_id, m_name, perms, added_by)
        if ok:
            with _AUTH_CACHE_LOCK:
                _AUTH_CACHE.pop(str(m_id).strip(), None)
            return jsonify({"success": True, "message": "تمت إضافة المشرف بنجاح!"}), 200
        return jsonify({"success": False, "error": "حدث خطأ أثناء إضافة المشرف"}), 500

    elif request.method == 'DELETE':
        if str(telegram_id).strip() != str(ADMIN_ID):
            return jsonify({"success": False, "error": "عذراً، حذف المشرفين مخصص للمالك الرئيسي فقط!"}), 403

        if str(mod_id).strip() == str(ADMIN_ID):
            return jsonify({"success": False, "error": "لا يمكن حذف الأدمن الرئيسي للنظام!"}), 400

        deleted_by = request.args.get("deletedBy", "المدير العام")
        ok = database.delete_moderator(mod_id, deleted_by)
        if ok:
            with _AUTH_CACHE_LOCK:
                _AUTH_CACHE.pop(str(mod_id).strip(), None)
            return jsonify({"success": True, "message": "تم حذف المشرف بنجاح"}), 200
        return jsonify({"success": False, "error": "حدث خطأ أثناء حذف المشرف"}), 500


@app.route('/api/admin-logs', methods=['GET'])
def admin_logs_handler():
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=False)
    if not success:
        return error_res

    if not is_admin_authorized(telegram_id):
        return jsonify({"success": False, "error": "غير مصرح لك للوصول للإدارة"}), 403

    logs = database.get_admin_logs(limit=50)
    return jsonify({"success": True, "logs": logs}), 200


@app.route('/tonconnect-manifest.json')
def serve_tonconnect_manifest():
    try:
        return send_from_directory('.', 'tonconnect-manifest.json', mimetype='application/json')
    except Exception:
        return jsonify({"error": "Manifest file not found"}), 404


@app.route('/api/user/info', methods=['GET', 'POST'])
def get_user_info_main():
    is_post = (request.method == 'POST')
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=is_post)
    if not success:
        return error_res

    try:
        device_id = request.headers.get('X-Device-Id') or request.args.get('device_id')
        fingerprint = request.headers.get('X-Device-Fingerprint') or request.args.get('fingerprint')

        if hasattr(database, 'check_and_bind_device') and device_id:
            device_check = database.check_and_bind_device(telegram_id, device_id, fingerprint)
            if device_check and device_check.get("banned"):
                return jsonify({
                    "success": False,
                    "error": device_check.get("reason", "تم حظر الحساب والجهاز بسبب تعدد الحسابات"),
                    "banned": True
                }), 403

        if database.is_user_banned(telegram_id):
            return jsonify({"success": False, "error": "حسابك معطل حالياً", "banned": True}), 403

        user_data = database.get_user(telegram_id)
        if not user_data:
            first_name = user_info.get('first_name', 'لاعب') if isinstance(user_info, dict) else 'لاعب'
            ref_id = user_info.get('start_param') if isinstance(user_info, dict) else None
            database.init_user(telegram_id, ref_id=ref_id, first_name=first_name)
            user_data = database.get_user(telegram_id)

        return jsonify({"success": True, "user": user_data}), 200
    except Exception as e:
        print(f"❌ Error in get_user_info_main: {e}")
        return jsonify({"success": False, "error": "حدث خطأ أثناء جلب بيانات الحساب"}), 500


@app.after_request
def add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    if request.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response


@app.errorhandler(500)
def handle_500_error(e):
    return jsonify({"status": "error", "success": False, "error": "حدث خطأ داخلي في السيرفر"}), 500


@app.errorhandler(404)
def handle_404_error(e):
    if request.path.startswith('/api/'):
        return jsonify({"status": "error", "success": False, "error": "المسار غير موجود"}), 404
    return send_from_directory('.', 'admin.html')


@app.route('/')
@app.route('/admin')
@app.route('/admin.html')
def serve_admin():
    return send_from_directory('.', 'admin.html')


@app.route('/<path:path>')
def serve_static(path):
    path_clean = path.strip('/').lower()
    if '..' in path_clean or path_clean.startswith('.'):
        return jsonify({"error": "Access Denied"}), 403

    if path_clean in ['', 'admin', 'admin.html', 'index', 'index.html']:
        return send_from_directory('.', 'admin.html')

    allowed_extensions = (
        '.html', '.css', '.js', '.json', '.png', '.jpg',
        '.jpeg', '.gif', '.svg', '.webp', '.ico', '.woff',
        '.woff2', '.ttf', '.otf'
    )
    if not any(path_clean.endswith(ext) for ext in allowed_extensions):
        return jsonify({"error": "Access Denied"}), 403

    forbidden_files = (
        'firebase-adminsdk.json', 'config.json', 'credentials.json',
        'package.json', 'package-lock.json', 'requirements.txt', '.env'
    )
    if any(f in path_clean for f in forbidden_files):
        return jsonify({"error": "Access Denied"}), 403

    try:
        return send_from_directory('.', path)
    except Exception:
        return send_from_directory('.', 'admin.html')


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
