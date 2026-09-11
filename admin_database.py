"""
ملف admin_database.py
يعمل كوسيط (Facade Router) يربط بين ملفات قاعدة البيانات الفرعية للموديولات
(مثل addons_db، admin_chat_db، super_admin_db إلخ) وقاعدة البيانات الرئيسية لتنظيم الكود ومنع كثرة الأسطر.
"""

from database import get_db

def _get_db():
    """جلب كائن قاعدة البيانات من الملف الرئيسي"""
    return get_db()


# ==================== إعادة توجيه وظائف قسم الإضافات (Addons / Promo Codes) ====================
try:
    from addons.addons_db import (
        create_promo_code,
        redeem_promo_code,
        get_all_promo_codes,
        delete_promo_code,
        toggle_promo_code_status
    )
except ImportError as e:
    print(f"⚠️ Error importing addons_db in admin_database: {e}")


# ==================== إعادة توجيه وظائف نظام الإشعارات والأدمن الرئيسي (Super Admin) ====================
try:
    from super_admin.super_admin_db import (
        get_all_user_ids,
        log_broadcast_campaign,
        get_user_by_id,
        get_latest_broadcast_campaign
    )
except ImportError as e:
    print(f"⚠️ Note: super_admin_db module import warning: {e}")
    
    # دوال احتياطية آمنة لضمان استقرار النظام في حال عدم التصدير المباشر
    def get_all_user_ids():
        try:
            db = _get_db()
            if not db:
                return []
            users_ref = db.collection('users').stream()
            user_ids = []
            for doc in users_ref:
                data = doc.to_dict() or {}
                if not data.get('is_banned', False):
                    user_ids.append(str(doc.id))
            return user_ids
        except Exception as err:
            print(f"❌ Error fetching user ids fallback: {err}")
            return []

    def log_broadcast_campaign(admin_name, message, total_targets, success_count, blocked_count, failed_count):
        try:
            db = _get_db()
            if not db:
                return False
            import time
            doc_ref = db.collection('broadcast_campaigns').document()
            doc_ref.set({
                'id': doc_ref.id,
                'admin_name': admin_name,
                'message': message,
                'total_targets': total_targets,
                'success_count': success_count,
                'blocked_count': blocked_count,
                'failed_count': failed_count,
                'created_at': time.time()
            })
            return True
        except Exception as err:
            print(f"❌ Error logging campaign fallback: {err}")
            return False

    def get_user_by_id(user_id):
        try:
            db = _get_db()
            if not db:
                return None
            doc = db.collection('users').document(str(user_id)).get()
            return doc.to_dict() if doc.exists else None
        except Exception as err:
            print(f"❌ Error fetching user fallback: {err}")
            return None

    def get_latest_broadcast_campaign():
        try:
            db = _get_db()
            if not db:
                return None
            docs = db.collection('broadcast_campaigns').order_by('created_at', direction='DESCENDING').limit(1).get()
            for doc in docs:
                return doc.to_dict()
            return None
        except Exception as err:
            print(f"❌ Error getting latest campaign fallback: {err}")
            return None


# ==================== إعادة توجيه وظائف محادثات الدعم والإدارة (Admin Chat) ====================
try:
    from admin_chat.admin_chat_db import *
except ImportError:
    pass
