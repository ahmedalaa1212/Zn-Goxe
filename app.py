import os
import sys
from flask import Flask, jsonify, send_from_directory, request, redirect
from flask_cors import CORS

# 🎯 إدراج مسار المشروع الرئيسي لتجاوز حاجة الملفات إلى __init__.py
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import database
from core.security import get_authenticated_user

app = Flask(__name__, static_folder=BASE_DIR, static_url_path='')

# ==========================================
# 🛡️ إعدادات CORS والأمان العامة
# ==========================================
CORS(app, resources={r"/api/*": {"origins": "*"}}, supports_credentials=True)

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
        if hasattr(mod, blueprint_name):
            return getattr(mod, blueprint_name)
    except Exception:
        pass
        
    try:
        mod = __import__(f"{module_path}.{module_path}_api", fromlist=[blueprint_name])
        if hasattr(mod, blueprint_name):
            return getattr(mod, blueprint_name)
    except Exception:
        pass
        
    try:
        mod = __import__(f"{module_path}_api", fromlist=[blueprint_name])
        if hasattr(mod, blueprint_name):
            return getattr(mod, blueprint_name)
    except Exception:
        pass
        
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
    ('users', 'users_bp', '/api/users'),
    ('super_admin', 'super_admin_bp', '/api/super-admin'),
    ('ads', 'ads_bp', '/api/ads'),
    
    # 💳 موديولات المحفظة
    ('wallet', 'wallet_bp', '/api/wallet'),
    ('wallet.deposit.deposit_api', 'deposit_bp', '/api/wallet/deposit'),
    ('wallet.withdraw.withdraw_api', 'withdraw_bp', '/api/wallet/withdraw'),
    ('wallet.history.history_api', 'history_bp', '/api/wallet/history'),
    ('wallet.exchange.exchange_api', 'exchange_bp', '/api/wallet/exchange'),
    
    # 💎 موديول محفظة ZNX والمتصدرين الجديد
    ('znx_wallet', 'znx_wallet_bp', '/api/znx-wallet'),
    
    # ⚡ موديولات الألعاب
    ('games', 'games_bp', '/api/games'),
    ('games.card_api', 'card_bp', '/api/games/card'),
    
    # 🏆 أرباح العروض
    ('offers', 'offers_bp', '/api/offers'),
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
    else:
        print(f"ℹ️ لم يتم العثور على الموديول: {bp_name} في المسار {mod_path}")

# ==========================================
# 🔍 دالة استخراج وتوثيق معرف تليجرام الشاملة
# ==========================================
def extract_telegram_user_from_request(req):
    """
    استخراج بيانات مستخدم تليجرام الموثقة أو الممررة من مختلف المصادر (Headers, Query String, JSON Body)
    لمنع فشل طلبات GET وحل مشكلة الشاشة الفارغة وعدم إنشاء حسابات Firebase.
    """
    is_post = (req.method == 'POST')
    
    # 1. محاولة التوثيق عبر التوقيع الرقمي (core.security)
    try:
        success, tg_id, user_info, error_res = get_authenticated_user(req, is_post=is_post)
        if success and tg_id and str(tg_id).strip() not in ("None", "null", "", "undefined"):
            return True, str(tg_id).strip(), user_info or {}, None
    except Exception as e:
        print(f"⚠️ Security Auth Check Exception: {e}")

    # 2. الاستخراج الاحتياطي من Query Parameters أو Headers أو JSON Body
    req_json = req.get_json(silent=True) if req.is_json else {}
    if not isinstance(req_json, dict):
        req_json = {}

    direct_id = (
        req.args.get('tg_id') or 
        req.args.get('telegram_id') or 
        req.args.get('user_id') or 
        req_json.get('tg_id') or 
        req_json.get('telegram_id') or 
        req_json.get('user_id') or 
        req.headers.get('X-Telegram-User-Id')
    )

    init_data_str = (
        req.args.get('initData') or 
        req.args.get('init_data') or 
        req_json.get('initData') or 
        req.headers.get('X-Telegram-Init-Data') or 
        req.headers.get('Authorization')
    )

    extracted_user_info = {}
    if init_data_str:
        try:
            from urllib.parse import parse_qs
            import json
            
            clean_init = str(init_data_str)
            if clean_init.startswith('Bearer '):
                clean_init = clean_init[7:]
            
            parsed_params = parse_qs(clean_init)
            if 'user' in parsed_params:
                user_json_str = parsed_params['user'][0]
                user_data = json.loads(user_json_str)
                if isinstance(user_data, dict):
                    if 'id' in user_data and user_data['id']:
                        direct_id = str(user_data['id'])
                    extracted_user_info = {
                        'first_name': user_data.get('first_name', 'لاعب'),
                        'last_name': user_data.get('last_name', ''),
                        'username': user_data.get('username', ''),
                        'language_code': user_data.get('language_code', 'ar')
                    }
            if 'start_param' in parsed_params:
                extracted_user_info['start_param'] = parsed_params['start_param'][0]
        except Exception as e:
            print(f"⚠️ Parsing initData fallback failed: {e}")

    if direct_id and str(direct_id).strip() not in ("None", "null", "", "undefined"):
        return True, str(direct_id).strip(), extracted_user_info, None

    return False, None, {}, (jsonify({"success": False, "error": "لم يتم تقديم معرف تليجرام صالح"}), 401)


