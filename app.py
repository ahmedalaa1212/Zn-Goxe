import os
from flask import Flask, jsonify
from flask_cors import CORS

app = Flask(__name__)
# السماح للواجهة بالاتصال بالسيرفر
CORS(app)

# منع حفظ الكاش عشان البيانات تتحدث فوراً
@app.after_request
def add_header(response):
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, public, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

# ----------------------------------------------------
# 🌐 هنا هنربط القوائم (الوزراء) بعدين باستخدام Blueprints
# مثال: app.register_blueprint(wallet_api)
# ----------------------------------------------------

# مسار اختبار للتأكد إن السيرفر شغال على Railway
@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({"success": True, "message": "المايسترو جاهز والسيرفر يعمل بكفاءة 🚀"}), 200

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
