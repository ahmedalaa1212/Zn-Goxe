import os
import sys

# 🎯 إدراج مسار المشروع الرئيسي
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from flask import Flask, jsonify, send_from_directory, request
from flask_cors import CORS

import database
from core.security import get_authenticated_user

app = Flask(__name__, static_folder=BASE_DIR, static_url_path='')

# ==========================================
# 🛡️ إعدادات CORS والأمان العامة
# ==========================================
CORS(app, resources={r"/api/*": {"origins": "*"}})

WEB_URL = os.environ.get('WEB_URL', 'https://zn-goxe-production.up.railway.app').strip().rstrip('/')

# ==========================================
# 🔌 تسجيل موديولات المسارات (Blueprints)
# ==========================================
from farm.farm_api import farm_bp
from settings.settings_api import settings_bp
from friends.friends_api import friends_bp
from tasks.tasks_api import tasks_bp
from shop.shop_api import shop_bp
from support.support_api import support_bp
from admin_chat.admin_chat_api import admin_chat_bp

app.register_blueprint(farm_bp, url_prefix='/api/farm')
app.register_blueprint(settings_bp, url_prefix='/api/settings')
app.register_blueprint(friends_bp, url_prefix='/api/friends')
app.register_blueprint(tasks_bp, url_prefix='/api/tasks')
app.register_blueprint(shop_bp, url_prefix='/api/shop')
app.register_blueprint(support_bp, url_prefix='/api/support')
app.register_blueprint(admin_chat_bp, url_prefix='/api/admin-chat')

# 💳 تسجيل موديول المحفظة
try:
    from wallet.wallet_api import wallet_bp
    app.register_blueprint(wallet_bp, url_prefix='/api/wallet')
    print("✅ تم تسجيل موديول المحفظة (wallet_bp) بنجاح!")
except Exception as e:
    print(f"⚠️ تعذر تحميل موديول المحفظة الرئيسي: {e}")

# ⚡ تسجيل موديول الألعاب
try:
    from games.games_api import games_bp
    app.register_blueprint(games_bp)
    print("✅ تم تسجيل موديول الألعاب الرئيسي (games_bp) بنجاح!")
except Exception as e:
    print(f"⚠️ مجلد الألعاب غير موجود أو به خطأ، تم تخطيه: {e}")

# ==========================================
# 🌐 مسارات الخدمة والمستخدم الأساسية
# ==========================================

@app.route('/tonconnect-manifest.json')
def serve_tonconnect_manifest():
    try:
        response = send_from_directory(BASE_DIR, 'tonconnect-manifest.json', mimetype='application/json')
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        return response
    except Exception as e:
        return jsonify({"success": False, "error": "Manifest file not found"}), 404


@app.route('/api/user/info', methods=['GET', 'POST'])
def get_user_info_main():
    is_post = (request.method == 'POST')
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=is_post)
    
    if not success:
        req_json = request.get_json(silent=True) if request.is_json else {}
        tg_id_param = request.args.get('tg_id') or req_json.get('tg_id')
        if tg_id_param:
            telegram_id = str(tg_id_param).strip()
        else:
            return error_res
        
    try:
        if hasattr(database, 'is_user_banned') and database.is_user_banned(telegram_id):
            return jsonify({
                "success": False, 
                "error": "حسابك معطل حالياً بسبب مخالفة الشروط",
                "banned": True
            }), 403

        user_data = database.get_user(telegram_id)
        
        if not user_data:
            first_name = user_info.get('first_name', 'لاعب') if isinstance(user_info, dict) else 'لاعب'
            ref_id = user_info.get('start_param') if isinstance(user_info, dict) else None
            
            if hasattr(database, 'init_user'):
                database.init_user(telegram_id, ref_id=ref_id, first_name=first_name)
            user_data = database.get_user(telegram_id) or {}
            
        balance = float(user_data.get('balance', 0.0))
        usd_balance = float(user_data.get('usd_balance', 0.0))

        return jsonify({
            "success": True, 
            "user": user_data,
            "player": user_data,
            "balance": balance,
            "usd_balance": usd_balance,
            "uid": telegram_id
        }), 200

    except Exception as e:
        print(f"❌ Error fetching user info for {telegram_id}: {e}")
        return jsonify({"success": False, "error": "حدث خطأ أثناء جلب بيانات الحساب"}), 500

# ==========================================
# 🔒 الأمان وحماية الملفات والحجم
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
    return send_from_directory(BASE_DIR, 'index.html')


@app.route('/')
def serve_index():
    return send_from_directory(BASE_DIR, 'index.html')


@app.route('/<path:path>')
def serve_static(path):
    path_lower = path.lower()
    
    if path_lower == 'tonconnect-manifest.json':
        return serve_tonconnect_manifest()
    
    forbidden_extensions = ('.py', '.env', '.sh', '.git', '.pem', '.key', '.db', '.sqlite')
    forbidden_files = ('firebase-adminsdk.json', 'config.json', 'requirements.txt', 'dockerfile')
    
    if any(path_lower.endswith(ext) for ext in forbidden_extensions) or any(f in path_lower for f in forbidden_files):
        return jsonify({"success": False, "error": "Access Denied"}), 403
        
    target_file = os.path.join(BASE_DIR, path)
    if os.path.exists(target_file) and os.path.isfile(target_file):
        return send_from_directory(BASE_DIR, path)

    if path.startswith('api/') or any(path_lower.endswith(ext) for ext in ('.html', '.js', '.css', '.json')):
        return jsonify({"success": False, "error": "File not found"}), 404
        
    return send_from_directory(BASE_DIR, 'index.html')


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
