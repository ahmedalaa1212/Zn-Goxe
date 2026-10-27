# -*- coding: utf-8 -*-
import os
import sys
from datetime import datetime, timezone
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
    """استدعاء آمن لـ Blueprint سواء كان في مجلد رئيسي أو فرعي دون إيقاف السيرفر."""
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

    # 💎 موديول محفظة ZNX والمتصدرين
    ('znx_wallet', 'znx_wallet_bp', '/api/znx-wallet'),

    # ⚡ موديولات الألعاب
    ('games', 'games_bp', '/api/games'),
    ('games.card_api', 'card_bp', '/api/games/card'),

    # 🏆 أرباح العروض
    ('offers', 'offers_bp', '/api/offers'),
]

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
# 🛡️ الحارس الأمني الشامل لكل طلبات الـ API
# ==========================================
@app.before_request
def global_api_security_guard():
    """
    حماية مركزية شاملة لجميع نقاط الاتصال (/api/*):
    تمنع أي طلب غير موثق بتوقيع تليجرام، وتفحص بصمة الجهاز وحالة الحظر قبل الوصول لأي موديول فرعي.
    """
    if request.method == 'OPTIONS':
        return jsonify({"success": True}), 200

    path = request.path or ""
    if not path.startswith('/api/'):
        return None

    # استثناء مسار فحص نبض السيرفر
    if path in ('/api/health', '/api/health/'):
        return None

    # مسارات السوبر أدمن لها التحقق الإداري الخاص بها أيضاً، ولكن نوثق هوية التليجرام أولاً
    is_super_admin_route = path.startswith('/api/super-admin')
    success, tg_id, user_info, error_res = get_authenticated_user(
        request,
        is_post=(request.method == 'POST'),
        enforce_device_check=(not is_super_admin_route)
    )

    if not success or not tg_id:
        return error_res

    return None


# ==========================================
# 🔍 دالة استخراج وتوثيق معرف تليجرام الآمنة
# ==========================================
def extract_telegram_user_from_request(req):
    """
    استخراج بيانات مستخدم تليجرام الموثقة حصرياً عبر التوقيع الرقمي (core.security).
    تم إغلاق كافة الثغرات التي كانت تسمح بتمرير tg_id مزيف عبر الرابط أو JSON.
    """
    is_post = (req.method == 'POST')
    success, tg_id, user_info, error_res = get_authenticated_user(req, is_post=is_post)
    if success and tg_id:
        return True, str(tg_id).strip(), user_info or {}, None
    return False, None, {}, error_res


def extract_device_info_from_request(req):
    """استخراج معرّف الجهاز والبصمة الممررة في الطلب"""
    req_json = req.get_json(silent=True) if req.is_json else {}
    if not isinstance(req_json, dict):
        req_json = {}

    device_id = (
        req.headers.get('X-Device-Id') or
        req.args.get('device_id') or
        req.args.get('deviceId') or
        req_json.get('device_id') or
        req_json.get('deviceId')
    )

    fingerprint = (
        req.headers.get('X-Device-Fingerprint') or
        req.args.get('device_fingerprint') or
        req.args.get('fingerprint') or
        req.args.get('fingerprint_hash') or
        req.args.get('deviceFingerprint') or
        req_json.get('device_fingerprint') or
        req_json.get('fingerprint') or
        req_json.get('fingerprint_hash') or
        req_json.get('deviceFingerprint')
    )

    clean_device_id = str(device_id).strip() if device_id and str(device_id).strip() not in ("None", "null", "", "undefined") else None
    clean_fingerprint = str(fingerprint).strip() if fingerprint and str(fingerprint).strip() not in ("None", "null", "", "undefined") else None

    return clean_device_id, clean_fingerprint


# ==========================================
# 🌐 مسارات الخدمة والمستخدم الأساسية
# ==========================================

@app.route('/api/health', methods=['GET'])
def health_check():
    """مسار اختبار الجاهزية للسيرفر (Railway Health Check)"""
    return jsonify({"status": "ok", "message": "Server is running smoothly"}), 200


@app.route('/')
def serve_index():
    """تقديم الواجهة الرئيسية للـ Telegram Mini App"""
    try:
        return send_from_directory(BASE_DIR, 'index.html')
    except Exception as e:
        print(f"❌ Index File Error: {e}")
        return jsonify({"success": False, "error": "Index file not found"}), 404


@app.route('/tonconnect-manifest.json')
def serve_tonconnect_manifest():
    """تقديم ملف بيانات TON Connect"""
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
    """خدمة الملفات الثابتة للواجهة فقط ومنع الوصول لملفات السيرفر البرمجية (.py, .env)"""
    try:
        clean_name = filename.strip('/').lower()
        if '..' in clean_name or clean_name.startswith('.'):
            return jsonify({"success": False, "error": "Access Denied"}), 403

        # منع قراءة أي ملفات برمجية أو إعدادات حساسة
        forbidden_extensions = ('.py', '.pyc', '.env', '.sh', '.sql', '.db', '.sqlite', '.log', '.txt')
        forbidden_files = ('firebase-adminsdk.json', 'config.json', 'credentials.json', 'package.json', 'package-lock.json')
        if clean_name.endswith(forbidden_extensions) or any(f in clean_name for f in forbidden_files):
            return jsonify({"success": False, "error": "Access Denied"}), 403

        safe_base = os.path.abspath(BASE_DIR)
        file_path = os.path.abspath(os.path.join(BASE_DIR, filename))

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


# ==========================================
# 🔄 نقطة نهاية API النشاط اليومي (Ping/Sync)
# ==========================================

