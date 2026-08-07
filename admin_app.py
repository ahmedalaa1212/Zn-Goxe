import os
from flask import Flask, jsonify, send_from_directory, request
from flask_cors import CORS

import database
from core.security import get_authenticated_user

app = Flask(__name__)

# إعداد CORS للوصول إلى كافة مسارات API
CORS(app, resources={r"/api/*": {"origins": "*"}})

WEB_URL = os.environ.get('WEB_URL', 'https://zn-goxe-production.up.railway.app').strip().rstrip('/')

# ==========================================
# تسجيل المسارات (Blueprints) الخاصة ببرمجة المستخدم
# ==========================================
from farm.farm_api import farm_bp
from settings.settings_api import settings_bp
from friends.friends_api import friends_bp
from games.games_api import games_bp
from tasks.tasks_api import tasks_bp
from shop.shop_api import shop_bp
from wallet.wallet_api import wallet_bp
from support.support_api import support_bp

app.register_blueprint(farm_bp, url_prefix='/api/farm')
app.register_blueprint(settings_bp, url_prefix='/api/settings')
app.register_blueprint(friends_bp, url_prefix='/api/friends')
app.register_blueprint(games_bp, url_prefix='/api/games')
app.register_blueprint(tasks_bp, url_prefix='/api/tasks')
app.register_blueprint(shop_bp, url_prefix='/api/shop')
app.register_blueprint(wallet_bp, url_prefix='/api/wallet')
app.register_blueprint(support_bp, url_prefix='/api/support')

# ==========================================
# مسارات إدارة لعبة شبكة ZN Go (Admin API Endpoints)
# ==========================================

@app.route('/api/verify_admin', methods=['POST'])
def verify_admin_access():
    """التحقق المباشر من هويّة الإدارة أو المشرفين"""
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=True)
    if not success:
        return error_res

    if database.is_admin_or_mod(telegram_id):
        return jsonify({"success": True, "message": "تم التحقق بنجاح"}), 200
    return jsonify({"success": False, "error": "عذراً، البوت مخصص للإدارة فقط!"}), 403


@app.route('/api/admin/zn-go-settings', methods=['GET', 'POST'])
@app.route('/api/admin/settings/grid_36', methods=['GET', 'POST'])
def admin_zn_go_settings():
    """مسارات جلب وتحديث إعدادات لعبة شبكة ZN Go في Firestore"""
    is_post = (request.method == 'POST')
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=is_post)
    if not success:
        return error_res

    if not database.is_admin_or_mod(telegram_id):
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
    """مسارات إدارة لعبة الساحة الكبرى"""
    is_post = (request.method == 'POST')
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=is_post)
    if not success:
        return error_res

    if not database.is_admin_or_mod(telegram_id):
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
    """جلب إحصائيات الداشبورد العامة"""
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=False)
    if not success:
        return error_res

    if not database.is_admin_or_mod(telegram_id):
        return jsonify({"success": False, "error": "غير مصرح لك للوصول للإدارة"}), 403

    res = database.get_admin_dashboard_stats()
    return jsonify(res), 200


@app.route('/api/moderators', methods=['GET', 'POST'])
@app.route('/api/moderators/<mod_id>', methods=['DELETE'])
def admin_moderators_manager(mod_id=None):
    """إدارة قائمة المشرفين والصلاحيات"""
    is_post = (request.method in ['POST', 'DELETE'])
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=is_post)
    if not success:
        return error_res

    if not database.is_admin_or_mod(telegram_id):
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
        deleted_by = request.args.get("deletedBy", "المدير العام")
        ok = database.delete_moderator(mod_id, deleted_by)
        if ok:
            return jsonify({"success": True, "message": "تم حذف المشرف بنجاح"}), 200
        return jsonify({"success": False, "error": "حدث خطأ أثناء حذف المشرف"}), 500


@app.route('/api/admin-logs', methods=['GET'])
def admin_logs_handler():
    """جلب سجل النشاطات الإدارية"""
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=False)
    if not success:
        return error_res

    if not database.is_admin_or_mod(telegram_id):
        return jsonify({"success": False, "error": "غير مصرح لك للوصول للإدارة"}), 403

    logs = database.get_admin_logs(limit=50)
    return jsonify({"success": True, "logs": logs}), 200


# ==========================================
# مسارات للتكيف المباشر مع استدعاءات الجافاسكريبت القديمة والجديدة
# ==========================================

@app.route('/api/game/start', methods=['POST'])
@app.route('/api/game/step', methods=['POST'])
@app.route('/api/game/cashout', methods=['POST'])
def proxy_legacy_game_routes():
    """توجيه استدعاءات الفرونت إند الكلاسيكية تلقائياً إلى blueprint الألعاب"""
    from games.games_api import start_boxes_game, pick_box, end_boxes_game
    path = request.path
    if path.endswith('/start'):
        return start_boxes_game()
    elif path.endswith('/step'):
        return pick_box()
    elif path.endswith('/cashout'):
        return end_boxes_game()
    return jsonify({"success": False, "message": "مسار غير معروف"}), 404

# ==========================================
# المسارات المباشرة والخدمية للمستخدم
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
        if database.is_user_banned(telegram_id):
            return jsonify({
                "success": False, 
                "error": "حسابك معطل حالياً بسبب مخالفة الشروط",
                "banned": True
            }), 403

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
    return jsonify({"status": "error", "success": False, "error": "حدث خطأ داخلي في السيرفر", "message": "خطأ في الاتصال بالخادم."}), 500

@app.errorhandler(404)
def handle_404_error(e):
    if request.path.startswith('/api/'):
        return jsonify({"status": "error", "success": False, "error": "المسار غير موجود", "message": "خطأ في الاتصال بالخادم."}), 404
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
