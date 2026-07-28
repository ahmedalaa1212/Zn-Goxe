import os
import hashlib
import hmac
import json
import urllib.parse
from flask import jsonify

BOT_TOKEN = os.environ.get('BOT_TOKEN', '').strip()

def validate_telegram_data(init_data: str):
    """دالة التحقق من التشفير والـ initData الخاص بتليجرام"""
    token = os.environ.get('BOT_TOKEN', '').strip() or BOT_TOKEN
    if not init_data or not token:
        print("⚠️ Security Warning: init_data or BOT_TOKEN is missing!")
        return None
        
    try:
        parsed_data = dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True))
        
        if 'hash' not in parsed_data:
            return None
        hash_val = parsed_data.pop('hash')
        
        # ترتيب العناصر أبجدياً طبقاً لتعليمات تليجرام
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed_data.items()))
        
        # إنشاء التوقيع السري ومقارنته آمنياً
        secret_key = hmac.new(b"WebAppData", token.encode('utf-8'), hashlib.sha256).digest()
        calculated_hash = hmac.new(secret_key, data_check_string.encode('utf-8'), hashlib.sha256).hexdigest()
        
        # استخدام compare_digest للوقاية من هجمات Timing Attacks
        if hmac.compare_digest(calculated_hash, hash_val):
            user_str = parsed_data.get('user', '{}')
            return json.loads(user_str)
        return None
        
    except Exception as e:
        print(f"Security validation exception: {e}")
        return None

def get_authenticated_user(request, is_post=False):
    """استخراج وتأكيد صحة المستخدم من الطلب"""
    try:
        init_data = None
        if is_post:
            req_data = request.get_json(silent=True) or {}
            init_data = req_data.get('initData')
        
        if not init_data:
            init_data = request.args.get('initData') or request.headers.get('X-Telegram-Init-Data')
        
        if not init_data:
            return False, None, (jsonify({'success': False, 'error': 'بيانات المصادقة مفقودة (initData)'}), 401)
            
        user = validate_telegram_data(init_data)
        if not user:
            return False, None, (jsonify({'success': False, 'error': 'محاولة وصول غير مصرح بها أو توكن مفعل خاطئ'}), 403)
            
        telegram_id = str(user.get('id')).strip()
        return True, telegram_id, None
        
    except Exception as e:
        return False, None, (jsonify({'success': False, 'error': 'حدث خطأ في عملية المصادقة'}), 500)
