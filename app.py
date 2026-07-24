# app.py
import os
from flask import Flask, jsonify, send_from_directory, request
from flask_cors import CORS
from farm.farm_api import farm_bp

app = Flask(__name__)
# السماح للواجهة بالاتصال بالسيرفر (ضروري لتليجرام WebApp)
CORS(app)

# تسجيل مسار المزرعة
app.register_blueprint(farm_bp, url_prefix='/api/farm')

@app.after_request
def add_security_headers(response):
    # منع الكاش لضمان تحديث البيانات فوراً
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
    forbidden_dirs = ('core/', 'farm/', 'api/')
    
    if path.endswith(forbidden_extensions) or path.startswith(forbidden_dirs) or path == 'requirements.txt':
        return jsonify({"error": "Access Denied"}), 403
    
    return send_from_directory('.', path)

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({"success": True, "status": "active"}), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
