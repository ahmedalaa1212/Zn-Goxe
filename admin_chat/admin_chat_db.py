# admin_chat/admin_chat_db.py
from google.cloud import firestore
import database

def get_db():
    """ضمان الحصول على كائن قاعدة البيانات Firestore"""
    if database.db is None:
        return database.initialize_firebase()
    return database.db

def get_all_tickets_from_db():
    """جلب جميع تذاكر الدعم الفني مرتبة حسب أحدث تاريخ تحديث"""
    db_conn = get_db()
    if not db_conn:
        return []
    
    tickets_ref = db_conn.collection('support_tickets').stream()
    tickets = []
    for doc in tickets_ref:
        t = doc.to_dict() or {}
        if 'ticket_id' not in t:
            t['ticket_id'] = doc.id
        tickets.append(t)
        
    tickets.sort(key=lambda x: str(x.get('updated_at', '')), reverse=True)
    return tickets

def get_ticket_by_id_from_db(ticket_id):
    """جلب تذكرة واحدة فقط برقم التذكرة لتوفير قراءات Firestore"""
    db_conn = get_db()
    if not db_conn:
        return None
        
    t_doc = db_conn.collection('support_tickets').document(str(ticket_id)).get()
    if not t_doc.exists:
        return None

    ticket_data = t_doc.to_dict() or {}
    if 'ticket_id' not in ticket_data:
        ticket_data['ticket_id'] = t_doc.id

    return ticket_data

def mark_ticket_read_in_db(ticket_id):
    """تحديث حالة التذكرة إلى مقروءة بواسطة الأدمن"""
    db_conn = get_db()
    if not db_conn:
        return False
        
    t_ref = db_conn.collection('support_tickets').document(str(ticket_id))
    if t_ref.get().exists:
        t_ref.update({'has_unread_admin': False})
        return True
    return False

def add_admin_reply_to_db(ticket_id, text, now_str):
    """إضافة رد الأدمن وتحديث بيانات التذكرة، وإرجاع user_id لإرسال الإشعار"""
    db_conn = get_db()
    if not db_conn:
        return False, None, "مشكلة في الاتصال بقاعدة البيانات"

    t_ref = db_conn.collection('support_tickets').document(str(ticket_id))
    t_doc = t_ref.get()
    if not t_doc.exists:
        return False, None, "التذكرة غير موجودة"

    ticket_data = t_doc.to_dict() or {}
    user_id = ticket_data.get('user_id') or ticket_data.get('user_info', {}).get('id')

    new_msg = {
        'sender': 'admin',
        'text': str(text).strip(),
        'timestamp': now_str
    }

    t_ref.update({
        'messages': firestore.ArrayUnion([new_msg]),
        'updated_at': now_str,
        'has_unread_admin': False,
        'last_sender': 'admin'
    })

    return True, user_id, None

def close_ticket_in_db(ticket_id, now_str):
    """إغلاق التذكرة وتحديث حالتها إلى closed"""
    db_conn = get_db()
    if not db_conn:
        return False

    t_ref = db_conn.collection('support_tickets').document(str(ticket_id))
    t_ref.update({
        'status': 'closed',
        'has_unread_admin': False,
        'updated_at': now_str
    })
    return True
