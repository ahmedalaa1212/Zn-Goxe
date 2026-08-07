import os
import json
import hmac
import hashlib
import urllib.parse
from functools import wraps
from flask import Flask, jsonify, send_from_directory, request
from flask_cors import CORS

import database
from core.security import get_authenticated_user

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
            
            if user_id == str(ADMIN_ID):
                return {"user": user_data, "role": "المدير العام", "is_owner": True, "telegram_id": user_id}
                
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
    """ديكوريتور لحماية جميع مسارات API المخصصة للأدمن"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        init_data = request.headers.get('X-Telegram-Init-Data') or (request.get_json(silent=True) or {}).get('initData')
        auth_info = validate_telegram_admin(init_data)
        
        if auth_info:
            request.telegram_user = auth_info
            return f(*args, **kwargs)

        is_post = (request.method == 'POST')
        success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=is_post)
        if success:
            request.telegram_user = {"telegram_id": telegram_id, "role": "المدير العام", "user": user_info}
            return f(*args, **kwargs)

        return jsonify({"status": "error", "success": False, "message": "عذراً، البوت مخصص للإدارة فقط!"}), 403
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
    """البحث المباشر والذكي عن ملف الواجهة لتفادي مشكلة 404"""
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
    """التحقق المباشر من هويّة الأدمن وصلاحيات الدخول من التليجرام"""
    init_data = request.headers.get('X-Telegram-Init-Data') or (request.get_json(silent=True) or {}).get('initData')
    auth_info = validate_telegram_admin(init_data)
    
    if auth_info:
        return jsonify({
            "success": True,
            "role": auth_info["role"],
            "telegram_id": auth_info["telegram_id"],
            "user": auth_info["user"]
        }), 200

    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=True)
    if success:
        user_data = database.get_user(telegram_id) or {}
        return jsonify({
            "success": True,
            "role": "المدير العام",
            "telegram_id": telegram_id,
            "user": user_data
        }), 200

    return jsonify({"success": False, "message": "عذراً، البوت مخصص للإدارة فقط!"}), 403


@app.route('/api/admin/dashboard-stats', methods=['GET'])
@require_telegram_admin
def admin_dashboard_stats():
    """تزويد لوحة الإدارة بأرقام أرباح البوت والأرباح الفعلية والحد الأدنى"""
    try:
        arena_data = _fetch_arena_current_stats()
        stats_summary = database.get_game_profit_stats() or {} if hasattr(database, 'get_game_profit_stats') else {}
        settings = database.get_game_settings() or {} if hasattr(database, 'get_game_settings') else {}
        grid_cfg = settings.get('grid_game_config', {})

        total_bets = float(arena_data.get('total_bets', stats_summary.get('global_total_bets', 0.0)))
        total_payouts = float(arena_data.get('total_payouts', stats_summary.get('global_total_wins', 0.0)))
        
        bot_profit = round(max(0.0, total_bets - total_payouts), 2)
        user_profit = round(total_payouts, 2)
        
        actual_bot_percent = 0.0
        if total_bets > 0:
            actual_bot_percent = round(((total_bets - total_payouts) / total_bets) * 100.0, 1)

        target_margin_pct = float(settings.get('target_margin', stats_summary.get('target_margin_percent', 70.0)))
        min_bet = float(grid_cfg.get('min_bet', settings.get('min_bet', 10.0)))

        return jsonify({
            "status": "success",
            "success": True,
            "min_bet": min_bet,
            "target_margin": target_margin_pct,
            "stats": {
                "total_bot_profit": bot_profit,
                "total_wins": user_profit,
                "total_user_profit": user_profit,
                "actual_bot_percent": actual_bot_percent,
                "actual_margin": actual_bot_percent,
                "target_margin_percent": target_margin_pct,
                "min_bet": min_bet
            }
        }), 200
    except Exception as e:
        print(f"❌ Error fetching dashboard stats: {e}")
        return jsonify({"status": "error", "message": "حدث خطأ أثناء جلب بيانات لوحة التحكم"}), 500


@app.route('/api/admin/update-margin', methods=['POST'])
@require_telegram_admin
def update_margin():
    """تعديل وحفظ نسبة أرباح البوت والحد الأدنى للعب في الفايربيس"""
    try:
        telegram_id = request.telegram_user.get('telegram_id', 'unknown')
        req_data = request.get_json(silent=True) or {}
        bot_margin = req_data.get('bot_margin') or req_data.get('target_margin')
        min_bet = req_data.get('min_bet')

        if bot_margin is None and min_bet is None:
            return jsonify({"status": "error", "success": False, "message": "يرجى تحديد البيانات المراد تعديلها"}), 400

        if bot_margin is not None:
            try:
                bot_margin = float(bot_margin)
                if bot_margin < 0 or bot_margin > 100:
                    return jsonify({"status": "error", "success": False, "message": "النسبة يجب أن تكون بين 0 و 100"}), 400
            except (ValueError, TypeError):
                return jsonify({"status": "error", "success": False, "message": "قيمة النسبة غير صالحة"}), 400

        if min_bet is not None:
            try:
                min_bet = float(min_bet)
            except (ValueError, TypeError):
                return jsonify({"status": "error", "success": False, "message": "قيمة الحد الأدنى غير صالحة"}), 400

        if hasattr(database, 'update_grid_game_config'):
            database.update_grid_game_config(
                min_bet=min_bet,
                target_margin=bot_margin
            )

        if hasattr(database, 'update_game_settings'):
            update_payload = {'updated_by': telegram_id}
            if bot_margin is not None:
                update_payload['target_margin'] = bot_margin
                update_payload['player_margin'] = round(100.0 - bot_margin, 2)
            if min_bet is not None:
                update_payload['min_bet'] = min_bet
            database.update_game_settings(update_payload)

        if hasattr(database, 'clear_settings_cache'):
            database.clear_settings_cache()

        return jsonify({"status": "success", "success": True, "message": "تم تحديث إعدادات الأرباح والحد الأدنى بنجاح"}), 200

    except Exception as e:
        print(f"❌ Error updating margin: {e}")
        return jsonify({"status": "error", "success": False, "message": "حدث خطأ أثناء تحديث نسبة التحكم"}), 500


@app.route('/api/admin/stats', methods=['GET'])
@require_telegram_admin
def get_admin_stats():
    """جلب تفاصيل إحصائيات التحكم بالأرباح للاستخدام المباشر"""
    try:
        arena_data = _fetch_arena_current_stats()
        settings = database.get_game_settings() or {} if hasattr(database, 'get_game_settings') else {}
        stats_summary = database.get_game_profit_stats() or {} if hasattr(database, 'get_game_profit_stats') else {}
        grid_cfg = settings.get('grid_game_config', {})

        total_bets = float(arena_data.get('total_bets', stats_summary.get('global_total_bets', 0.0)))
        total_payouts = float(arena_data.get('total_payouts', stats_summary.get('global_total_wins', 0.0)))

        bot_profit = round(max(0.0, total_bets - total_payouts), 2)
        user_profit = round(total_payouts, 2)

        actual_margin = 0.0
        if total_bets > 0:
            actual_margin = round(((total_bets - total_payouts) / total_bets) * 100.0, 1)

        target_margin_pct = float(settings.get('target_margin', stats_summary.get('target_margin_percent', 70.0)))
        player_margin_pct = round(max(0.0, 100.0 - target_margin_pct), 2)
        min_bet = float(grid_cfg.get('min_bet', settings.get('min_bet', 10.0)))

        return jsonify({
            "status": "success",
            "success": True,
            "target_margin": target_margin_pct,
            "player_margin": player_margin_pct,
            "bot_margin": target_margin_pct,
            "commission_percent": player_margin_pct,
            "min_bet": min_bet,
            "stats": {
                "total_bot_profit": bot_profit,
                "total_user_profit": user_profit,
                "total_wins": user_profit,
                "actual_margin": actual_margin,
                "actual_bot_percent": actual_margin,
                "actual_user_percent": round(100.0 - actual_margin, 1),
                "global_total_bets": total_bets,
                "global_total_wins": total_payouts,
                "min_bet": min_bet
            }
        }), 200
    except Exception as e:
        print(f"❌ Error fetching admin stats: {e}")
        return jsonify({"status": "error", "success": False, "error": "حدث خطأ أثناء جلب إحصائيات الأرباح"}), 500


@app.route('/api/admin/settings', methods=['POST'])
@require_telegram_admin
def save_admin_settings_route():
    """حفظ الإعدادات الإدارية المباشرة"""
    return update_margin()


# ==========================================
# مسارات إعدادات اللعبة والأرباح (Game Settings)
# ==========================================

@app.route('/api/game-settings', methods=['GET', 'POST'])
@require_telegram_admin
def manage_game_settings():
    """جلب وتحديث إعدادات الأرباح من واجهة الأدمن"""
    if request.method == 'GET':
        try:
            arena_data = _fetch_arena_current_stats()
            settings = database.get_game_settings() or {} if hasattr(database, 'get_game_settings') else {}
            stats_summary = database.get_game_profit_stats() or {} if hasattr(database, 'get_game_profit_stats') else {}
            grid_cfg = settings.get('grid_game_config', {})

            total_bets = float(arena_data.get('total_bets', stats_summary.get('global_total_bets', 0.0)))
            total_payouts = float(arena_data.get('total_payouts', stats_summary.get('global_total_wins', 0.0)))

            bot_profit = round(max(0.0, total_bets - total_payouts), 2)
            user_profit = round(total_payouts, 2)

            actual_margin = 0.0
            if total_bets > 0:
                actual_margin = round(((total_bets - total_payouts) / total_bets) * 100.0, 1)

            target_margin_pct = float(settings.get('target_margin', stats_summary.get('target_margin_percent', 70.0)))
            player_margin_pct = round(max(0.0, 100.0 - target_margin_pct), 2)
            min_bet = float(grid_cfg.get('min_bet', settings.get('min_bet', 10.0)))

            return jsonify({
                "status": "success",
                "success": True,
                "target_margin": target_margin_pct,
                "player_margin": player_margin_pct,
                "commission_percent": player_margin_pct,
                "min_bet": min_bet,
                "grid_game_config": grid_cfg,
                "stats": {
                    "total_bot_profit": bot_profit,
                    "total_user_profit": user_profit,
                    "total_wins": user_profit,
                    "actual_margin": actual_margin,
                    "actual_bot_percent": actual_margin,
                    "actual_user_percent": round(100.0 - actual_margin, 1),
                    "global_total_bets": total_bets,
                    "global_total_wins": total_payouts,
                    "min_bet": min_bet
                }
            }), 200
        except Exception as e:
            print(f"❌ Error fetching game settings: {e}")
            return jsonify({"status": "error", "success": False, "error": "حدث خطأ أثناء جلب إعدادات الأرباح"}), 500

    elif request.method == 'POST':
        return update_margin()


# ==========================================
# مسارات المشرفين واللوجات (Moderators & Admin Logs)
# ==========================================

@app.route('/api/moderators', methods=['GET', 'POST'])
@require_telegram_admin
def manage_moderators():
    """جلب وإضافة المشرفين من لوحة الأدمن"""
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
    """حذف مشرف وحظر صلاحياته"""
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
    """جلب سجل التحركات والنشاطات الإدارية"""
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
    """منع الكاش للـ API"""
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
    return jsonify({
        "status": "error",
        "message": "لم يتم العثور على ملف الواجهة (admin.html أو super_admin.html). يُرجى التأكد من مسار الملف في المشروع."
    }), 404

@app.route('/<path:path>')
def serve_static(path):
    # 1. البحث عن الملف مباشرة من BASE_DIR
    target_path = os.path.join(BASE_DIR, path)
    if os.path.isfile(target_path):
        return send_from_directory(BASE_DIR, path)
    
    # 2. البحث داخل مجلد super_admin
    super_admin_dir = os.path.join(BASE_DIR, 'super_admin')
    if os.path.isfile(os.path.join(super_admin_dir, path)):
        return send_from_directory(super_admin_dir, path)

    # 3. البحث داخل مجلد templates
    templates_dir = os.path.join(BASE_DIR, 'templates')
    if os.path.isfile(os.path.join(templates_dir, path)):
        return send_from_directory(templates_dir, path)

    # Fallback to Admin UI for non-API frontend routes safely
    if not path.startswith('api/'):
        ui_res = _serve_admin_ui()
        if ui_res:
            return ui_res

    return jsonify({"status": "error", "error": "الملف غير موجود"}), 404

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
