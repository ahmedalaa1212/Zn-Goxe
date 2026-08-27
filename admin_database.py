"""
ملف admin_database.py
يعمل كوسيط (Facade Router) يربط بين ملفات قاعدة البيانات الفرعية للموديولات
(مثل addons_db، admin_chat_db، إلخ) وقاعدة البيانات الرئيسية لتنظيم الكود ومنع كثرة الأسطر.
"""

from database import get_db

def _get_db():
    """جلب كائن قاعدة البيانات من الملف الرئيسي"""
    return get_db()


# ==================== إعادة توجيه وظائف قسم الإضافات (Addons / Promo Codes) ====================
from addons.addons_db import (
    create_promo_code,
    redeem_promo_code,
    get_all_promo_codes,
    delete_promo_code,
    toggle_promo_code_status
)


# ==================== مستقبلاً: استيراد باقي القوائم تلقائياً ====================
# يمكنك إضافة استيراد ملفات الداتا بيز للقوائم الأخرى بنفس الطريقة هنا:
# from admin_chat.admin_chat_db import *
# from super_admin.super_admin_db import *
