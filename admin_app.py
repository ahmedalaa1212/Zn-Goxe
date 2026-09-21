# admin_app.py
import os
import sys
import time
import threading
import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from flask import Flask, jsonify, send_from_directory, request
from flask_cors import CORS

import database
from core.security import get_authenticated_user

app = Flask(__name__, static_folder='.', static_url_path='')

CORS(app, resources={r"/api/*": {"origins": "*", "allow_headers": ["Content-Type", "Authorization", "X-Init-Data", "X-Device-Id", "X-Device-Fingerprint"]}})

WEB_URL = os.environ.get('WEB_URL', 'https://admin-zn-production.up.railway.app').strip().rstrip('/')
ADMIN_ID = os.environ.get("ADMIN_ID", "5102387551").strip()
ADMIN_BOT_TOKEN = os.environ.get("ADMIN_BOT_TOKEN") or os.environ.get("BOT_TOKEN")

def is_admin_authorized(telegram_id):
    """فحص موحد: الأدمن الرئيسي له السلطة المطلقة دائماً"""
    if not telegram_id:
        return False
    
    user_id_str = str(telegram_id).strip()
    if user_id_str == str(ADMIN_ID):
        return True
        
    try:
        return database.is_admin_or_mod(user_id_str)
    except Exception as e:
        print(f"⚠️ Error checking admin status: {e}")
        return False

# ==========================================
# 🤖 تشغيل بوت الأدمن في الخلفية لوصل لوحة الإدارة فقط
# ==========================================
admin_bot = None
if ADMIN_BOT_TOKEN:
    import telebot
    from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

    admin_bot = telebot.TeleBot(ADMIN_BOT_TOKEN)

    @admin_bot.message_handler(commands=['start'])
    def send_welcome(message):
        try:
            user_id = message.from_user.id
            first_name = message.from_user.first_name or "المستخدم"
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

    def run_bot_worker():
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

        data = request.get_json() or {}
        m_id = data.get("id")
        m_name = data.get("name")
        perms = data.get("permissions", {})
        added_by = data.get("addedBy", "المدير العام")

        if not m_id or not m_name:
            return jsonify({"success": False, "error": "بيانات المشرف ناقصة"}), 400

        ok = database.add_moderator(m_id, m_name, perms, added_by)
        if ok:
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
    except Exception as e:
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
    if path_clean in ['', 'admin', 'admin.html', 'index', 'index.html']:
        return send_from_directory('.', 'admin.html')
        
    allowed_extensions = ('.html', '.css', '.js', '.json', '.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.ico', '.woff', '.woff2', '.ttf', '.otf')
    if not any(path_clean.endswith(ext) for ext in allowed_extensions):
        return jsonify({"error": "Access Denied"}), 403
        
    forbidden_files = ('firebase-adminsdk.json', 'config.json', 'credentials.json', 'package.json', 'package-lock.json', 'requirements.txt')
    if any(f in path_clean for f in forbidden_files):
        return jsonify({"error": "Access Denied"}), 403
        
    try:
        return send_from_directory('.', path)
    except Exception:
        return send_from_directory('.', 'admin.html')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
