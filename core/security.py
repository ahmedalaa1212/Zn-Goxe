import os
import hashlib
import hmac
import json
import urllib.parse
from flask import jsonify
from database import is_user_banned

def validate_telegram_data(init_data: str):
    """دالة التحقق من التشفير والـ initData الخاص بتليجرام"""
    token = os.environ.get('BOT_TOKEN', '').strip()
    if not init_data or not token:
        print("⚠️ Security Warning: init_data or BOT_TOKEN is missing!")
        return None
        
    try:
        parsed_data = dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True))
        
        if 'hash' not in parsed_data:
            return None
        hash_val = parsed_data.pop('hash')
        
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed_data.items()))
        
        secret_key = hmac.new(b"WebAppData", token.encode('utf-8'), hashlib.sha256).digest()
        calculated_hash = hmac.new(secret_key, data_check_string.encode('utf-8'), hashlib.sha256).hexdigest()
        
        if hmac.compare_digest(calculated_hash, hash_val):
            user_str = parsed_data.get('user', '{}')
            return json.loads(user_str)
        return None
        
    except Exception as e:
        print(f"Security validation exception: {e}")
        return None

def get_authenticated_user(request, is_post=False):
    """استخرج واستأذن المستخدم وتأكد فوراً أنه غير محظور"""
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
            return False, None, (jsonify({'success': False, 'error': 'محاولة وصول غير مصرح بها'}), 403)
            
        telegram_id = str(user.get('id')).strip()

        # ✅ حماية قصوى: فحص الحظر قبل السماح بأي عملية في السيرفر
        if is_user_banned(telegram_id):
            return False, None, (jsonify({'success': False, 'error': 'تم حظر حسابك لمخالفة القوانين'}), 403)

        return True, telegram_id, None
        
    except Exception as e:
        return False, None, (jsonify({'success': False, 'error': 'حدث خطأ في عملية المصادقة'}), 500)
