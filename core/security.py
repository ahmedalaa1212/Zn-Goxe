# core/security.py
import os
import hashlib
import hmac
import json
import urllib.parse
from flask import jsonify

# توكن البوت بنجيبه من إعدادات السيرفر المخفية (Environment Variables)
BOT_TOKEN = os.environ.get('BOT_TOKEN', '').strip()

def validate_telegram_data(init_data: str):
    """
    دالة للتحقق من أن الطلب قادم فعلاً من تليجرام وليس من هاكر.
    تقوم بفك التشفير ومطابقته مع توكن البوت.
    """
    if not init_data or not BOT_TOKEN:
        return None
        
    try:
        # تحويل النص إلى قاموس بيانات
        parsed_data = dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True))
        
        # استخراج الختم (hash) للمقارنة لاحقاً
        if 'hash' not in parsed_data:
            return None
        hash_val = parsed_data.pop('hash')
        
        # ترتيب البيانات أبجدياً وتجهيزها للتشفير
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed_data.items()))
        
        # إنشاء المفتاح السري باستخدام التوكن
        secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        
        # تشفير البيانات ومقارنتها بالختم المرسل
        calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        
        if calculated_hash == hash_val:
            # إذا كان سليماً، نرجع بيانات المستخدم كـ Dictionary
            return json.loads(parsed_data.get('user', '{}'))
        return None
        
    except Exception:
        return None

def get_authenticated_user(request, is_post=False):
    """
    دالة مساعدة جاهزة للاستخدام في أي (Blueprint).
    تقوم باستخراج الـ initData من الطلب (GET أو POST) والتحقق منه.
    ترجع 3 قيم: (حالة النجاح، آي دي المستخدم، رسالة الخطأ إن وجدت).
    """
    try:
        if is_post:
            req_data = request.get_json(silent=True) or {}
            init_data = req_data.get('initData')
        else:
            init_data = request.args.get('initData')
        
        if not init_data:
            return False, None, (jsonify({'success': False, 'error': 'بيانات المصادقة مفقودة (initData)'}), 401)
            
        user = validate_telegram_data(init_data)
        if not user:
            return False, None, (jsonify({'success': False, 'error': 'محاولة وصول غير مصرح بها أو تلاعب بالبيانات'}), 403)
            
        telegram_id = str(user.get('id')).strip()
        return True, telegram_id, None
        
    except Exception:
        return False, None, (jsonify({'success': False, 'error': 'حدث خطأ في عملية المصادقة'}), 500)
