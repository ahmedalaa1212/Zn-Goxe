from datetime import datetime, timezone
from firebase_admin import firestore
import database

def create_support_ticket(tg_id, subject, message):
    """إنشاء تذكرة دعم جديدة من قبل المستخدم"""
    try:
        if not tg_id or not message:
            return False, "يرجى كتابة نص الرسالة"

        db = database.get_db()
        ticket_doc = {
            "user_id": str(tg_id),
            "subject": subject or "استفسار عام",
            "message": message,
            "status": "open",
            "replies": [],
            "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            "timestamp": firestore.SERVER_TIMESTAMP
        }
        res = db.collection("support_tickets").add(ticket_doc)
        return True, f"تم إرسال تذكرة الدعم بنجاح! رقم التذكرة: {res[1].id}"
    except Exception as e:
        print(f"❌ Error creating support ticket: {e}")
        return False, f"حدث خطأ أثناء الإرسال: {e}"


def get_user_support_tickets(tg_id):
    """جلب قائمة تذاكر الدعم الخاصة بالمستخدم"""
    try:
        db = database.get_db()
        docs = db.collection("support_tickets").where("user_id", "==", str(tg_id)).stream()
        tickets = []
        for doc in docs:
            d = doc.to_dict() or {}
            d["id"] = doc.id
            tickets.append(d)
        return tickets
    except Exception as e:
        print(f"❌ Error getting user support tickets: {e}")
        return []


def get_all_support_tickets_admin(status_filter="open", limit=50):
    """جلب جميع التذاكر للوحة الإدارة"""
    try:
        db = database.get_db()
        ref = db.collection("support_tickets")
        if status_filter != "all":
            ref = ref.where("status", "==", status_filter)

        docs = ref.limit(limit).stream()
        tickets = []
        for doc in docs:
            d = doc.to_dict() or {}
            d["id"] = doc.id
            tickets.append(d)
        return tickets
    except Exception as e:
        print(f"❌ Error getting all support tickets: {e}")
        return []


def reply_to_support_ticket(ticket_id, reply_text, admin_name="فريق الدعم"):
    """الرد على تذكرة دعم وتحديث حالتها"""
    try:
        if not ticket_id or not reply_text:
            return False, "نص الرد غير صالح"

        db = database.get_db()
        ticket_ref = db.collection("support_tickets").document(str(ticket_id))
        ticket_doc = ticket_ref.get()

        if not ticket_doc.exists:
            return False, "التذكرة غير موجودة"

        reply_entry = {
            "sender": admin_name,
            "message": reply_text,
            "time": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        }

        ticket_ref.update({
            "status": "answered",
            "replies": firestore.ArrayUnion([reply_entry])
        })

        database.log_admin_action(admin_name, f"الرد على تذكرة الدعم {ticket_id}")
        return True, "تم إرسال الرد بنجاح!"
    except Exception as e:
        print(f"❌ Error replying to support ticket: {e}")
        return False, f"حدث خطأ: {e}"
