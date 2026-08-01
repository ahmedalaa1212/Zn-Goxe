import os
from flask import Flask, jsonify, send_from_directory, request
from flask_cors import CORS

# استدعاء ملف database لتهيئة قواعد البيانات
import database
from core.security import get_authenticated_user

# ==========================================
# 1. إعداد التطبيق والمتغيرات الأساسية
# ==========================================
app = Flask(__name__)

# تفعيل CORS لجميع مسارات الـ API بدون قيود
CORS(app, resources={r"/api/*": {"origins": "*"}}, supports_credentials=True)

WEB_URL = os.environ.get('WEB_URL', 'https://zn-goxe-production.up.railway.app').strip().rstrip('/')

if not WEB_URL.startswith('http'):
    WEB_URL = f"https://{WEB_URL}"

# ==========================================
# 2. استدعاء وتسجيل مسارات القوائم (Blueprints)
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
# 3. مسار جلب بيانات المستخدم المباشر /api/user/info
# ==========================================
@app.route('/api/user/info', methods=['GET', 'POST'])
def get_user_info_main():
    is_post = (request.method == 'POST')
    success, telegram_id, error_res = get_authenticated_user(request, is_post=is_post)
    if not success:
        return error_res
        
    try:
        user_data = database.get_user(telegram_id)
        if not user_data:
            return jsonify({"success": False, "error": "المستخدم غير موجود"}), 404
            
        return jsonify({
            "success": True,
            "user": user_data
        }), 200
    except Exception as e:
        print(f"Error fetching user info: {e}")
        return jsonify({"success": False, "error": "خطأ في جلب البيانات"}), 500

# ==========================================
# 4. إعدادات الحماية وتمرير الهيدرز
# ==========================================
@app.after_request
def add_security_headers(response):
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, public, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

# ==========================================
# 5. معالجة الأخطاء العالمية (تصحيح أكواد الحالة)
# ==========================================
@app.errorhandler(500)
def handle_500_error(e):
    return jsonify({
        "success": False,
        "error": "حدث خطأ داخلي في السيرفر (500). يرجى التأكد من الاتصال بقاعدة البيانات."
    }), 500  # ✅ تم تعديل الكود إلى 500 لمنع تصفير الرصيد في الفرونت إند

@app.errorhandler(404)
def handle_404_error(e):
    if request.path.startswith('/api/'):
        return jsonify({
            "success": False,
            "error": "المسار المطلوب غير موجود في السيرفر (404)."
        }), 404  # ✅ تم تعديل الكود إلى 404
    return send_from_directory('.', 'index.html')

# ==========================================
# 6. مسارات TON Connect والصفحة الرئيسية
# ==========================================
@app.route('/tonconnect-manifest.json')
def serve_manifest():
    return jsonify({
        "url": WEB_URL,
        "name": "ZN Goxe Web3",
        "iconUrl": f"{WEB_URL}/static/icon.png",
        "termsOfServiceUrl": f"{WEB_URL}/terms",
        "privacyPolicyUrl": f"{WEB_URL}/privacy"
    }), 200

@app.route('/')
def serve_index():
    return send_from_directory('.', 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    if path == 'tonconnect-manifest.json':
        return serve_manifest()

    forbidden_extensions = ('.py', '.env', '.md', '.txt')
    forbidden_dirs = ('core/', 'admin_chat/', '.git/', '.github/')
    
    if any(path.startswith(d) for d in forbidden_dirs) or (path.endswith(forbidden_extensions) and path != 'favicon.ico'):
        return jsonify({"error": "Access Denied", "message": "غير مصرح لك بالوصول لهذا الملف"}), 403
    
    try:
        return send_from_directory('.', path)
    except Exception:
        return send_from_directory('.', 'index.html')

# ==========================================
# 7. فحص حالة السيرفر والتشغيل
# ==========================================
@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({
        "success": True, 
        "status": "active",
        "service": "ZN Goxe Backend"
    }), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    print(f"🚀 Server is running on port {port}...")
    app.run(host='0.0.0.0', port=port)
