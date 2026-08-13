import os
import random
from flask import Flask, jsonify, send_from_directory, request, Blueprint
from flask_cors import CORS

import database
from core.security import get_authenticated_user

app = Flask(__name__)

# إعداد CORS للوصول إلى كافة مسارات API
CORS(app, resources={r"/api/*": {"origins": "*"}})

WEB_URL = os.environ.get('WEB_URL', 'https://zn-goxe-production.up.railway.app').strip().rstrip('/')

# ==========================================
# تسجيل المسارات (Blueprints) الخاصة بجميع موديولات المشروع
# ==========================================
from farm.farm_api import farm_bp
from settings.settings_api import settings_bp
from friends.friends_api import friends_bp
from tasks.tasks_api import tasks_bp
from shop.shop_api import shop_bp
from wallet.wallet_api import wallet_bp
from support.support_api import support_bp
from admin_chat.admin_chat_api import admin_chat_bp

# تسجيل مسارات الـ API مع البادئات المخصصة لكل موديول
app.register_blueprint(farm_bp, url_prefix='/api/farm')
app.register_blueprint(settings_bp, url_prefix='/api/settings')
app.register_blueprint(friends_bp, url_prefix='/api/friends')
app.register_blueprint(tasks_bp, url_prefix='/api/tasks')
app.register_blueprint(shop_bp, url_prefix='/api/shop')
app.register_blueprint(wallet_bp, url_prefix='/api/wallet')
app.register_blueprint(support_bp, url_prefix='/api/support')
app.register_blueprint(admin_chat_bp, url_prefix='/api/admin-chat')

# ⚡ تسجيل مسار الألعاب محمي بـ Try/Except عشان لو المجلد محذوف السيرفر ميقعش
try:
    from games.games_api import games_bp
    app.register_blueprint(games_bp)
    print("✅ تم تسجيل موديول الألعاب الرئيسي (games_bp) بنجاح!")
except ImportError as e:
    print(f"⚠️ مجلد الألعاب غير موجود حالياً، تم تخطيه ولن يتم إيقاف السيرفر: {e}")

# ==========================================
# 🎮 مسارات لعبة Goxe Tower Direct Blueprint
# ==========================================
goxe_bp = Blueprint('goxe', __name__)
goxe_sessions = {}
GOXE_MULTIPLIERS = [1.10, 1.30, 1.50, 1.80, 2.20, 2.70, 3.30, 3.90, 4.40, 5.00]

@goxe_bp.route('/config', methods=['GET', 'POST'])
def goxe_config():
    is_post = (request.method == 'POST')
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=is_post)
    
    if not success:
        tg_id_param = request.args.get('tg_id') or (request.json.get('tg_id') if request.is_json and request.json else None)
        if tg_id_param:
            telegram_id = str(tg_id_param)

    session_data = goxe_sessions.get(telegram_id) if telegram_id else None
    
    return jsonify({
        "success": True,
        "multipliers": GOXE_MULTIPLIERS,
        "min_bet": 10,
        "max_bet": 10000,
        "active_session": session_data if (session_data and session_data.get('is_active')) else None
    }), 200

@goxe_bp.route('/start', methods=['POST'])
def goxe_start():
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=True)
    
    if not success:
        tg_id_param = request.args.get('tg_id') or (request.json.get('tg_id') if request.is_json and request.json else None)
        if tg_id_param:
            telegram_id = str(tg_id_param)
        else:
            return error_res

    data = request.get_json() or {}
    try:
        bet_amount = float(data.get('bet_amount', 100))
    except (ValueError, TypeError):
        return jsonify({"success": False, "error": "مبلغ الرهان غير صالح"}), 400

    user_data = database.get_user(telegram_id)
    if not user_data:
        return jsonify({"success": False, "error": "المستخدم غير موجود"}), 404

    balance = float(user_data.get('balance', 0.0))
    if balance < bet_amount:
        return jsonify({"success": False, "error": f"رصيدك غير كافٍ! رصيدك الحالي: {balance:.2f} ZN"}), 400

    # خصم المبلغ من رصيد المستخدم
    if hasattr(database, 'update_user_balance'):
        database.update_user_balance(telegram_id, -bet_amount)
    elif hasattr(database, 'add_balance'):
        database.add_balance(telegram_id, -bet_amount)
    elif hasattr(database, 'update_user'):
        database.update_user(telegram_id, {'balance': balance - bet_amount})

    goxe_sessions[telegram_id] = {
        "bet_amount": bet_amount,
        "current_floor": 0,
        "is_active": True
    }

    return jsonify({
        "success": True,
        "message": "تم بدء الجولة بنجاح",
        "current_floor": 0
    }), 200

@goxe_bp.route('/climb', methods=['POST'])
def goxe_climb():
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=True)
    
    if not success:
        tg_id_param = request.args.get('tg_id') or (request.json.get('tg_id') if request.is_json and request.json else None)
        if tg_id_param:
            telegram_id = str(tg_id_param)
        else:
            return error_res

    session = goxe_sessions.get(telegram_id)
    if not session or not session.get("is_active"):
        return jsonify({"success": False, "error": "لا توجد جولة نشطة حالياً"}), 400

    data = request.get_json() or {}
    door_index = int(data.get('door_index', 0))

    # احتمال القنبلة (باب واحد من الـ 3 أبواب)
    bomb_door = random.randint(0, 2)
    
    if door_index == bomb_door:
        session["is_active"] = False
        return jsonify({
            "success": True,
            "result": "bomb",
            "message": "💥 للأسف! كانت قنبلة وخسرت الجولة."
        }), 200

    session["current_floor"] += 1
    current_floor = session["current_floor"]

    if current_floor >= len(GOXE_MULTIPLIERS):
        win_amount = session["bet_amount"] * GOXE_MULTIPLIERS[-1]
        
        # إضافة الأرباح للرصيد
        if hasattr(database, 'update_user_balance'):
            database.update_user_balance(telegram_id, win_amount)
        elif hasattr(database, 'add_balance'):
            database.add_balance(telegram_id, win_amount)
        elif hasattr(database, 'update_user'):
            u = database.get_user(telegram_id) or {}
            b = float(u.get('balance', 0.0))
            database.update_user(telegram_id, {'balance': b + win_amount})

        session["is_active"] = False
        return jsonify({
            "success": True,
            "result": "max_win",
            "winnings": win_amount,
            "message": f"🎉 مبروك! وصلت لأعلى دور وحققت {win_amount:.2f} ZN!"
        }), 200

    return jsonify({
        "success": True,
        "result": "safe",
        "current_floor": current_floor,
        "multiplier": GOXE_MULTIPLIERS[current_floor - 1]
    }), 200

