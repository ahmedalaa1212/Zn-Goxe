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

app = Flask(__name__)
# السماح للواجهة بالاتصال بالسيرفر (ضروري لتليجرام WebApp)
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

# ==========================================
# 3. إعدادات الحماية والتوجيه (Security & Static)
# ==========================================
@app.after_request
def add_security_headers(response):
    # منع الكاش لضمان تحديث البيانات فوراً وعدم حفظ بيانات حساسة
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, public, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route('/')
def serve_index():
    return send_from_directory('.', 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    # 🛡️ حماية صارمة: منع الوصول لملفات البايثون، الإعدادات، ومفتاح الفايربيس
    forbidden_extensions = ('.py', '.env', '.json', '.md')
    
    # 🟢 المجلدات المحظور الوصول إليها مباشرة من المتصفح
    forbidden_dirs = ('core/', 'api/', '.git/')
    
    # التحقق من الأمان قبل إرسال الملف
    if path.endswith(forbidden_extensions) or any(path.startswith(d) for d in forbidden_dirs) or path == 'requirements.txt':
        return jsonify({"error": "Access Denied", "message": "غير مصرح لك بالوصول لهذا الملف"}), 403
    
    return send_from_directory('.', path)

# ==========================================
# 4. فحص حالة السيرفر (Health Check)
# ==========================================
@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({"success": True, "status": "active"}), 200

# ==========================================
# تشغيل السيرفر
# ==========================================
if __name__ == '__main__':
    # بورت 8080 مناسب جداً لاستضافة Railway
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
