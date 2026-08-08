from datetime import datetime, timezone
from firebase_admin import firestore
import database

def send_direct_notification(recipient_tg_id, title, message_text, sender_name="الإدارة"):
    """إرسال إشعار / رسالة خاصة مباشرة لمستخدم محدد"""
    try:
        if not recipient_tg_id or not message_text:
            return False, "بيانات الرسالة غير كاملة"

        db = database.get_db()
        notif_data = {
            "user_id": str(recipient_tg_id),
            "title": title or "تنبيه إداري",
            "message": message_text,
            "sender": sender_name,
            "is_read": False,
            "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            "timestamp": firestore.SERVER_TIMESTAMP
        }
        db.collection("user_notifications").add(notif_data)
        return True, f"تم إرسال الإشعار للمستخدم {recipient_tg_id} بنجاح!"
    except Exception as e:
        print(f"❌ Error sending direct notification: {e}")
        return False, f"حدث خطأ أثناء الإرسال: {e}"


def get_user_notifications(tg_id, limit=20):
    """جلب قائمة إشعارات المستخدم"""
    try:
        db = database.get_db()
        docs = (
            db.collection("user_notifications")
            .where("user_id", "==", str(tg_id))
            .limit(limit)
            .stream()
        )
        notifs = []
        for doc in docs:
            d = doc.to_dict() or {}
            d["id"] = doc.id
            notifs.append(d)
        return notifs
    except Exception as e:
        print(f"❌ Error getting user notifications: {e}")
        return []


def mark_notification_as_read(notification_id):
    """تحديد الإشعار كمقروء"""
    try:
        db = database.get_db()
        db.collection("user_notifications").document(str(notification_id)).update({"is_read": True})
        return True
    except Exception as e:
        print(f"❌ Error marking notification as read: {e}")
        return False


def create_global_broadcast(title, message_text, admin_name="المدير العام"):
    """إنشاء بث جماعي لجميع مستخدمي البوت"""
    try:
        if not message_text:
            return False, "يرجى إدخال نص الإذاعة العامة"

        db = database.get_db()
        broadcast_doc = {
            "title": title or "إعلان عام",
            "message": message_text,
            "created_by": admin_name,
            "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            "timestamp": firestore.SERVER_TIMESTAMP
        }
        res = db.collection("global_broadcasts").add(broadcast_doc)
        database.log_admin_action(admin_name, f"إرسال إعلان عام جديد: {title}")

        return True, f"تم إنشاء الإذاعة الجماعية بنجاح (رقم المعاملة: {res[1].id})"
    except Exception as e:
        print(f"❌ Error creating global broadcast: {e}")
        return False, f"حدث خطأ: {e}"