@goxe_bp.route('/cashout', methods=['POST'])
def goxe_cashout():
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=True)
    
    if not success:
        tg_id_param = request.args.get('tg_id') or (request.json.get('tg_id') if request.is_json and request.json else None)
        if tg_id_param:
            telegram_id = str(tg_id_param)
        else:
            return error_res

    session = goxe_sessions.get(telegram_id)
    if not session or not session.get("is_active") or session["current_floor"] == 0:
        return jsonify({"success": False, "error": "لا يمكنك السحب الآن"}), 400

    current_floor = session["current_floor"]
    multiplier = GOXE_MULTIPLIERS[current_floor - 1]
    winnings = session["bet_amount"] * multiplier

    # إضافة الأرباح للرصيد
    if hasattr(database, 'update_user_balance'):
        database.update_user_balance(telegram_id, winnings)
    elif hasattr(database, 'add_balance'):
        database.add_balance(telegram_id, winnings)
    elif hasattr(database, 'update_user'):
        u = database.get_user(telegram_id) or {}
        b = float(u.get('balance', 0.0))
        database.update_user(telegram_id, {'balance': b + winnings})

    session["is_active"] = False
    return jsonify({
        "success": True,
        "winnings": winnings
    }), 200

# تسجيل Blueprint لعبة Goxe بالرابط المطلوب
app.register_blueprint(goxe_bp, url_prefix='/api/games/goxe')

# ==========================================
# المسارات المباشرة والخدمية للمستخدم
# ==========================================

@app.route('/tonconnect-manifest.json')
def serve_tonconnect_manifest():
    """تقديم ملف البيانات الخاص بمحفظة TON Connect مع السماح للطلبات الخارجية"""
    try:
        response = send_from_directory('.', 'tonconnect-manifest.json', mimetype='application/json')
        response.headers['Access-Control-Allow-Origin'] = '*'
        return response
    except Exception as e:
        print(f"❌ Manifest Error: {e}")
        return jsonify({"success": False, "error": "Manifest file not found"}), 404

@app.route('/api/user/info', methods=['GET', 'POST'])
def get_user_info_main():
    """جلب وتأكيد بيانات المستخدم والتحقق المباشر من حالة الحظر"""
    is_post = (request.method == 'POST')
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=is_post)
    
    # محاولة الحصول على ID من المعلمات في حالة عدم إرسال initData (للتطوير المحلي فقط)
    if not success:
        tg_id_param = request.args.get('tg_id') or (request.json.get('tg_id') if request.is_json and request.json else None)
        if tg_id_param:
            telegram_id = str(tg_id_param)
        else:
            return error_res
        
    try:
        # فحص حالة الحظر من قاعدة البيانات
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
            user_data = database.get_user(telegram_id) or {}
            
        balance = float(user_data.get('balance', 0.0))
        return jsonify({
            "success": True, 
            "user": user_data,
            "player": user_data,
            "balance": balance,
            "uid": telegram_id
        }), 200
    except Exception as e:
        print(f"❌ Error fetching user info for {telegram_id}: {e}")
        return jsonify({"success": False, "error": "حدث خطأ أثناء جلب بيانات الحساب"}), 500

# ==========================================
# الأمان والتحكم بالهيدرز والملفات الثابتة
# ==========================================

@app.after_request
def add_security_headers(response):
    """منع التخزين المؤقت (Cache) لمسارات الـ API لضمان دقة البيانات اللحظية"""
    if request.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response

@app.errorhandler(500)
def handle_500_error(e):
    return jsonify({
        "status": "error", 
        "success": False, 
        "error": "حدث خطأ داخلي في السيرفر", 
        "message": "خطأ في الاتصال بالخادم."
    }), 500

@app.errorhandler(404)
def handle_404_error(e):
    if request.path.startswith('/api/'):
        return jsonify({
            "status": "error", 
            "success": False, 
            "error": "المسار غير موجود", 
            "message": "خطأ في الاتصال بالخادم."
        }), 404
    return send_from_directory('.', 'index.html')

@app.route('/')
def serve_index():
    return send_from_directory('.', 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    """تقديم الملفات الثابتة وتأمين الملفات البرمجية والحساسة تحديداً"""
    path_lower = path.lower()
    
    if path_lower == 'tonconnect-manifest.json':
        return serve_tonconnect_manifest()
    
    forbidden_extensions = ('.py', '.env', '.sh', '.git', '.pem', '.key')
    forbidden_files = ('firebase-adminsdk.json', 'config.json', 'requirements.txt')
    
    if any(path_lower.endswith(ext) for ext in forbidden_extensions) or any(f in path_lower for f in forbidden_files):
        return jsonify({"success": False, "error": "Access Denied"}), 403
        
    try:
        return send_from_directory('.', path)
    except Exception:
        return send_from_directory('.', 'index.html')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
