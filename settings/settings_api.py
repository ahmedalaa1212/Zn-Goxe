from flask import Blueprint, jsonify, request

# تعريف الـ Blueprint اللي ملف app.py بيدور عليه
settings_bp = Blueprint('settings', __name__)

# مسار (Endpoint) تجريبي عشان السيرفر ما يديش خطأ
@settings_bp.route('/', methods=['GET'])
def get_settings():
    return jsonify({
        "success": True, 
        "message": "ملف الإعدادات يعمل بنجاح!"
    }), 200

# لو عندك دوال تانية خاصة بالإعدادات تقدر تضيفها هنا بعدين

