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
# 🔌 تسجيل موديولات المسارات (Blueprints)
# ==========================================

# الدوال الاستعراضية مع المحافظة على الأمان والاستدعاء المرن
def safe_import_blueprint(module_name, blueprint_name):
    try:
        mod = __import__(f"{module_name}.{module_name}_api", fromlist=[blueprint_name])
        return getattr(mod, blueprint_name)
    except Exception:
        try:
            mod = __import__(f"{module_name}_api", fromlist=[blueprint_name])
            return getattr(mod, blueprint_name)
        except Exception as e:
            print(f"⚠️ فشل استدعاء {module_name}: {e}")
            return None

farm_bp = safe_import_blueprint('farm', 'farm_bp')
settings_bp = safe_import_blueprint('settings', 'settings_bp')
friends_bp = safe_import_blueprint('friends', 'friends_bp')
tasks_bp = safe_import_blueprint('tasks', 'tasks_bp')
shop_bp = safe_import_blueprint('shop', 'shop_bp')
support_bp = safe_import_blueprint('support', 'support_bp')
admin_chat_bp = safe_import_blueprint('admin_chat', 'admin_chat_bp')

if farm_bp: app.register_blueprint(farm_bp, url_prefix='/api/farm')
if settings_bp: app.register_blueprint(settings_bp, url_prefix='/api/settings')
if friends_bp: app.register_blueprint(friends_bp, url_prefix='/api/friends')
if tasks_bp: app.register_blueprint(tasks_bp, url_prefix='/api/tasks')
if shop_bp: app.register_blueprint(shop_bp, url_prefix='/api/shop')
if support_bp: app.register_blueprint(support_bp, url_prefix='/api/support')
if admin_chat_bp: app.register_blueprint(admin_chat_bp, url_prefix='/api/admin-chat')

# 💳 تسجيل موديول المحفظة الرئيسي بشكل نقي وقوي جداً
wallet_bp = None
try:
    from wallet.wallet_api import wallet_bp
except ImportError:
    try:
        from wallet_api import wallet_bp
    except ImportError as e:
        print(f"❌ تعذر استدعاء ملف wallet_api: {e}")

if wallet_bp:
    try:
        app.register_blueprint(wallet_bp, url_prefix='/api/wallet')
        print("✅ تم تسجيل موديول المحفظة (wallet_bp) بنجاح على /api/wallet!")
    except Exception as e:
        print(f"❌ تعذر تسجيل موديول المحفظة في Flask: {e}")

# ⚡ تسجيل موديول الألعاب بشكل آمن
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
    """تقديم ملف بيانات TON Connect لمنع مشاكل الـ CORS في المحافظ"""
    try:
        response = send_from_directory(BASE_DIR, 'tonconnect-manifest.json', mimetype='application/json')
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        return response
    except Exception as e:
        print(f"❌ Manifest Error: {e}")
        return jsonify({"success": False, "error": "Manifest file not found"}), 404


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
# 🔒 الأمان وحماية الملفات والحجم
# ==========================================

@app.after
