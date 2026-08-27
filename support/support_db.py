# support/support_db.py
from datetime import datetime, timezone
import logging
import database

try:
    from google.cloud.firestore import ArrayUnion
except ImportError:
    ArrayUnion = None

logger = logging.getLogger(__name__)

def get_db():
    """الحصول على كائن الاتصال بقاعدة البيانات Firestore"""
    if database.db is None:
        return database.initialize_firebase()
    return database.db

def get_or_create_active_ticket(uid: str, custom_ticket_id: str = None, user_info: dict = None) -> dict:
    """جلب التذكرة النشطة للمستخدم أو إنشاء تذكرة جديدة باستهلاك أدنى لقراءات Firestore"""
    db = get_db()
    if not db:
        return None

    uid_str = str(uid).strip()
    tickets_ref = db.collection('support_tickets')

    if custom_ticket_id:
        doc = tickets_ref.document(str(custom_ticket_id).strip()).get()
        if doc.exists:
            data = doc.to_dict() or {}
            ticket_owner = str(data.get('uid') or data.get('user_id') or '')
            if ticket_owner == uid_str:
                return data

    query = tickets_ref.where('uid', '==', uid_str).where('status', '==', 'open').limit(1).stream()
    for doc in query:
        return doc.to_dict()

    query_alt = tickets_ref.where('user_id', '==', uid_str).where('status', '==', 'open').limit(1).stream()
    for doc in query_alt:
        return doc.to_dict()

    now_iso = datetime.now(timezone.utc).isoformat()
    ticket_id = custom_ticket_id or f"TK-{uid_str[-4:]}-{int(datetime.now().timestamp()) % 100000}"
    
    welcome_message = {
        "sender": "admin",
        "text": f"مرحباً بك في مركز الدعم الفني! 🎧\nكودك المرجعي للمحادثة: {ticket_id}\n\nيرجى التكرم بالالتزام بآداب الحوار والتعامل اللائق مع فريق الدعم. تفضل بكتابة استفسارك وسيقوم الفريق بالرد عليك في أقرب وقت.",
        "timestamp": now_iso
    }

    new_ticket_data = {
        "ticket_id": ticket_id,
        "uid": uid_str,
        "user_id": uid_str,
        "user_info": user_info or {},
        "status": "open",
        "has_unread_admin": True,
        "last_sender": "system",
        "created_at": now_iso,
        "updated_at": now_iso,
        "messages": [welcome_message]
    }

    tickets_ref.document(ticket_id).set(new_ticket_data)
    return new_ticket_data

def add_support_message(uid: str, ticket_id: str, text: str, sender: str = "user", user_info: dict = None) -> dict:
    """إضافة رسالة جديدة بشكل مباشر ومسارع بدون قراءة مسبقة لتقليل زمن الاستجابة"""
    db = get_db()
    if not db:
        return {"success": False, "message": "خطأ في الاتصال بقاعدة البيانات"}

    uid_str = str(uid).strip()
    clean_text = text.strip()[:2000]

    if not clean_text:
        return {"success": False, "message": "لا يمكن إرسال رسالة فارغة"}

    ticket_ref = db.collection('support_tickets').document(ticket_id)
    now_iso = datetime.now(timezone.utc).isoformat()

    new_msg = {
        "sender": sender,
        "text": clean_text,
        "timestamp": now_iso
    }

    update_payload = {
        "updated_at": now_iso,
        "has_unread_admin": True if sender == "user" else False,
        "last_sender": sender
    }
    
    if user_info:
        update_payload["user_info"] = user_info

    if ArrayUnion:
        update_payload["messages"] = ArrayUnion([new_msg])
        try:
            ticket_ref.update(update_payload)
            return {
                "success": True,
                "ticket_id": ticket_id,
                "status": "open",
                "message_data": new_msg
            }
        except Exception:
            pass

    # في حالة عدم وجود ArrayUnion أو فشل التحديث السريع
    ticket_doc = ticket_ref.get()
    if not ticket_doc.exists:
        ticket_data = get_or_create_active_ticket(uid_str, custom_ticket_id=ticket_id, user_info=user_info)
        if not ticket_data:
            return {"success": False, "message": "تعذر العثور على التذكرة"}
    else:
        ticket_data = ticket_doc.to_dict() or {}

    ticket_owner = str(ticket_data.get('uid') or ticket_data.get('user_id') or '')
    if ticket_owner != uid_str:
        return {"success": False, "message": "غير مصرح لك بالوصول لهذه التذكرة"}

    if ticket_data.get('status') == 'closed':
        return {"success": False, "message": "تم إنهاء هذه المحادثة بالكامل."}

    messages = ticket_data.get('messages', [])
    messages.append(new_msg)
    update_payload["messages"] = messages
    ticket_ref.update(update_payload)

    return {
        "success": True,
        "ticket_id": ticket_id,
        "status": ticket_data.get('status', 'open'),
        "messages": messages
    }

def create_new_user_ticket(uid: str, user_info: dict = None) -> dict:
    """إغلاق أي تذكرة مفتوحة قديمة وإنشاء تذكرة دعم جديدة فوراً بشكل أسرع"""
    db = get_db()
    if not db:
        return None

    uid_str = str(uid).strip()
    tickets_ref = db.collection('support_tickets')

    open_tickets = tickets_ref.where('uid', '==', uid_str).where('status', '==', 'open').stream()
    for doc in open_tickets:
        tickets_ref.document(doc.id).update({"status": "closed"})

    ticket_id = f"TK-{uid_str[-4:]}-{int(datetime.now().timestamp()) % 100000}"
    now_iso = datetime.now(timezone.utc).isoformat()

    welcome_message = {
        "sender": "admin",
        "text": f"مرحباً بك في تذكرة الدعم الفني الجديدة! 🎧\nالكود المرجعي: {ticket_id}\n\nتفضل بكتابة استفسارك وسيقوم الفريق بالمتابعة والرد عليك.",
        "timestamp": now_iso
    }

    new_ticket_data = {
        "ticket_id": ticket_id,
        "uid": uid_str,
        "user_id": uid_str,
        "user_info": user_info or {},
        "status": "open",
        "has_unread_admin": True,
        "last_sender": "system",
        "created_at": now_iso,
        "updated_at": now_iso,
        "messages": [welcome_message]
    }

    tickets_ref.document(ticket_id).set(new_ticket_data)
    return new_ticket_data
