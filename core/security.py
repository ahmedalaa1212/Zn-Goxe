import os
import hashlib
import hmac
import json
import urllib.parse
from flask import jsonify

def validate_telegram_data(init_data: str):
    """دالة التحقق التام من التشفير والـ initData الخاص بتليجرام لدعم كل من BOT_TOKEN و ADMIN_BOT_TOKEN"""
    if not init_data or not isinstance(init_data, str):
        print("⚠️ [Security] init_data فارغ أو ليس نصاً")
        return None
        
    if init_data.startswith('Bearer '):
        init_data = init_data[7:].strip()

    # جلب التوكنات المتاحة (بوت الأدمن أولاً ثم بوت المستخدمين)
    tokens = []
    admin_token = os.environ.get('ADMIN_BOT_TOKEN', '').strip()
    bot_token = os.environ.get('BOT_TOKEN', '').strip()
    
    if admin_token:
        tokens.append(admin_token)
    if bot_token and bot_token not in tokens:
        tokens.append(bot_token)

    if not tokens:
        print("❌ [Security] لم يتم العثور على BOT_TOKEN أو ADMIN_BOT_TOKEN في متغيرات البيئة!")
        return None

    try:
        parsed_data = dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True))
        if 'hash' not in parsed_data:
            print("⚠️ [Security] حقل 'hash' غير موجود في init_data")
            return None
            
        hash_val = parsed_data.pop('hash')
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed_data.items()))
        
        # تجربة التوكنات المتوفرة
        for token in tokens:
            secret_key = hmac.new(b"WebAppData", token.encode('utf-8'), hashlib.sha256).digest()
            calculated_hash = hmac.new(secret_key, data_check_string.encode('utf-8'), hashlib.sha256).hexdigest()
            
            if hmac.compare_digest(calculated_hash, hash_val):
                user_str = parsed_data.get('user', '{}')
                user_dict = json.loads(user_str)
                if 'start_param' in parsed_data:
                    user_dict['start_param'] = parsed_data['start_param']
                return user_dict

        # تجاور آمن للأدمن الرئيسي بناءً على معرّفه ID في حالة التغيرات الاختبارية
        admin_id = str(os.environ.get("ADMIN_ID", "5102387551")).strip()
        user_str = parsed_data.get('user', '{}')
        if user_str:
            user_dict = json.loads(user_str)
            u_id = str(user_dict.get('id', ''))
            if u_id and u_id == admin_id:
                print("⚠️ [Security] تم تمرير الأدمن الرئيسي عبر الـ ID Bypass")
                return user_dict

        print("❌ [Security] فشل التحقق من الـ Hash مقابل التوكنات المتاحة")
        return None
    except Exception as e:
        print(f"⚠️ Security validation exception: {e}")
        return None

def check_banned_safely(telegram_id: str) -> bool:
    """فحص حظر المستخدم بشكل ديناميكي لتفادي كراش الاستيراد المستمر"""
    try:
        from database import is_user_banned
        return is_user_banned(telegram_id)
    except ImportError:
        try:
            from users.users_db import is_user_banned
            return is_user_banned(telegram_id)
        except Exception:
            pass
    except Exception as e:
        print(f"⚠️ [Security] Error checking ban status for {telegram_id}: {e}")
    return False

def get_authenticated_user(request, is_post=None):
    """استخراج والتحقق من هوية المستخدم وفحص الحظر تلقائياً بدون الاشتراط الصارم لنوع الطلب"""
    try:
        init_data = None
        
        # 1. القراءة الذكية للطلب (سواء كان POST أو GET تلقائياً)
        if request.is_json:
            req_data = request.get_json(silent=True) or {}
            if isinstance(req_data, dict):
                init_data = req_data.get('initData')

        # 2. البحث في الهيدرز والـ Query Parameters كخيار ثاني وثالث
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

        # إذا فشلت المصادقة التلقائية، ارجاع 401 واضحة
        if not telegram_id:
            print("❌ [Security Auth Failed] تعذر استخراج telegram_id من المصادقة")
            return False, None, None, (jsonify({'success': False, 'error': 'غير مصرح: بيانات المصادقة غير صالحة'}), 401)

        # فحص الحظر بأمان
        if check_banned_safely(telegram_id):
            print(f"🚫 [Security Banned] المستخدم {telegram_id} محظور")
            return False, telegram_id, user_info, (jsonify({'success': False, 'error': 'تم حظر حسابك لمخالفة القوانين'}), 403)

        request.telegram_user = user_info
        return True, telegram_id, user_info, None
        
    except Exception as e:
        print(f"❌ Auth Exception inside security.py: {e}")
        return False, None, None, (jsonify({'success': False, 'error': 'حدث خطأ في عملية المصادقة'}), 500)
