import os
from flask import Flask, jsonify, send_from_directory
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

# ==========================================
# 🌐 1. عرض الواجهة للمستخدمين (Frontend)
# ==========================================

# ده المسار الرئيسي اللي هيفتح ملف index.html أول ما البوت يشتغل
@app.route('/')
def serve_index():
    return send_from_directory('.', 'index.html')

# ده مسار ذكي بيقرأ أي ملف (css, js, html) جوه الفولدرات بتاعتك
@app.route('/<path:path>')
def serve_static(path):
    # 🛡️ حماية: نمنع أي حد يوصل لملفات البايثون أو الإعدادات السرية
    if path.endswith('.py') or path.endswith('.env') or path.startswith('core/') or path == 'requirements.txt':
        return jsonify({"error": "غير مصرح لك بالوصول"}), 403
    
    # لو الملف عادي (زي الصور، الجافاسكريبت، التصميم)، السيرفر هيعرضه
    return send_from_directory('.', path)


# ==========================================
# ⚙️ 2. مسارات العمليات (Backend APIs)
# ==========================================

# مسار اختبار للتأكد إن السيرفر شغال
@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({"success": True, "message": "المايسترو جاهز والسيرفر يعمل بكفاءة 🚀"}), 200

# ----------------------------------------------------
# هنا هنربط القوائم (الوزراء) بعدين باستخدام Blueprints
# ----------------------------------------------------

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
