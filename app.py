import os
import sys

# 🎯 إدراج مسار المشروع الرئيسي لتجاوز حاجة الملفات إلى __init__.py
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
# 🔌 دالة استدعاء الموديولات الموحدة والآمنة
# ==========================================
def safe_import_blueprint(module_path, blueprint_name):
    """
    استدعاء آمن لـ Blueprint سواء كان في مجلد رئيسي أو فرعي دون إيقاف السيرفر.
    """
    try:
        mod = __import__(module_path, fromlist=[blueprint_name])
        return getattr(mod, blueprint_name)
    except Exception:
        try:
            mod = __import__(f"{module_path}.{module_path}_api", fromlist=[blueprint_name])
            return getattr(mod, blueprint_name)
        except Exception:
            try:
                mod = __import__(f"{module_path}_api", fromlist=[blueprint_name])
                return getattr(mod, blueprint_name)
            except Exception:
                return None

# ==========================================
# 🔌 قائمة تسجيل الموديولات (Blueprints)
# ==========================================
blueprints_config = [
    # (مسار الموديول/المجلد, اسم الـ Blueprint, بادئة المسار)
    ('farm', 'farm_bp', '/api/farm'),
    ('settings', 'settings_bp', '/api/settings'),
    ('friends', 'friends_bp', '/api/friends'),
    ('tasks', 'tasks_bp', '/api/tasks'),
    ('shop', 'shop_bp', '/api/shop'),
    ('support', 'support_bp', '/api/support'),
    ('admin_chat', 'admin_chat_bp', '/api/admin-chat'),
    
    # 💳 موديولات المحفظة (الرئيسية والفرعية)
    ('wallet', 'wallet_bp', '/api/wallet'),
    ('wallet.deposit.deposit_api', 'deposit_bp', '/api/wallet/deposit'),
    ('wallet.withdraw.withdraw_api', 'withdraw_bp', '/api/wallet/withdraw'),
    ('wallet.history.history_api', 'history_bp', '/api/wallet/history'),
    ('wallet.exchange.exchange_api', 'exchange_bp', '/api/wallet/exchange'),
    
    # ⚡ موديولات الألعاب (الرئيسية والفرعية)
    ('games', 'games_bp', '/api/games'),
    ('games.card_api', 'card_bp', '/api/games/card'),
]

# تنفيذ التسجيل التلقائي للموديولات
for mod_path, bp_name, prefix in blueprints_config:
    bp = safe_import_blueprint(mod_path, bp_name)
    if bp:
        try:
            app.register_blueprint(bp, url_prefix=prefix)
            print(f"✅ تم تسجيل الموديول: {bp_name} على المسار {prefix}")
        except Exception as e:
            print(f"⚠️ خطأ أثناء تسجيل {bp_name}: {e}")

# ==========================================
# 🌐 مسارات الخدمة والمستخدم الأساسية
# ==========================================

@app.route('/')
def serve_index():
    """تقديم الواجهة الرئيسية للـ Telegram Mini App وإصلاح خطأ 404"""
    try:
        return send_from_directory(BASE_DIR, 'index.html')
    except Exception as e:
        print(f"❌ Index File Error: {e}")
        return jsonify({"success": False, "error": "Index file not found"}), 404


@app.route('/tonconnect-manifest.json')
def serve_tonconnect_manifest():
    """تقديم ملف بيانات TON Connect لمنع مشاكل الـ CORS في المحافظ"""
    try:
        response = send_from_directory(BASE_DIR, 'tonconnect-manifest.json', mimetype='application/json')
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        return response
    except Exception as e:
        print(f"❌ Manifest Error: {e}")
        return jsonify({"success": False, "error": "Manifest file not found"}), 404


@app.route('/<path:filename>')
def serve_static_files(filename):
    """خدمة كافة الملفات الثابتة والأقسام الفرعية بشكل مباشر (مثل مجلد wallet ومحتوياته deposit, withdraw, history)"""
    file_path = os.path.join(BASE_DIR, filename)
    if os.path.exists(file_path) and os.path.isfile(file_path):
        return send_from_directory(BASE_DIR, filename)
    elif os.path.isdir(file_path):
        index_in_dir = os.path.join(file_path, 'index.html')
        if os.path.exists(index_in_dir):
            return send_from_directory(file_path, 'index.html')
    return jsonify({"success": False, "error": f"File {filename} not found"}), 404


@app.route('/api/user/info', methods=['GET', 'POST'])
def get_user_info_main():
    """جلب بيانات حساب المستخدم والتحقق من الحظر وتهيئة الحسابات الجديدة"""
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
        # فحص حظر الحساب
        if hasattr(database, 'is_user_banned') and database.is_user_banned(telegram_id):
            return jsonify({
                "success": False, 
                "error": "حسابك معطل حالياً بسبب مخالفة الشروط",
                "banned": True
            }), 403

        user_data = database.get_user(telegram_id)
        
        # تهيئة حساب جديد إن لم يكن موجوداً
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
# 🔒 الأمان وحماية الملفات
# ==========================================

@app.after_request
def add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    return response

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
