import os
from flask import Flask, jsonify, send_from_directory, request
from flask_cors import CORS

import database
from core.security import get_authenticated_user

app = Flask(__name__)

# إعداد CORS للوصول إلى مسارات API
CORS(app, resources={r"/api/*": {"origins": "*"}})

WEB_URL = os.environ.get('WEB_URL', 'https://zn-goxe-production.up.railway.app').strip().rstrip('/')

# ==========================================
# تسجيل المسارات (Blueprints)
# ==========================================
from farm.farm_api import farm_bp
from settings.settings_api import settings_bp
from friends.friends_api import friends_bp
from games.games_api import games_bp
from tasks.tasks_api import tasks_bp
from shop.shop_api import shop_bp
from wallet.wallet_api import wallet_bp
from support.support_api import support_bp
from admin_chat.admin_chat_api import admin_chat_bp

app.register_blueprint(farm_bp, url_prefix='/api/farm')
app.register_blueprint(settings_bp, url_prefix='/api/settings')
app.register_blueprint(friends_bp, url_prefix='/api/friends')
app.register_blueprint(games_bp, url_prefix='/api/games')
app.register_blueprint(tasks_bp, url_prefix='/api/tasks')
app.register_blueprint(shop_bp, url_prefix='/api/shop')
app.register_blueprint(wallet_bp, url_prefix='/api/wallet')
app.register_blueprint(support_bp, url_prefix='/api/support')
app.register_blueprint(admin_chat_bp, url_prefix='/api/admin/chat')

# ==========================================
# المسارات المباشرة والخدمية
# ==========================================

@app.route('/tonconnect-manifest.json')
def serve_tonconnect_manifest():
    """تقديم ملف البيانات الخاص بمحفظة TON Connect"""
    try:
        return send_from_directory('.', 'tonconnect-manifest.json', mimetype='application/json')
    except Exception as e:
        print(f"❌ Manifest Error: {e}")
        return jsonify({"error": "Manifest file not found"}), 404

@app.route('/api/user/info', methods=['GET', 'POST'])
def get_user_info_main():
    """جلب وتأكيد بيانات المستخدم والتحقق المباشر من حالة الحظر"""
    is_post = (request.method == 'POST')
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=is_post)
    if not success:
        return error_res
        
    try:
        # 1. التحقق الفوري من كاش الحظر قبل استهلاك الاستعلامات
        if database.is_user_banned(telegram_id):
            return jsonify({
                "success": False, 
                "error": "حسابك معطل حالياً بسبب مخالفة الشروط",
                "banned": True
            }), 403

        # 2. جلب بيانات المستخدم أو إنشاؤه إذا كان جديداً
        user_data = database.get_user(telegram_id)
        if not user_data:
            first_name = user_info.get('first_name', 'لاعب') if isinstance(user_info, dict) else 'لاعب'
            ref_id = user_info.get('start_param') if isinstance(user_info, dict) else None
            
            database.init_user(telegram_id, ref_id=ref_id, first_name=first_name)
            user_data = database.get_user(telegram_id)
            
        return jsonify({"success": True, "user": user_data}), 200
    except Exception as e:
        print(f"❌ Error fetching user info for {telegram_id}: {e}")
        return jsonify({"success": False, "error": "حدث خطأ أثناء جلب بيانات الحساب"}), 500


@app.route('/api/verify_admin', methods=['POST'])
def verify_admin_access():
    """التحقق المباشر من هويّة الأدمن وصلاحيات الدخول من التليجرام"""
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=True)
    if not success:
        return error_res

    try:
        user_data = database.get_user(telegram_id) or {}
        # فحص إن كان المدير يملك صلاحيات أو معرّف الإدارة الرئيسي
        return jsonify({
            "success": True,
            "role": "المدير العام",
            "telegram_id": telegram_id,
            "user": user_data
        }), 200
    except Exception as e:
        print(f"❌ Error verifying admin {telegram_id}: {e}")
        return jsonify({"success": False, "message": "فشل التحقق من صلاحيات المدير"}), 500


