# core/security.py
import os
import hashlib
import hmac
import json
import urllib.parse
from flask import jsonify

# توكن البوت بنجيبه من إعدادات السيرفر المخفية
BOT_TOKEN = os.environ.get('BOT_TOKEN', '').strip()

def validate_telegram_data(init_data: str):
    """
    دالة للتحقق من أن الطلب قادم فعلاً من تليجرام وليس من هاكر
    """
    if not init_data or not BOT_TOKEN:
        return None
    try:
        parsed_data = dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True))
        if 'hash' not in parsed_data:
            return None
            
        hash_val = parsed_data.pop('hash')
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed_data.items()))
        
        secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        
        if calculated_hash == hash_val:
            return json.loads(parsed_data.get('user', '{}'))
        return None
    except Exception:
        return None

def get_authenticated_user(request, is_post=False):
    """
    دالة جاهزة للاستخدام في أي قائمة للتأكد من هوية المستخدم
    """
    try:
        if is_post:
            req_data = request.get_json(silent=True) or {}
            init_data = req_data.get('initData')
        else:
            init_data = request.args.get('initData')
        
        if not init_data:
            return False, None, (jsonify({'success': False, 'error': 'بيانات المصادقة مفقودة'}), 401)
            
        user = validate_telegram_data(init_data)
        if not user:
            return False, None, (jsonify({'success': False, 'error': 'محاولة وصول غير مصرح بها'}), 401)
            
        telegram_id = str(user.get('id')).strip()
        return True, telegram_id, None
    except Exception:
        return False, None, (jsonify({'success': False, 'error': 'خطأ في المصادقة'}), 401)