@app.route('/api/ping', methods=['POST', 'OPTIONS'])
def sync_user_activity():
    """استقبال طلب إشارة النشاط (Ping) وتحديث حقل last_active_at للمستخدم الموثق"""
    if request.method == 'OPTIONS':
        return jsonify({"success": True}), 200

    try:
        success, user_id, _, err_res = extract_telegram_user_from_request(request)
        if not success or not user_id:
            return err_res or (jsonify({"success": False, "message": "Unauthorized"}), 401)

        if hasattr(database, 'update_user_last_active'):
            database.update_user_last_active(user_id)

        return jsonify({
            "success": True,
            "message": "Activity updated",
            "server_time": datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        }), 200

    except Exception as e:
        print(f"❌ Error updating activity ping: {e}")
        return jsonify({"success": False, "error": "خطأ في تحديث النشاط"}), 500


@app.route('/api/user/info', methods=['GET', 'POST', 'OPTIONS'])
def get_user_info_main():
    """جلب بيانات حساب المستخدم والتحقق الصارم من الحظر وبصمة الجهاز"""
    if request.method == 'OPTIONS':
        return jsonify({"success": True}), 200

    success, telegram_id, user_info, err_response = extract_telegram_user_from_request(request)
    if not success or not telegram_id:
        return err_response or (jsonify({"success": False, "error": "تعذر التوثيق أو معرف المستخدم غير متاح"}), 401)

    try:
        user_data = database.get_user(telegram_id)

        # إن لم يكن المستخدم مسجلاً بعد، يتم إنشاؤه أولاً ثم ربط جهازه فوراً
        if not user_data or not isinstance(user_data, dict) or len(user_data) == 0:
            first_name = user_info.get('first_name', 'لاعب') if isinstance(user_info, dict) else 'لاعب'
            ref_id = user_info.get('start_param') if isinstance(user_info, dict) else None
            user_data = database.init_user(telegram_id, ref_id=ref_id, first_name=first_name)

        # تحديث اسم المستخدم أو اليوزرنيم إذا تغير في تليجرام
        if isinstance(user_info, dict) and user_data:
            updates = {}
            tg_username = user_info.get('username') or ''
            if tg_username and user_data.get('username') != tg_username:
                updates['username'] = tg_username
            if updates:
                database.update_user(telegram_id, updates)

        # تأكيد ربط الجهاز بعد ضمان وجود السجل في جدول users
        device_id, fingerprint = extract_device_info_from_request(request)
        if (device_id or fingerprint) and hasattr(database, 'check_and_bind_device'):
            device_check = database.check_and_bind_device(telegram_id, device_id, fingerprint)
            if isinstance(device_check, dict) and (device_check.get('banned') or device_check.get('allowed') is False):
                ban_reason = device_check.get('reason') or "تم حظر الحساب والجهاز فوراً لاكتشاف تعدد الحسابات على نفس الجهاز."
                return jsonify({
                    "success": False,
                    "error": ban_reason,
                    "banned": True,
                    "is_banned": True
                }), 403

        if hasattr(database, 'is_user_banned') and database.is_user_banned(telegram_id):
            return jsonify({
                "success": False,
                "error": "تم حظر هذا الحساب وجميع الحسابات المرتبطة بهذا الجهاز بسبب تعدد الحسابات",
                "banned": True,
                "is_banned": True
            }), 403

        balance = float(user_data.get('balance', 0.0))
        usd_balance = float(user_data.get('usd_balance', 0.0))
        znx_balance = float(user_data.get('znx_balance', 0.0))
        ad_balance = float(user_data.get('ad_balance', 0.0))

        return jsonify({
            "success": True,
            "user": user_data,
            "player": user_data,
            "balance": balance,
            "usd_balance": usd_balance,
            "znx_balance": znx_balance,
            "ad_balance": ad_balance,
            "uid": str(telegram_id),
            "server_time": datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        }), 200

    except Exception as e:
        print(f"❌ Error fetching user info for {telegram_id}: {e}")
        return jsonify({"success": False, "error": "حدث خطأ أثناء جلب بيانات الحساب"}), 500


# ==========================================
# 🔄 التوافق الاحتياطي لمسار المتصدرين القديم
# ==========================================

@app.route('/api/leaderboard/init', methods=['GET', 'POST', 'OPTIONS'])
@app.route('/api/leaderboard/data', methods=['GET', 'POST', 'OPTIONS'])
def legacy_leaderboard_data():
    if request.method == 'OPTIONS':
        return jsonify({"success": True}), 200
    try:
        from znx_wallet.znx_wallet_api import get_wallet_data
        return get_wallet_data()
    except Exception as e:
        print(f"⚠️ Legacy leaderboard direct handler error: {e}")
        return redirect('/api/znx-wallet/data', code=307)


@app.route('/api/leaderboard/convert', methods=['POST', 'OPTIONS'])
def legacy_leaderboard_convert():
    if request.method == 'OPTIONS':
        return jsonify({"success": True}), 200
    try:
        from znx_wallet.znx_wallet_api import process_conversion
        return process_conversion()
    except Exception as e:
        print(f"⚠️ Legacy conversion direct handler error: {e}")
        return redirect('/api/znx-wallet/convert', code=307)


@app.route('/api/leaderboard', methods=['GET', 'POST', 'OPTIONS'])
@app.route('/api/leaderboard/<path:subpath>', methods=['GET', 'POST', 'OPTIONS'])
def leaderboard_legacy_fallback(subpath=""):
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
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Requested-With, X-Telegram-User-Id, X-Telegram-Init-Data, X-Init-Data, X-Device-Id, X-Device-Fingerprint, X-User-ID, X-Admin-ID'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS, PUT, DELETE'
    return response


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