# ==========================================
# مسارات الإدارة العليا (Super Admin APIs)
# ==========================================

@app.route('/api/admin/stats', methods=['GET'])
def get_admin_stats():
    """تجميع وجلب إحصائيات الأرباح ونسب الألعاب للإدارة العليا"""
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=False)
    if not success:
        return error_res

    try:
        settings = database.get_game_settings() or {}
        stats_summary = database.get_game_profit_stats() or {}

        target_margin_pct = float(settings.get('target_margin', stats_summary.get('target_margin_percent', 70.0)))
        player_margin_pct = round(max(0.0, 100.0 - target_margin_pct), 2)

        return jsonify({
            "success": True,
            "target_margin": target_margin_pct,
            "player_margin": player_margin_pct,
            "bot_margin": target_margin_pct,
            "commission_percent": player_margin_pct,
            "stats": {
                "total_bot_profit": stats_summary.get("total_bot_profit", 0.0),
                "total_user_profit": stats_summary.get("total_user_profit", 0.0),
                "actual_margin": stats_summary.get("actual_bot_percent", 0.0),
                "actual_bot_percent": stats_summary.get("actual_bot_percent", 0.0),
                "actual_user_percent": stats_summary.get("actual_user_percent", 0.0)
            }
        }), 200
    except Exception as e:
        print(f"❌ Error fetching admin stats: {e}")
        return jsonify({"success": False, "error": "حدث خطأ أثناء جلب إحصائيات الأرباح"}), 500


@app.route('/api/admin/settings', methods=['POST'])
def save_admin_settings():
    """حفظ نسبة البوت ونسبة اللاعبين في إعدادات النظام الإدارية"""
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=True)
    if not success:
        return error_res

    try:
        data = request.get_json(silent=True) or {}
        target_margin = data.get('target_margin')
        bot_margin = data.get('bot_margin')
        player_margin = data.get('player_margin')

        if target_margin is None and bot_margin is not None:
            target_margin = bot_margin
        elif target_margin is None and player_margin is not None:
            target_margin = round(100.0 - float(player_margin), 2)

        if target_margin is not None:
            target_margin = float(target_margin)
            if target_margin < 0 or target_margin > 100:
                return jsonify({"success": False, "error": "النسبة يجب أن تكون بين 0 و 100"}), 400

            # تحديث الإعدادات في قاعدة البيانات
            if hasattr(database, 'update_game_settings'):
                database.update_game_settings({
                    'target_margin': target_margin,
                    'player_margin': round(100.0 - target_margin, 2),
                    'updated_by': telegram_id
                })

            if hasattr(database, 'update_grid_game_config'):
                database.update_grid_game_config(target_margin=target_margin)

            if hasattr(database, 'clear_settings_cache'):
                database.clear_settings_cache()

            return jsonify({
                "success": True,
                "message": "تم حفظ نسبة البوت ونسبة اللاعبين بنجاح",
                "target_margin": target_margin,
                "player_margin": round(100.0 - target_margin, 2)
            }), 200
        else:
            return jsonify({"success": False, "error": "يرجى تحديد نسبة البوت أو نسبة اللاعبين"}), 400
    except Exception as e:
        print(f"❌ Error saving admin settings: {e}")
        return jsonify({"success": False, "error": "حدث خطأ أثناء حفظ الإعدادات"}), 500


# ==========================================
# مسارات التحكم بالألعاب المباشرة (Game & Profit Control API)
# ==========================================

