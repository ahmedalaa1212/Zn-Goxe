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
    if not init_data or not token:
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
        print(f"⚠️ Security validation exception: {e}")
        return None

def get_authenticated_user(request, is_post=False):
    """استخراج والتحقق من هويّة المستخدم وفحص الحظر مباشرة"""
    try:
        req_data = {}
        if is_post:
            req_data = request.get_json(silent=True) or {}
            init_data = req_data.get('initData')
        else:
            init_data = request.args.get('initData')
            
        if not init_data:
            init_data = request.headers.get('X-Telegram-Init-Data') or request.args.get('initData')
            
        telegram_id = None

        # 1. المصادقة عبر initData
        if init_data:
            user = validate_telegram_data(init_data)
            if user:
                telegram_id = str(user.get('id')).strip()

        # 2. المصادقة الاحتياطية (Fallback) عبر X-TG-ID أو الـ Body/Query
        if not telegram_id:
            telegram_id = (
                request.headers.get('X-TG-ID') or 
                req_data.get('tg_id') or 
                request.args.get('tg_id')
            )
            if telegram_id:
                telegram_id = str(telegram_id).strip()

        # إذا تعذر التعرف على المستخدم نهائياً
        if not telegram_id:
            return False, None, (jsonify({'success': False, 'error': 'بيانات المصادقة مفقودة (initData)'}), 401)

        # ✅ حماية قصوى: فحص الحظر قبل السماح بأي عملية في السيرفر
        if is_user_banned(telegram_id):
            return False, None, (jsonify({'success': False, 'error': 'تم حظر حسابك لمخالفة القوانين'}), 403)

        return True, telegram_id, None
        
    except Exception as e:
        print(f"❌ Auth Exception: {e}")
        return False, None, (jsonify({'success': False, 'error': 'حدث خطأ في عملية المصادقة'}), 500)