# ==========================================
# 🌐 مسارات الخدمة والمستخدم الأساسية
# ==========================================

@app.route('/api/health', methods=['GET'])
def health_check():
    """مسار اختبار الجاهزية للسيرفر (Railway Health Check)"""
    return jsonify({"status": "ok", "message": "Server is running smoothly"}), 200


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
    """خدمة كافة الملفات الثابتة والأقسام الفرعية بشكل آمن ومحمي من ثغرات Directory Traversal"""
    try:
        safe_base = os.path.abspath(BASE_DIR)
        file_path = os.path.abspath(os.path.join(BASE_DIR, filename))
        
        # منع ثغرات Directory Traversal
        if not file_path.startswith(safe_base):
            return jsonify({"success": False, "error": "غير مسموح بالوصول لهذا المسار"}), 403

        if os.path.exists(file_path) and os.path.isfile(file_path):
            rel_path = os.path.relpath(file_path, safe_base)
            return send_from_directory(BASE_DIR, rel_path)
        elif os.path.isdir(file_path):
            index_in_dir = os.path.join(file_path, 'index.html')
            if os.path.exists(index_in_dir):
                rel_index = os.path.relpath(index_in_dir, safe_base)
                return send_from_directory(BASE_DIR, rel_index)
        
        return jsonify({"success": False, "error": f"File {filename} not found"}), 404
    except Exception as e:
        print(f"❌ Static File Error: {e}")
        return jsonify({"success": False, "error": "حدث خطأ أثناء جلب الملف"}), 500


@app.route('/api/user/info', methods=['GET', 'POST', 'OPTIONS'])
def get_user_info_main():
    """جلب بيانات حساب المستخدم والتحقق من الحظر وتهيئة الحسابات الجديدة تلقائياً في Firebase"""
    if request.method == 'OPTIONS':
        return jsonify({"success": True}), 200

    success, telegram_id, user_info, err_response = extract_telegram_user_from_request(request)
    
    if not success or not telegram_id:
        if err_response:
            return err_response
        return jsonify({"success": False, "error": "تعذر التوثيق أو معرف المستخدم غير متاح"}), 401

    try:
        # فحص حظر الحساب
        if database.is_user_banned(telegram_id):
            return jsonify({
                "success": False, 
                "error": "حسابك معطل حالياً بسبب مخالفة الشروط",
                "banned": True
            }), 403

        user_data = database.get_user(telegram_id)
        
        # إن لم يكن مستند المستخدم موجوداً، يتم إنشاؤه فوراً في Firestore
        if not user_data or not isinstance(user_data, dict) or len(user_data) == 0:
            first_name = user_info.get('first_name', 'لاعب') if isinstance(user_info, dict) else 'لاعب'
            ref_id = user_info.get('start_param') if isinstance(user_info, dict) else None
            
            user_data = database.init_user(telegram_id, ref_id=ref_id, first_name=first_name)
            
        balance = float(user_data.get('balance', 0.0))
        usd_balance = float(user_data.get('usd_balance', 0.0))
        znx_balance = float(user_data.get('znx_balance', 0.0))

        return jsonify({
            "success": True, 
            "user": user_data,
            "player": user_data,
            "balance": balance,
            "usd_balance": usd_balance,
            "znx_balance": znx_balance,
            "uid": str(telegram_id)
        }), 200

    except Exception as e:
        print(f"❌ Error fetching user info for {telegram_id}: {e}")
        return jsonify({"success": False, "error": "حدث خطأ أثناء جلب بيانات الحساب"}), 500


# ==========================================
# 🔄 التوافق الاحتياطي لمسار المتصدرين القديم
# ==========================================

@app.route('/api/leaderboard', methods=['GET', 'POST', 'OPTIONS'])
@app.route('/api/leaderboard/<path:subpath>', methods=['GET', 'POST', 'OPTIONS'])
def leaderboard_legacy_fallback(subpath=""):
    """
    تحويل تلقائي لجميع الطلبات القادمة للمسار القديم /api/leaderboard 
    إلى المسار الجديد /api/znx-wallet لتفادي توقف النسخ القديمة وضمان العمل بدون انكسار.
    """
    if request.method == 'OPTIONS':
        return jsonify({"success": True}), 200

    target = f"/api/znx-wallet/{subpath}".rstrip('/') if subpath else "/api/znx-wallet/data"
    if request.query_string:
        target += f"?{request.query_string.decode('utf-8')}"

    return redirect(target, code=307)


# ==========================================
# 🔒 الأمان وحماية الملفات ومعالجة CORS
# ==========================================

@app.after_request
def add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Requested-With, X-Telegram-User-Id, X-Telegram-Init-Data'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS, PUT, DELETE'
    return response

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