@app.route('/api/game-settings', methods=['GET', 'POST'])
def manage_game_settings():
    """جلب وتحديث إعدادات أرباح البوت ونسب التحكم في الألعاب"""
    is_post = (request.method == 'POST')
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=is_post)
    if not success:
        return error_res

    if request.method == 'GET':
        try:
            settings = database.get_game_settings() or {}
            stats_summary = database.get_game_profit_stats() or {}
            grid_cfg = settings.get('grid_game_config', {})

            target_margin_pct = float(settings.get('target_margin', stats_summary.get('target_margin_percent', 70.0)))
            player_margin_pct = round(max(0.0, 100.0 - target_margin_pct), 2)

            return jsonify({
                "success": True,
                "target_margin": target_margin_pct,
                "player_margin": player_margin_pct,
                "commission_percent": player_margin_pct,
                "grid_game_config": grid_cfg,
                "stats": {
                    "total_bot_profit": stats_summary.get("total_bot_profit", 0.0),
                    "total_user_profit": stats_summary.get("total_user_profit", 0.0),
                    "actual_margin": stats_summary.get("actual_bot_percent", 0.0),
                    "actual_bot_percent": stats_summary.get("actual_bot_percent", 0.0),
                    "actual_user_percent": stats_summary.get("actual_user_percent", 0.0)
                }
            }), 200
        except Exception as e:
            print(f"❌ Error fetching game settings: {e}")
            return jsonify({"success": False, "error": "حدث خطأ أثناء جلب إعدادات الأرباح"}), 500

    elif request.method == 'POST':
        try:
            data = request.get_json(silent=True) or {}
            target_margin_input = data.get('target_margin') or data.get('bot_margin')
            commission_input = data.get('commission_percent') or data.get('player_margin')
            min_bet_input = data.get('min_bet')

            if target_margin_input is None and commission_input is not None:
                target_margin_input = round(100.0 - float(commission_input), 2)

            if target_margin_input is not None or min_bet_input is not None:
                if hasattr(database, 'update_grid_game_config'):
                    database.update_grid_game_config(
                        min_bet=min_bet_input,
                        target_margin=target_margin_input
                    )
            
            if hasattr(database, 'update_game_settings'):
                database.update_game_settings(data)

            if hasattr(database, 'clear_settings_cache'):
                database.clear_settings_cache()

            return jsonify({
                "success": True,
                "message": "تم تحديث إعدادات الأرباح ونسبة البوت بنجاح"
            }), 200
        except Exception as e:
            print(f"❌ Error updating game settings: {e}")
            return jsonify({"success": False, "error": "حدث خطأ أثناء حفظ إعدادات الأرباح"}), 500

# ==========================================
# الأمان والتحكم بالهيدرز والملفات الثابتة
# ==========================================

@app.after_request
def add_security_headers(response):
    """منع التخزين المؤقت (Cache) لمسارات الـ API"""
    if request.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response

@app.errorhandler(500)
def handle_500_error(e):
    return jsonify({"success": False, "error": "حدث خطأ داخلي في السيرفر"}), 500

@app.errorhandler(404)
def handle_404_error(e):
    if request.path.startswith('/api/'):
        return jsonify({"success": False, "error": "المسار غير موجود"}), 404
    return send_from_directory('.', 'index.html')

@app.route('/')
def serve_index():
    return send_from_directory('.', 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    """تقديم الملفات الثابتة وتأمين الملفات البرمجية والحساسة تحديداً"""
    path_lower = path.lower()
    
    if path_lower == 'tonconnect-manifest.json':
        return send_from_directory('.', 'tonconnect-manifest.json', mimetype='application/json')
    
    # حظر الامتدادات والملفات الحساسة بوضوح
    forbidden_extensions = ('.py', '.env', '.sh', '.git', '.pem', '.key')
    forbidden_files = ('firebase-adminsdk.json', 'config.json', 'requirements.txt')
    
    if any(path_lower.endswith(ext) for ext in forbidden_extensions) or any(f in path_lower for f in forbidden_files):
        return jsonify({"error": "Access Denied"}), 403
        
    try:
        return send_from_directory('.', path)
    except Exception:
        return send_from_directory('.', 'index.html')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
