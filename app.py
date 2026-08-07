# app.py
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


# ==========================================
# مسارات التحكم بإعدادات الأرباح والألعاب (Game & Profit Control API)
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
            grid_cfg = settings.get('grid_game_config', {})
            stats = settings.get('stats', {})

            # استخراج أرباح البوت والمستخدمين للحساب
            bot_profit = float(stats.get('total_bot_profit', stats.get('total_user_losses', 0.0)))
            user_profit = float(stats.get('total_user_profit', stats.get('total_user_wins', 0.0)))

            total_turnover = bot_profit + user_profit
            actual_margin = (bot_profit / total_turnover * 100.0) if total_turnover > 0 else 0.0

            target_margin = float(grid_cfg.get('target_margin', settings.get('commission_percent', 70.0)))
            commission_percent = float(settings.get('commission_percent', round(100.0 - target_margin, 2)))

            return jsonify({
                "success": True,
                "target_margin": target_margin,
                "commission_percent": commission_percent,
                "grid_game_config": grid_cfg,
                "stats": {
                    "total_bot_profit": bot_profit,
                    "total_user_profit": user_profit,
                    "actual_margin": round(actual_margin, 2)
                }
            }), 200
        except Exception as e:
            print(f"❌ Error fetching game settings: {e}")
            return jsonify({"success": False, "error": "حدث خطأ أثناء جلب إعدادات الأرباح"}), 500

    elif request.method == 'POST':
        try:
            data = request.get_json(silent=True) or {}
            target_margin_input = data.get('target_margin')
            commission_input = data.get('commission_percent')
            min_bet_input = data.get('min_bet')

            updates = {}
            grid_updates = {}

            if target_margin_input is not None:
                t_margin = float(target_margin_input)
                grid_updates['target_margin'] = t_margin
                updates['commission_percent'] = round(100.0 - t_margin, 2)

            if commission_input is not None and target_margin_input is None:
                comm_val = float(commission_input)
                updates['commission_percent'] = comm_val
                grid_updates['target_margin'] = round(100.0 - comm_val, 2)

            if min_bet_input is not None:
                grid_updates['min_bet'] = float(min_bet_input)

            if grid_updates:
                for k, v in grid_updates.items():
                    updates[f'grid_game_config.{k}'] = v

            if updates:
                database.db.collection('app_config').document('game_settings').set(updates, merge=True)
                
                # تصفير الكاش في السيرفر لتحديث البيانات فوراً
                if hasattr(database, '_GAME_SETTINGS_CACHE'):
                    database._GAME_SETTINGS_CACHE = None

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
    
    # حظر الامتدادات والملفات الحساسة بوضوح بدلاً من حظر كل ملفات JSON
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
