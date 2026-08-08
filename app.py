import os
from flask import Flask, jsonify, send_from_directory, request
from flask_cors import CORS

import database
from core.security import get_authenticated_user

app = Flask(__name__)

# إعداد CORS للوصول إلى كافة مسارات API
CORS(app, resources={r"/api/*": {"origins": "*"}})

WEB_URL = os.environ.get('WEB_URL', 'https://zn-goxe-production.up.railway.app').strip().rstrip('/')

# ==========================================
# تسجيل المسارات (Blueprints) الخاصة بجميع موديولات المشروع
# ==========================================
from farm.farm_api import farm_bp
from settings.settings_api import settings_bp
from friends.friends_api import friends_bp
from games.games_api import games_bp
from tasks.tasks_api import tasks_bp
from shop.shop_api import shop_bp
from wallet.wallet_api import wallet_bp
from support.support_api import support_bp
from admin_chat.admin_chat_api import admin_chat_bp

# تسجيل مسارات الـ API مع البادئات المخصصة لكل موديول
app.register_blueprint(farm_bp, url_prefix='/api/farm')
app.register_blueprint(settings_bp, url_prefix='/api/settings')
app.register_blueprint(friends_bp, url_prefix='/api/friends')
app.register_blueprint(games_bp, url_prefix='/api/games')
app.register_blueprint(tasks_bp, url_prefix='/api/tasks')
app.register_blueprint(shop_bp, url_prefix='/api/shop')
app.register_blueprint(wallet_bp, url_prefix='/api/wallet')
app.register_blueprint(support_bp, url_prefix='/api/support')
app.register_blueprint(admin_chat_bp, url_prefix='/api/admin-chat')

# ==========================================
# مسارات للتكيف المباشر مع استدعاءات الجافاسكريبت القديمة والجديدة
# ==========================================

@app.route('/api/game/start', methods=['POST'])
@app.route('/api/game/step', methods=['POST'])
@app.route('/api/game/cashout', methods=['POST'])
def proxy_legacy_game_routes():
    """توجيه استدعاءات الفرونت إند الكلاسيكية تلقائياً إلى blueprint الألعاب"""
    from games.games_api import start_boxes_game, pick_box, end_boxes_game
    path = request.path
    if path.endswith('/start'):
        return start_boxes_game()
    elif path.endswith('/step'):
        return pick_box()
    elif path.endswith('/cashout'):
        return end_boxes_game()
    return jsonify({"success": False, "message": "مسار غير معروف"}), 404

# ==========================================
# المسارات المباشرة والخدمية للمستخدم
# ==========================================

@app.route('/tonconnect-manifest.json')
def serve_tonconnect_manifest():
    """تقديم ملف البيانات الخاص بمحفظة TON Connect"""
    try:
        return send_from_directory('.', 'tonconnect-manifest.json', mimetype='application/json')
    except Exception as e:
        print(f"❌ Manifest Error: {e}")
        return jsonify({"error": "Manifest file not found"}), 404

@app.route('/api/user/info', methods=['GET', 'POST'])
def get_user_info_main():
    """جلب وتأكيد بيانات المستخدم والتحقق المباشر من حالة الحظر"""
    is_post = (request.method == 'POST')
    success, telegram_id, user_info, error_res = get_authenticated_user(request, is_post=is_post)
    if not success:
        return error_res
        
    try:
        if database.is_user_banned(telegram_id):
            return jsonify({
                "success": False, 
                "error": "حسابك معطل حالياً بسبب مخالفة الشروط",
                "banned": True
            }), 403

        user_data = database.get_user(telegram_id)
        if not user_data:
            first_name = user_info.get('first_name', 'لاعب') if isinstance(user_info, dict) else 'لاعب'
            ref_id = user_info.get('start_param') if isinstance(user_info, dict) else None
            
            database.init_user(telegram_id, ref_id=ref_id, first_name=first_name)
            user_data = database.get_user(telegram_id)
            
        return jsonify({"success": True, "user": user_data}), 200
    except Exception as e:
        print(f"❌ Error fetching user info for {telegram_id}: {e}")
        return jsonify({"success": False, "error": "حدث خطأ أثناء جلب بيانات الحساب"}), 500

# ==========================================
# الأمان والتحكم بالهيدرز والملفات الثابتة
# ==========================================

@app.after_request
def add_security_headers(response):
    """منع التخزين المؤقت (Cache) لمسارات الـ API"""
    if request.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response

@app.errorhandler(500)
def handle_500_error(e):
    return jsonify({"status": "error", "success": False, "error": "حدث خطأ داخلي في السيرفر", "message": "خطأ في الاتصال بالخادم."}), 500

@app.errorhandler(404)
def handle_404_error(e):
    if request.path.startswith('/api/'):
        return jsonify({"status": "error", "success": False, "error": "المسار غير موجود", "message": "خطأ في الاتصال بالخادم."}), 404
    return send_from_directory('.', 'index.html')

@app.route('/')
def serve_index():
    return send_from_directory('.', 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    """تقديم الملفات الثابتة وتأمين الملفات البرمجية والحساسة تحديداً"""
    path_lower = path.lower()
    
    if path_lower == 'tonconnect-manifest.json':
        return send_from_directory('.', 'tonconnect-manifest.json', mimetype='application/json')
    
    forbidden_extensions = ('.py', '.env', '.sh', '.git', '.pem', '.key')
    forbidden_files = ('firebase-adminsdk.json', 'config.json', 'requirements.txt')
    
    if any(path_lower.endswith(ext) for ext in forbidden_extensions) or any(f in path_lower for f in forbidden_files):
        return jsonify({"error": "Access Denied"}), 403
        
    try:
        return send_from_directory('.', path)
    except Exception:
        return send_from_directory('.', 'index.html')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
