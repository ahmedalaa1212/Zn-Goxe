import os
import sys
import time
import threading

# ضمان إضافة المسار الرئيسي للمشروع لمنع أخطاء الاستيراد (ImportError)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from flask import Flask, jsonify, send_from_directory, request
from flask_cors import CORS

import database
from core.security import get_authenticated_user

app = Flask(__name__)

# إعداد CORS للوصول إلى كافة مسارات API
CORS(app, resources={r"/api/*": {"origins": "*"}})

WEB_URL = os.environ.get('WEB_URL', 'https://admin-zn-production.up.railway.app').strip().rstrip('/')
ADMIN_ID = os.environ.get("ADMIN_ID", "5102387551").strip()

def is_admin_authorized(telegram_id):
    """فحص موحد: الأدمن الرئيسي له السلطة المطلقة دائماً"""
    if not telegram_id:
        return False
    
    if str(telegram_id).strip() == str(ADMIN_ID):
        return True
        
    try:
        return database.is_admin_or_mod(str(telegram_id).strip())
    except Exception as e:
        print(f"⚠️ Error checking admin status: {e}")
        return False

# ==========================================
# تسجيل المسارات (Blueprints)
# ==========================================

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
# مسارات إدارة اللعبة والداشبورد
# ==========================================

@app.route('/api/verify_admin', methods=['POST'])
def verify_admin_access():
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=True)
    if not success:
        return error_res

    if is_admin_authorized(telegram_id):
        role = "المدير العام (Owner)" if str(telegram_id).strip() == str(ADMIN_ID) else "مشرف"
        return jsonify({"success": True, "message": "تم التحقق بنجاح", "role": role}), 200
        
    return jsonify({"success": False, "error": "عذراً، البوت مخصص للإدارة فقط!"}), 403

@app.route('/api/admin/zn-go-settings', methods=['GET', 'POST'])
@app.route('/api/admin/settings/grid_36', methods=['GET', 'POST'])
def admin_zn_go_settings():
    is_post = (request.method == 'POST')
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=is_post)
    if not success:
        return error_res

    if not is_admin_authorized(telegram_id):
        return jsonify({"success": False, "error": "غير مصرح لك للوصول للإدارة"}), 403

    if request.method == 'GET':
        try:
            settings = database.get_game_settings() or {}
            zn_cfg = settings.get("zn_go_config") or settings.get("grid_game_config", {})
            stats = database.get_game_profit_stats()

            raw_target = float(zn_cfg.get("target_margin", 0.70))
            bot_profit = round(raw_target * 100.0 if raw_target <= 1.0 else raw_target, 2)
            player_profit = round(100.0 - bot_profit, 2)
            min_bet = float(zn_cfg.get("min_bet", 10.0))

            return jsonify({
                "success": True,
                "config": {
                    "bot_profit": bot_profit,
                    "bot_margin": bot_profit,
                    "player_profit": player_profit,
                    "player_margin": player_profit,
                    "min_bet": min_bet
                },
                "stats": stats
            }), 200
        except Exception as e:
            print(f"❌ Error reading ZN Go settings: {e}")
            return jsonify({"success": False, "error": "خطأ أثناء قراءة البيانات"}), 500

    elif request.method == 'POST':
        try:
            data = request.get_json() or {}
            bot_profit = data.get("bot_profit", data.get("bot_margin"))
            min_bet = data.get("min_bet")

            if bot_profit is None or min_bet is None:
                return jsonify({"success": False, "error": "يرجى تقديم كافة حقول البيانات المطلوب حفظها"}), 400

            bot_margin_val = float(bot_profit)
            min_bet_val = float(min_bet)

            ok = database.update_zn_go_config(
                min_bet=min_bet_val,
                target_margin=bot_margin_val / 100.0 if bot_margin_val > 1.0 else bot_margin_val
            )

            if ok:
                admin_name = user_info.get("first_name", f"Admin {telegram_id}") if isinstance(user_info, dict) else f"Admin {telegram_id}"
                database.log_admin_action(
                    admin_name,
                    f"تحديث إعدادات ZN Go: أرباح البوت {bot_margin_val}%، الحد الأدنى {min_bet_val}"
                )
                return jsonify({"success": True, "message": "تم حفظ إعدادات شبكة ZN Go بنجاح!"}), 200
            else:
                return jsonify({"success": False, "error": "فشل حفظ الإعدادات في الفايربيس"}), 500
        except Exception as e:
            print(f"❌ Error updating ZN Go settings: {e}")
            return jsonify({"success": False, "error": f"حدث خطأ أثناء التحديث: {str(e)}"}), 500

