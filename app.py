import os
from flask import Flask, jsonify, send_from_directory, request
from flask_cors import CORS

# ==========================================
# 1. إعداد التطبيق المتغيرات الأساسية
# ==========================================
app = Flask(__name__)
CORS(app)

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
# 3. إعدادات الحماية وتمرير الهيدرز
# ==========================================
@app.after_request
def add_security_headers(response):
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, public, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

# ==========================================
# 4. مسارات تطبيق TON Connect والصفحة الرئيسية
# ==========================================
@app.route('/tonconnect-manifest.json')
def serve_manifest():
    """ملف البيان المعتمد لاتصال محفظة TON Connect"""
    return jsonify({
        "url": WEB_URL,
        "name": "ZN Goxe Bot",
        "iconUrl": f"{WEB_URL}/logo.png",
        "termsOfDeliveryUrl": WEB_URL,
        "privacyPolicyUrl": WEB_URL
    }), 200

@app.route('/')
def serve_index():
    return send_from_directory('.', 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    # السماح الصريح بملف المانفيست
    if path == 'tonconnect-manifest.json':
        return serve_manifest()

    # حظر الامتدادات والمجلدات الحساسة
    forbidden_extensions = ('.py', '.env', '.json', '.md', '.txt')
    forbidden_dirs = ('core/', 'admin_chat/', '.git/', '.github/')
    
    # السماح بالملفات العامة كـ (js, css, html, png, jpg, ico)
    if any(path.startswith(d) for d in forbidden_dirs) or (path.endswith(forbidden_extensions) and path != 'favicon.ico'):
        return jsonify({"error": "Access Denied", "message": "غير مصرح لك بالوصول لهذا الملف"}), 403
    
    try:
        return send_from_directory('.', path)
    except Exception:
        # في حالة طلب صفحة غير موجودة توجيهه إلى index.html
        return send_from_directory('.', 'index.html')

# ==========================================
# 5. فحص حالة السيرفر (Health Check)
# ==========================================
@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({
        "success": True, 
        "status": "active",
        "service": "ZN Goxe Backend"
    }), 200

# ==========================================
# 6. نقطة التشغيل الرئيسية
# ==========================================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    print(f"🚀 Server is running on port {port}...")
    app.run(host='0.0.0.0', port=port)
