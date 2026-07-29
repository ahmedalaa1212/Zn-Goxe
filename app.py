import os
from flask import Flask, jsonify, send_from_directory, request
from flask_cors import CORS

# ==========================================
# 1. استدعاء ملفات القوائم (Blueprints)
# ==========================================
from farm.farm_api import farm_bp
from settings.settings_api import settings_bp
from friends.friends_api import friends_bp
from games.games_api import games_bp
from tasks.tasks_api import tasks_bp
from shop.shop_api import shop_bp
from wallet.wallet_api import wallet_bp
from support.support_api import support_bp

app = Flask(__name__)
CORS(app)

# ==========================================
# 2. تسجيل مسارات القوائم (Routing)
# ==========================================
app.register_blueprint(farm_bp, url_prefix='/api/farm')
app.register_blueprint(settings_bp, url_prefix='/api/settings')
app.register_blueprint(friends_bp, url_prefix='/api/friends')
app.register_blueprint(games_bp, url_prefix='/api/games')
app.register_blueprint(tasks_bp, url_prefix='/api/tasks')
app.register_blueprint(shop_bp, url_prefix='/api/shop')
app.register_blueprint(wallet_bp, url_prefix='/api/wallet')
app.register_blueprint(support_bp, url_prefix='/api/support')

# ==========================================
# 3. إعدادات الحماية والتوجيه (Security & Static)
# ==========================================
@app.after_request
def add_security_headers(response):
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, public, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

# مسار خاص وضروري لمكتبة TON Connect
@app.route('/tonconnect-manifest.json')
def serve_manifest():
    return jsonify({
        "url": "https://zn-goxe-production.up.railway.app",
        "name": "ZN Goxe Bot",
        "iconUrl": "https://zn-goxe-production.up.railway.app/favicon.ico",
        "termsOfDeliveryUrl": "https://zn-goxe-production.up.railway.app",
        "privacyPolicyUrl": "https://zn-goxe-production.up.railway.app"
    }), 200

@app.route('/')
def serve_index():
    return send_from_directory('.', 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    # السماح بملف المانفيست واستثناء بقية الملفات الحساسة
    if path == 'tonconnect-manifest.json':
        return serve_manifest()

    forbidden_extensions = ('.py', '.env', '.json', '.md')
    forbidden_dirs = ('core/', 'api/', '.git/')
    
    if path.endswith(forbidden_extensions) or any(path.startswith(d) for d in forbidden_dirs) or path == 'requirements.txt':
        return jsonify({"error": "Access Denied", "message": "غير مصرح لك بالوصول لهذا الملف"}), 403
    
    return send_from_directory('.', path)

# ==========================================
# 4. فحص حالة السيرفر (Health Check)
# ==========================================
@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({"success": True, "status": "active"}), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
