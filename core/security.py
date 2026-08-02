import os
import hashlib
import hmac
import json
import urllib.parse
from flask import jsonify
from database import is_user_banned

def validate_telegram_data(init_data: str):
    """دالة التحقق التام من التشفير والـ initData الخاص بتليجرام"""
    token = os.environ.get('BOT_TOKEN', '').strip()
    if not init_data or not isinstance(init_data, str) or not token:
        return None
        
    if init_data.startswith('Bearer '):
        init_data = init_data[7:].strip()

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
            user_dict = json.loads(user_str)
            if 'start_param' in parsed_data:
                user_dict['start_param'] = parsed_data['start_param']
            return user_dict
        return None
    except Exception as e:
        print(f"⚠️ Security validation error: {e}")
        return None

def get_authenticated_user(request, is_post=False):
    """استخراج والتحقق من هوية المستخدم وفحص الحظر مباشرة"""
    try:
        init_data = None
        if is_post:
            req_data = request.get_json(silent=True)
            if isinstance(req_data, dict):
                init_data = req_data.get('initData')
            
        if not init_data:
            init_data = (
                request.headers.get('X-Telegram-Init-Data') or 
                request.headers.get('Authorization') or 
                request.args.get('initData')
            )
            
        telegram_id = None
        user_info = None

        if init_data:
            user_info = validate_telegram_data(init_data)
            if user_info and isinstance(user_info, dict) and user_info.get('id'):
                telegram_id = str(user_info.get('id')).strip()

        if not telegram_id:
            return False, None, None, (jsonify({'success': False, 'error': 'غير مصرح: بيانات المصادقة غير صالحة'}), 401)

        if is_user_banned(telegram_id):
            return False, telegram_id, user_info, (jsonify({'success': False, 'error': 'تم حظر حسابك لمخالفة القوانين'}), 403)

        request.telegram_user = user_info
        return True, telegram_id, user_info, None
        
    except Exception as e:
        print(f"❌ Auth Exception: {e}")
        return False, None, None, (jsonify({'success': False, 'error': 'حدث خطأ في عملية المصادقة'}), 500)
