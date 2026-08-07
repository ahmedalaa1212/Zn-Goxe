import os
import json
import hmac
import hashlib
import urllib.parse
from functools import wraps
from flask import Flask, jsonify, send_from_directory, request
from flask_cors import CORS

import database

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, static_folder=BASE_DIR)

# إعداد CORS بالسماح للوحة الأدمن بالوصول لكافة المسارات
CORS(app, resources={r"/api/*": {"origins": "*"}})

BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = os.environ.get("ADMIN_ID", "5102387551")

# تسجيل blueprint شات الإدارة إن وجد
try:
    from admin_chat.admin_chat_api import admin_chat_bp
    app.register_blueprint(admin_chat_bp, url_prefix='/api/admin/chat')
    print("✅ تم تسجيل API الدردشة والدعم بنجاح")
except Exception as e:
    print(f"⚠️ لم يتم تسجيل admin_chat_bp: {e}")

# ==========================================
# 🛡️ دالة التحقق الأمني الرقمي لبيانات تليجرام (InitData)
# ==========================================
def validate_telegram_admin(init_data):
    if not init_data or not BOT_TOKEN:
        return None
    try:
        parsed_data = dict(urllib.parse.parse_qsl(init_data))
        hash_from_telegram = parsed_data.pop('hash', None)
        if not hash_from_telegram:
            return None
        
        data_check_string = '\n'.join([f"{k}={v}" for k, v in sorted(parsed_data.items())])
        secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        
        if calculated_hash == hash_from_telegram:
            user_data = json.loads(parsed_data.get('user', '{}'))
            user_id = str(user_data.get('id'))
            
            # 1. فحص هل هو المدير الرئيسي المباشر (Owner)
            if user_id == str(ADMIN_ID):
                return {"user": user_data, "role": "المدير العام", "is_owner": True, "telegram_id": user_id}
                
            # 2. فحص حي ومباشر في الفايربيس لو هو مشرف حالي ونشط
            if hasattr(database, 'db') and database.db:
                mod_doc = database.db.collection('moderators').document(user_id).get()
                if mod_doc.exists:
                    mod_data = mod_doc.to_dict() or {}
                    return {"user": user_data, "role": "مشرف", "is_owner": False, "permissions": mod_data.get('permissions', {}), "telegram_id": user_id}
                    
        return None
    except Exception as e:
        print(f"❌ Auth Error: {e}")
        return None


