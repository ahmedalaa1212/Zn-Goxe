import os
from flask import Flask, jsonify, send_from_directory, request
from flask_cors import CORS

import database
from core.security import get_authenticated_user

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "*"}})

WEB_URL = os.environ.get('WEB_URL', 'https://zn-goxe-production.up.railway.app').strip().rstrip('/')

# ==========================================
# تسجيل المسارات (Blueprints)
# ==========================================
from farm.farm_api import farm_bp
from settings.settings_api import settings_bp
from friends.friends_api import friends_bp
from games.games_api import games_bp
from tasks.tasks_api import tasks_bp
from shop.shop_api import shop_bp
from wallet.wallet_api import wallet_bp
from support.support_api import support_bp
from admin_chat.admin_chat_api import admin_chat_bp  # 🔹 تم إضافة استيراد مسار الدعم للأدمن

app.register_blueprint(farm_bp, url_prefix='/api/farm')
app.register_blueprint(settings_bp, url_prefix='/api/settings')
app.register_blueprint(friends_bp, url_prefix='/api/friends')
app.register_blueprint(games_bp, url_prefix='/api/games')
app.register_blueprint(tasks_bp, url_prefix='/api/tasks')
app.register_blueprint(shop_bp, url_prefix='/api/shop')
app.register_blueprint(wallet_bp, url_prefix='/api/wallet')
app.register_blueprint(support_bp, url_prefix='/api/support')
app.register_blueprint(admin_chat_bp, url_prefix='/api/admin/chat')  # 🔹 تم تسجيل Blueprint محادثات الأدمن

@app.route('/tonconnect-manifest.json')
def serve_tonconnect_manifest():
    return send_from_directory('.', 'tonconnect-manifest.json', mimetype='application/json')

@app.route('/api/user/info', methods=['GET', 'POST'])
def get_user_info_main():
    is_post = (request.method == 'POST')
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=is_post)
    if not success:
        return error_res
        
    try:
        user_data = database.get_user(telegram_id)
        if not user_data:
            first_name = user_info.get('first_name', 'لاعب') if isinstance(user_info, dict) else 'لاعب'
            ref_id = user_info.get('start_param') if isinstance(user_info, dict) else None
            
            database.init_user(telegram_id, ref_id=ref_id, first_name=first_name)
            user_data = database.get_user(telegram_id)
            
        return jsonify({"success": True, "user": user_data}), 200
    except Exception as e:
        print(f"Error fetching user info: {e}")
        return jsonify({"success": False, "error": "خطأ في جلب البيانات"}), 500

@app.after_request
def add_security_headers(response):
    if request.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
    return response

@app.errorhandler(500)
def handle_500_error(e):
    return jsonify({"success": False, "error": "حدث خطأ داخلي في السيرفر"}), 500

@app.errorhandler(404)
def handle_404_error(e):
    if request.path.startswith('/api/'):
        return jsonify({"success": False, "error": "المسار غير موجود"}), 404
    return send_from_directory('.', 'index.html')

@app.route('/')
def serve_index():
    return send_from_directory('.', 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    path_lower = path.lower()
    if path_lower == 'tonconnect-manifest.json':
        return send_from_directory('.', 'tonconnect-manifest.json', mimetype='application/json')
    forbidden = ('.py', '.env', '.json', '.sh', '.git')
    if any(path_lower.endswith(ext) for ext in forbidden):
        return jsonify({"error": "Access Denied"}), 403
    try:
        return send_from_directory('.', path)
    except Exception:
        return send_from_directory('.', 'index.html')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