@app.route('/api/admin/settings/big_arena', methods=['GET', 'POST'])
def admin_big_arena_settings():
    is_post = (request.method == 'POST')
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=is_post)
    if not success:
        return error_res

    if not is_admin_authorized(telegram_id):
        return jsonify({"success": False, "error": "غير مصرح لك للوصول للإدارة"}), 403

    if request.method == 'GET':
        arena_cfg = database.get_arena_config()
        raw_target = float(arena_cfg.get("target_margin", 0.70))
        bot_margin = round(raw_target * 100.0 if raw_target <= 1.0 else raw_target, 2)
        return jsonify({
            "success": True,
            "config": {
                "bot_margin": bot_margin,
                "player_margin": round(100.0 - bot_margin, 2),
                "min_bet": float(arena_cfg.get("entry_fee", 10.0)),
                "enabled": True
            }
        }), 200

    elif request.method == 'POST':
        data = request.get_json() or {}
        bot_margin = data.get("bot_margin")
        min_bet = data.get("min_bet")

        ok = database.update_arena_config(
            entry_fee=min_bet,
            target_margin=bot_margin
        )
        if ok:
            return jsonify({"success": True, "message": "تم حفظ إعدادات الساحة الكبرى بنجاح!"}), 200
        return jsonify({"success": False, "error": "حدث خطأ أثناء حفظ بيانات الساحة"}), 500

@app.route('/api/admin/dashboard-stats', methods=['GET'])
def admin_dashboard_stats():
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=False)
    if not success:
        return error_res

    if not is_admin_authorized(telegram_id):
        return jsonify({"success": False, "error": "غير مصرح لك للوصول للإدارة"}), 403

    res = database.get_admin_dashboard_stats()
    return jsonify(res), 200

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

# ==========================================
# المسارات الخدمية وتوجيه الصفحات
# ==========================================

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

# ==========================================
# 🤖 تشغيل البوت تلقائياً في الخلفية مع الخادم
# ==========================================
bot_instance = None

def start_telegram_bot():
    global bot_instance
    try:
        import telebot
        from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

        BOT_TOKEN = os.environ.get("ADMIN_BOT_TOKEN") or os.environ.get("BOT_TOKEN")
        if not BOT_TOKEN:
            print("⚠️ لم يتم العثور على ADMIN_BOT_TOKEN في متغيرات البيئة!")
            return

        ADMIN_WEBAPP_URL = WEB_URL if WEB_URL.endswith('/admin') else f"{WEB_URL}/admin"
        bot = telebot.TeleBot(BOT_TOKEN)
        bot_instance = bot

        @bot.message_handler(commands=['start'])
        def send_welcome(message):
            try:
                user_id = str(message.from_user.id).strip()
                print(f"👑 [/start] Received from ID: {user_id}")
                
                if not is_admin_authorized(user_id):
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
                print(f"❌ Error handling /start: {e}")

        @bot.message_handler(func=lambda message: True)
        def handle_all_messages(message):
            try:
                user_id = str(message.from_user.id).strip()
                if not is_admin_authorized(user_id):
                    bot.reply_to(message, "⛔ عذراً، البوت مخصص للإدارة فقط.")
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
                print(f"❌ Error handling message: {e}")

        print("🤖 بدء تشغيل خيط البوت وتصفية التحديثات القديمة...")
        bot.remove_webhook(drop_pending_updates=True)
        time.sleep(1)
        bot.infinity_polling(skip_pending=True, timeout=20, long_polling_timeout=10)
    except Exception as e:
        print(f"⚠️ Bot Execution Error: {e}")

# بدء تشغيل خيط البوت عند إقلاع السيرفر
bot_thread = threading.Thread(target=start_telegram_bot, daemon=True)
bot_thread.start()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