def require_telegram_admin(f):
    """ديكوريتور صارم لحماية جميع مسارات API المخصصة للأدمن فقط"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        init_data = request.headers.get('X-Telegram-Init-Data') or (request.get_json(silent=True) or {}).get('initData')
        auth_info = validate_telegram_admin(init_data)
        
        if auth_info:
            request.telegram_user = auth_info
            return f(*args, **kwargs)

        # ⛔ حظر صارم: أي حساب غير موجود في الفايربيس يرفض فوراً بـ 403
        return jsonify({"status": "error", "success": False, "message": "⛔ عذراً، الوصول مقتصر فقط على الإدارة والمشرفين المصرح لهم حالياً!"}), 403
    return decorated_function

# ==========================================
# دالة مساعدة لجلب البيانات المباشرة
# ==========================================
def _fetch_arena_current_stats():
    """جلب إحصائيات arena/current مباشرة من Firestore"""
    try:
        if hasattr(database, 'db') and database.db:
            doc_ref = database.db.collection('arena').document('current')
            doc = doc_ref.get()
            if doc.exists:
                return doc.to_dict()
    except Exception as e:
        print(f"⚠️ Error fetching arena/current doc: {e}")
    return {}

def _serve_admin_ui():
    """البحث المباشر عن ملف الواجهة لتفادي 404"""
    possible_targets = [
        (BASE_DIR, 'admin.html'),
        (BASE_DIR, 'super_admin.html'),
        (os.path.join(BASE_DIR, 'super_admin'), 'super_admin.html'),
        (os.path.join(BASE_DIR, 'super_admin'), 'admin.html'),
        (os.path.join(BASE_DIR, 'templates'), 'super_admin.html'),
        (os.path.join(BASE_DIR, 'templates'), 'admin.html'),
    ]
    for directory, filename in possible_targets:
        if os.path.isfile(os.path.join(directory, filename)):
            return send_from_directory(directory, filename)
    return None

# ==========================================
# مسارات التوثيق وإحصائيات الأدمن (Super Admin APIs)
# ==========================================

@app.route('/api/verify_admin', methods=['POST'])
def verify_admin_access():
    """التحقق المباشر والصارم من هويّة الأدمن وصلاحيات الدخول من التليجرام"""
    req_json = request.get_json(silent=True) or {}
    init_data = request.headers.get('X-Telegram-Init-Data') or req_json.get('initData')
    
    auth_info = validate_telegram_admin(init_data)
    
    if auth_info:
        return jsonify({
            "success": True,
            "role": auth_info["role"],
            "telegram_id": auth_info["telegram_id"],
            "user": auth_info["user"],
            "permissions": auth_info.get("permissions", {})
        }), 200

    return jsonify({
        "success": False,
        "message": "⛔ تم رفض الدخول! حسابك غير مصرح له بدخول لوحة التحكم الإدارية."
    }), 403


@app.route('/api/admin/dashboard-stats', methods=['GET'])
@require_telegram_admin
def admin_dashboard_stats():
    """تزويد لوحة الإدارة بأرقام أرباح البوت والأرباح الفعلية والإعدادات المستقلة للألعاب"""
    try:
        arena_data = _fetch_arena_current_stats()
        stats_summary = database.get_game_profit_stats() or {} if hasattr(database, 'get_game_profit_stats') else {}

        grid_36_cfg = database.get_grid_36_config() if hasattr(database, 'get_grid_36_config') else {}
        big_arena_cfg = database.get_big_arena_config() if hasattr(database, 'get_big_arena_config') else {}

        total_bets = float(arena_data.get('total_bets', stats_summary.get('global_total_bets', 0.0)))
        total_payouts = float(arena_data.get('total_payouts', stats_summary.get('global_total_wins', 0.0)))
        
        bot_profit = round(max(0.0, total_bets - total_payouts), 2)
        user_profit = round(total_payouts, 2)
        
        actual_bot_percent = 0.0
        if total_bets > 0:
            actual_bot_percent = round(((total_bets - total_payouts) / total_bets) * 100.0, 1)

        return jsonify({
            "status": "success",
            "success": True,
            "grid_36": grid_36_cfg,
            "big_arena": big_arena_cfg,
            "stats": {
                "total_bot_profit": bot_profit,
                "total_wins": user_profit,
                "total_user_profit": user_profit,
                "actual_bot_percent": actual_bot_percent,
                "actual_margin": actual_bot_percent
            }
        }), 200
    except Exception as e:
        print(f"❌ Error fetching dashboard stats: {e}")
        return jsonify({"status": "error", "message": "حدث خطأ أثناء جلب بيانات لوحة التحكم"}), 500

# ==========================================
# 🆕 مسارات الإعدادات المنفصلة لكل لعبة (Endpoints)
# ==========================================

@app.route('/api/admin/settings/grid_36', methods=['GET', 'POST'])
@require_telegram_admin
def manage_grid_36_settings():
    """مسار قراءة وتحديث إعدادات لعبة شبكة الـ 36"""
    if request.method == 'GET':
        try:
            cfg = database.get_grid_36_config() if hasattr(database, 'get_grid_36_config') else {}
            bot_margin = float(cfg.get('bot_margin', 70.0))
            player_margin = round(max(0.0, 100.0 - bot_margin), 2)
            min_bet = float(cfg.get('min_bet', 10.0))
            enabled = bool(cfg.get('enabled', True))

            return jsonify({
                "status": "success",
                "success": True,
                "config": {
                    "bot_margin": bot_margin,
                    "player_margin": player_margin,
                    "min_bet": min_bet,
                    "enabled": enabled
                }
            }), 200
        except Exception as e:
            print(f"❌ Error fetching grid_36 config: {e}")
            return jsonify({"status": "error", "success": False, "message": "حدث خطأ أثناء جلب إعدادات شبكة الـ 36"}), 500

    elif request.method == 'POST':
        try:
            req_data = request.get_json(silent=True) or {}
            bot_margin = req_data.get('bot_margin')
            min_bet = req_data.get('min_bet')
            enabled = req_data.get('enabled', True)

            if bot_margin is None or min_bet is None:
                return jsonify({"status": "error", "success": False, "message": "يرجى تحديد أرباح البوت والحد الأدنى للرهان"}), 400

            bot_margin = float(bot_margin)
            min_bet = float(min_bet)
            enabled = bool(enabled)

            if bot_margin < 0 or bot_margin > 100:
                return jsonify({"status": "error", "success": False, "message": "نسبة أرباح البوت يجب أن تكون بين 0 و 100"}), 400

            if hasattr(database, 'update_grid_36_config'):
                database.update_grid_36_config(bot_margin=bot_margin, min_bet=min_bet, enabled=enabled)

            return jsonify({"status": "success", "success": True, "message": "تم تحديث إعدادات شبكة الـ 36 بنجاح"}), 200
        except Exception as e:
            print(f"❌ Error updating grid_36 config: {e}")
            return jsonify({"status": "error", "success": False, "message": "حدث خطأ أثناء حفظ إعدادات شبكة الـ 36"}), 500


@app.route('/api/admin/settings/big_arena', methods=['GET', 'POST'])
@require_telegram_admin
def manage_big_arena_settings():
    """مسار قراءة وتحديث إعدادات لعبة الساحة الكبرى"""
    if request.method == 'GET':
        try:
            cfg = database.get_big_arena_config() if hasattr(database, 'get_big_arena_config') else {}
            bot_margin = float(cfg.get('bot_margin', 70.0))
            player_margin = round(max(0.0, 100.0 - bot_margin), 2)
            min_bet = float(cfg.get('min_bet', 10.0))
            enabled = bool(cfg.get('enabled', True))

            return jsonify({
                "status": "success",
                "success": True,
                "config": {
                    "bot_margin": bot_margin,
                    "player_margin": player_margin,
                    "min_bet": min_bet,
                    "enabled": enabled
                }
            }), 200
        except Exception as e:
            print(f"❌ Error fetching big_arena config: {e}")
            return jsonify({"status": "error", "success": False, "message": "حدث خطأ أثناء جلب إعدادات الساحة الكبرى"}), 500

    elif request.method == 'POST':
        try:
            req_data = request.get_json(silent=True) or {}
            bot_margin = req_data.get('bot_margin')
            min_bet = req_data.get('min_bet')
            enabled = req_data.get('enabled', True)

            if bot_margin is None or min_bet is None:
                return jsonify({"status": "error", "success": False, "message": "يرجى تحديد أرباح البوت والحد الأدنى للرهان"}), 400

            bot_margin = float(bot_margin)
            min_bet = float(min_bet)
            enabled = bool(enabled)

            if bot_margin < 0 or bot_margin > 100:
                return jsonify({"status": "error", "success": False, "message": "نسبة أرباح البوت يجب أن تكون بين 0 و 100"}), 400

            if hasattr(database, 'update_big_arena_config'):
                database.update_big_arena_config(bot_margin=bot_margin, min_bet=min_bet, enabled=enabled)

            return jsonify({"status": "success", "success": True, "message": "تم تحديث إعدادات الساحة الكبرى بنجاح"}), 200
        except Exception as e:
            print(f"❌ Error updating big_arena config: {e}")
            return jsonify({"status": "error", "success": False, "message": "حدث خطأ أثناء حفظ إعدادات الساحة الكبرى"}), 500


# ==========================================
# مسارات المشرفين واللوجات (Moderators & Admin Logs)
# ==========================================

@app.route('/api/moderators', methods=['GET', 'POST'])
@require_telegram_admin
def manage_moderators():
    telegram_id = request.telegram_user.get('telegram_id', 'unknown')
    if request.method == 'GET':
        try:
            moderators = database.get_moderators() if hasattr(database, 'get_moderators') else []
            return jsonify({"status": "success", "success": True, "moderators": moderators}), 200
        except Exception as e:
            print(f"❌ Error fetching moderators: {e}")
            return jsonify({"status": "error", "success": False, "error": "حدث خطأ أثناء جلب قائمة المشرفين"}), 500

    elif request.method == 'POST':
        try:
            data = request.get_json(silent=True) or {}
            mod_id = data.get('id')
            mod_name = data.get('name')
            permissions = data.get('permissions', {})

            if not mod_id or not mod_name:
                return jsonify({"status": "error", "success": False, "error": "يرجى تحديد المعرف والاسم للمشرف"}), 400

            if hasattr(database, 'add_moderator'):
                database.add_moderator(mod_id, mod_name, permissions, added_by=telegram_id)

            return jsonify({"status": "success", "success": True, "message": "تمت إضافة المشرف بنجاح"}), 200
        except Exception as e:
            print(f"❌ Error adding moderator: {e}")
            return jsonify({"status": "error", "success": False, "error": "حدث خطأ أثناء إضافة المشرف"}), 500


@app.route('/api/moderators/<mod_id>', methods=['DELETE'])
@require_telegram_admin
def delete_moderator_route(mod_id):
    try:
        telegram_id = request.telegram_user.get('telegram_id', 'unknown')
        if hasattr(database, 'delete_moderator'):
            database.delete_moderator(mod_id, deleted_by=telegram_id)
        return jsonify({"status": "success", "success": True, "message": "تم حذف المشرف بنجاح"}), 200
    except Exception as e:
        print(f"❌ Error deleting moderator {mod_id}: {e}")
        return jsonify({"status": "error", "success": False, "error": "حدث خطأ أثناء حذف المشرف"}), 500


@app.route('/api/admin-logs', methods=['GET'])
@require_telegram_admin
def get_admin_logs_route():
    try:
        logs = database.get_admin_logs() if hasattr(database, 'get_admin_logs') else []
        return jsonify({"status": "success", "success": True, "logs": logs}), 200
    except Exception as e:
        print(f"❌ Error fetching admin logs: {e}")
        return jsonify({"status": "error", "success": False, "error": "حدث خطأ أثناء جلب السجلات"}), 500


# ==========================================
# الأمان ومعالجة الملفات الثابتة والواجهة
# ==========================================

@app.after_request
def add_security_headers(response):
    if request.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response

@app.errorhandler(500)
def handle_500_error(e):
    return jsonify({"status": "error", "success": False, "error": "حدث خطأ داخلي في سيرفر الإدارة"}), 500

@app.errorhandler(404)
def handle_404_error(e):
    if request.path.startswith('/api/'):
        return jsonify({"status": "error", "success": False, "error": "مسار الإدارة غير موجود"}), 404
    
    ui_res = _serve_admin_ui()
    if ui_res:
        return ui_res
    return jsonify({"status": "error", "success": False, "error": "الصفحة غير موجودة"}), 404

@app.route('/')
def serve_index():
    ui_res = _serve_admin_ui()
    if ui_res:
        return ui_res
    return jsonify({"status": "error", "message": "لم يتم العثور على ملف الواجهة"}), 404

@app.route('/<path:path>')
def serve_static(path):
    target_path = os.path.join(BASE_DIR, path)
    if os.path.isfile(target_path):
        return send_from_directory(BASE_DIR, path)
    
    super_admin_dir = os.path.join(BASE_DIR, 'super_admin')
    if os.path.isfile(os.path.join(super_admin_dir, path)):
        return send_from_directory(super_admin_dir, path)

    templates_dir = os.path.join(BASE_DIR, 'templates')
    if os.path.isfile(os.path.join(templates_dir, path)):
        return send_from_directory(templates_dir, path)

    if not path.startswith('api/'):
        ui_res = _serve_admin_ui()
        if ui_res:
            return ui_res

    return jsonify({"status": "error", "error": "الملف غير موجود"}), 404

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
