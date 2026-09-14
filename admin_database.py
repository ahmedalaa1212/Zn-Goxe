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


# ==================== إعادة توجيه وظائف نظام الإدارة العليا والحظر والتحليلات (Super Admin) ====================
try:
    from super_admin.super_admin_db import (
        ban_user_db,
        unban_user_db,
        get_system_global_analytics,
        add_moderator_db,
        list_moderators_db,
        remove_moderator_db,
        get_admin_logs,
        modify_user_balance_admin,
        reset_user_account_admin,
        get_all_user_ids,
        get_user_by_id,
        log_broadcast_campaign,
        get_latest_broadcast_stats
    )
except ImportError as e:
    print(f"⚠️ Note: super_admin_db module import warning: {e}")

    # 🚫 دالة fallback لحظر مستخدم وحجب جهازه
    def ban_user_db(tg_id, reason="تم الحظر من قبل الإدارة العليا", admin_name="السوبر أدمن"):
        try:
            db = _get_db()
            if not db:
                return False, "قاعدة البيانات غير متوفرة"
            
            tg_id_str = str(tg_id).strip()
            user_ref = db.collection("users").document(tg_id_str)
            user_doc = user_ref.get()
            
            # 1. تحديث حقول الحظر بالتوازي (banned و is_banned)
            user_ref.update({
                "banned": True,
                "is_banned": True,
                "ban_reason": reason
            })

            # 2. البحث عن معرف الجهاز المرتبط بالمستخدم وحفظه في banned_devices
            import time
            device_ids = set()
            
            if user_doc.exists:
                u_data = user_doc.to_dict() or {}
                if u_data.get("device_id"):
                    device_ids.add(str(u_data.get("device_id")).strip())

            # البحث في مجموعة الأجهزة (devices)
            try:
                dev_docs = db.collection("devices").where("primary_user_id", "==", tg_id_str).stream()
                for d in dev_docs:
                    device_ids.add(str(d.id).strip())
            except Exception as d_err:
                print(f"⚠️ Warning searching devices collection: {d_err}")

            # إدراج كل معرّف جهاز في مجموعة banned_devices
            for dev_id in device_ids:
                if dev_id:
                    db.collection("banned_devices").document(dev_id).set({
                        "device_id": dev_id,
                        "banned_user_id": tg_id_str,
                        "reason": reason,
                        "banned_by": admin_name,
                        "timestamp": time.time()
                    }, merge=True)

            return True, f"تم حظر المستخدم {tg_id_str} وحظر الأجهزة المرتبطة به بنجاح"
        except Exception as err:
            return False, f"خطأ في الحظر الاحتياطي: {err}"

    # 🟢 دالة fallback لفك الحظر عن المستخدم وجهازه
    def unban_user_db(tg_id, admin_name="السوبر أدمن"):
        try:
            db = _get_db()
            if not db:
                return False, "قاعدة البيانات غير متوفرة"
            
            tg_id_str = str(tg_id).strip()
            user_ref = db.collection("users").document(tg_id_str)
            user_doc = user_ref.get()

            # 1. إرجاع حقول الحظر إلى False وإلغاء السبب
            user_ref.update({
                "banned": False,
                "is_banned": False,
                "ban_reason": None
            })

            # 2. جلب جميع الأجهزة المرتبطة بهذا المستخدم لمسحها من banned_devices
            device_ids = set()
            if user_doc.exists:
                u_data = user_doc.to_dict() or {}
                if u_data.get("device_id"):
                    device_ids.add(str(u_data.get("device_id")).strip())

            try:
                dev_docs = db.collection("devices").where("primary_user_id", "==", tg_id_str).stream()
                for d in dev_docs:
                    device_ids.add(str(d.id).strip())
            except Exception as d_err:
                print(f"⚠️ Warning searching devices for unban: {d_err}")

            # مسح الأجهزة من قائمة الأجهزة المحظورة
            for dev_id in device_ids:
                if dev_id:
                    db.collection("banned_devices").document(dev_id).delete()

            # مسح أي قيود حظر إضافية مسجلة بـ Telegram ID في banned_devices
            try:
                bd_docs = db.collection("banned_devices").where("banned_user_id", "==", tg_id_str).stream()
                for bd in bd_docs:
                    db.collection("banned_devices").document(bd.id).delete()
            except Exception as bd_err:
                print(f"⚠️ Warning cleaning banned_devices by user id: {bd_err}")

            return True, f"تم فك الحظر عن المستخدم {tg_id_str} وجميع الأجهزة المربوطة به بنجاح"
        except Exception as err:
            return False, f"خطأ في فك الحظر الاحتياطي: {err}"

    # 📊 دالة fallback للتحليلات الكلية
    def get_system_global_analytics():
        try:
            db = _get_db()
            if not db:
                return {"total_users": 0, "active_today": 0, "banned_users": 0, "top_active_users": []}
            users = list(db.collection("users").stream())
            total_users = len(users)
            banned_count = sum(1 for u in users if (u.to_dict() or {}).get("banned") or (u.to_dict() or {}).get("is_banned"))
            return {
                "total_users": total_users,
                "active_today": max(0, total_users - banned_count),
                "banned_users": banned_count,
                "total_circulating_zn": 0.0,
                "top_active_users": []
            }
        except Exception as err:
            print(f"❌ Error getting analytics fallback: {err}")
            return {"total_users": 0, "active_today": 0, "banned_users": 0, "top_active_users": []}

    # 👤 دوال fallback للمشرفين والسجلات
    def add_moderator_db(tg_id, name, permissions=None, admin_name="السوبر أدمن"):
        return False, "غير مدعوم في الوضع الاحتياطي"

    def list_moderators_db():
        return []

    def remove_moderator_db(tg_id, admin_name="السوبر أدمن"):
        return False, "غير مدعوم في الوضع الاحتياطي"

    def get_admin_logs(limit=50):
        return []

    def modify_user_balance_admin(tg_id, amount, balance_type="balance", operation="add", admin_name="السوبر أدمن"):
        return False, "غير مدعوم في الوضع الاحتياطي", 0.0

    def reset_user_account_admin(tg_id, admin_name="السوبر أدمن"):
        return False, "غير مدعوم في الوضع الاحتياطي"

    # 📢 دوال fallback للإشعارات والبث الجماعي
    def get_all_user_ids():
        try:
            db = _get_db()
            if not db:
                return []
            users_ref = db.collection('users').stream()
            user_ids = []
            for doc in users_ref:
                data = doc.to_dict() or {}
                if not (data.get('banned', False) or data.get('is_banned', False)):
                    user_ids.append(str(doc.id))
            return user_ids
        except Exception as err:
            print(f"❌ Error fetching user ids fallback: {err}")
            return []

    def log_broadcast_campaign(admin_name, message, total_targets, success_count, blocked_count):
        try:
            db = _get_db()
            if not db:
                return False
            import time
            doc_ref = db.collection('broadcasts').document()
            doc_ref.set({
                'id': doc_ref.id,
                'admin_name': admin_name,
                'message_snippet': message[:100],
                'total_targets': total_targets,
                'success_count': success_count,
                'blocked_count': blocked_count,
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
                return False, None
            doc = db.collection('users').document(str(user_id)).get()
            return (True, doc.to_dict()) if doc.exists else (False, None)
        except Exception as err:
            print(f"❌ Error fetching user fallback: {err}")
            return False, None

    def get_latest_broadcast_stats():
        try:
            db = _get_db()
            if not db:
                return None
            docs = db.collection('broadcasts').order_by('created_at', direction='DESCENDING').limit(1).get()
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
