# -*- coding: utf-8 -*-
# support/support_db.py
import json
import logging
from datetime import datetime, timezone
from psycopg2.extras import RealDictCursor, Json
import database
from database import get_db_connection, format_iso

logger = logging.getLogger(__name__)


def get_db():
    """ضمان الحصول على اتصال قاعدة البيانات Supabase"""
    return database.get_db()


def _normalize_ticket_row(row):
    """توحيد وتنسيق بيانات التذكرة المستخرجة من PostgreSQL لتعمل بسلاسة مع الواجهة"""
    if not row:
        return None
    d = dict(row)
    for k in ('created_at', 'updated_at'):
        if isinstance(d.get(k), datetime):
            d[k] = format_iso(d[k])
    if isinstance(d.get('user_info'), str):
        try:
            d['user_info'] = json.loads(d['user_info'])
        except Exception:
            d['user_info'] = {}
    elif not isinstance(d.get('user_info'), dict):
        d['user_info'] = {}

    if isinstance(d.get('messages'), str):
        try:
            d['messages'] = json.loads(d['messages'])
        except Exception:
            d['messages'] = []
    elif not isinstance(d.get('messages'), list):
        d['messages'] = []

    d['has_unread_admin'] = bool(d.get('has_unread_admin', False))
    return d


def _enrich_user_info(uid_str: str, user_info: dict = None) -> dict:
    """ضمان وجود اسم ويوزر المستخدم في التذكرة ليظهر للأدمن بوضوح"""
    info = dict(user_info) if isinstance(user_info, dict) else {}
    if not info.get('first_name') or not info.get('username'):
        try:
            u_data = database.get_user(uid_str)
            if u_data:
                info.setdefault('id', uid_str)
                info['first_name'] = info.get('first_name') or u_data.get('first_name') or u_data.get('name') or 'مستخدم'
                info['username'] = info.get('username') or u_data.get('username') or ''
        except Exception:
            pass
    info.setdefault('id', uid_str)
    info.setdefault('first_name', 'مستخدم')
    info.setdefault('username', '')
    return info


def get_or_create_active_ticket(uid: str, custom_ticket_id: str = None, user_info: dict = None) -> dict:
    """جلب التذكرة النشطة للمستخدم أو إنشاء تذكرة جديدة لحظياً في Supabase"""
    uid_str = str(uid).strip()
    if not uid_str:
        return None

    clean_info = _enrich_user_info(uid_str, user_info)

    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # 1. إذا تم تمرير رقم تذكرة محدد، نفحصه أولاً
                if custom_ticket_id:
                    clean_tid = str(custom_ticket_id).strip()
                    cur.execute("""
                        SELECT * FROM support_tickets
                        WHERE ticket_id = %s AND (uid = %s OR user_id = %s)
                        LIMIT 1
                    """, (clean_tid, uid_str, uid_str))
                    row = cur.fetchone()
                    if row:
                        return _normalize_ticket_row(row)

                # 2. البحث عن أحدث تذكرة مفتوحة للمستخدم
                cur.execute("""
                    SELECT * FROM support_tickets
                    WHERE (uid = %s OR user_id = %s) AND status = 'open'
                    ORDER BY updated_at DESC
                    LIMIT 1
                """, (uid_str, uid_str))
                row = cur.fetchone()
                if row:
                    return _normalize_ticket_row(row)

                # 3. إنشاء تذكرة جديدة إذا لم توجد تذكرة مفتوحة
                now_iso = datetime.now(timezone.utc).isoformat()
                ticket_id = custom_ticket_id or f"TK-{uid_str[-4:]}-{int(datetime.now().timestamp()) % 100000}"

                welcome_message = {
                    "sender": "admin",
                    "text": (
                        f"مرحباً بك في مركز الدعم الفني! 🎧\n"
                        f"كودك المرجعي للمحادثة: {ticket_id}\n\n"
                        f"يرجى التكرم بالالتزام بآداب الحوار والتعامل اللائق مع فريق الدعم. "
                        f"تفضل بكتابة استفسارك وسيقوم الفريق بالرد عليك في أقرب وقت."
                    ),
                    "timestamp": now_iso
                }

                messages_list = [welcome_message]

                cur.execute("""
                    INSERT INTO support_tickets (
                        ticket_id, uid, user_id, user_info, status,
                        has_unread_admin, last_sender, messages, created_at, updated_at
                    )
                    VALUES (%s, %s, %s, %s, 'open', FALSE, 'system', %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    ON CONFLICT (ticket_id) DO UPDATE
                    SET updated_at = CURRENT_TIMESTAMP
                    RETURNING *
                """, (
                    ticket_id,
                    uid_str,
                    uid_str,
                    Json(clean_info),
                    Json(messages_list)
                ))
                inserted_row = cur.fetchone()
                return _normalize_ticket_row(inserted_row)

    except Exception as e:
        logger.error(f"❌ Error in get_or_create_active_ticket: {e}")
        return None


def add_support_message(uid: str, ticket_id: str, text: str, sender: str = "user", user_info: dict = None) -> dict:
    """إضافة رسالة جديدة ذرياً في Supabase وإرجاع قائمة الرسائل المحدثة بالكامل للعرض اللحظي"""
    uid_str = str(uid).strip()
    clean_tid = str(ticket_id or '').strip()
    clean_text = str(text or '').strip()[:2000]

    if not clean_text:
        return {"success": False, "message": "لا يمكن إرسال رسالة فارغة"}

    now_iso = datetime.now(timezone.utc).isoformat()
    new_msg = {
        "sender": sender,
        "text": clean_text,
        "timestamp": now_iso
    }

    clean_info = _enrich_user_info(uid_str, user_info)
    has_unread = True if sender == "user" else False

    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # فحص التذكرة الحالية
                cur.execute("""
                    SELECT * FROM support_tickets
                    WHERE ticket_id = %s
                    LIMIT 1
                """, (clean_tid,))
                ticket_row = cur.fetchone()

                if not ticket_row:
                    # إذا لم تكن التذكرة موجودة في القاعدة (مثلاً كانت مؤقتة بالواجهة)، ننشئها فوراً ونضيف الرسالة
                    created_ticket = get_or_create_active_ticket(uid_str, custom_ticket_id=clean_tid, user_info=clean_info)
                    if not created_ticket:
                        return {"success": False, "message": "تعذر إنشاء أو العثور على التذكرة"}
                    clean_tid = created_ticket['ticket_id']
                else:
                    ticket_owner = str(ticket_row.get('uid') or ticket_row.get('user_id') or '')
                    if ticket_owner != uid_str and sender == "user":
                        return {"success": False, "message": "غير مصرح لك بالوصول لهذه التذكرة"}

                    if ticket_row.get('status') == 'closed':
                        return {"success": False, "message": "تم إنهاء هذه المحادثة بالكامل. يرجى فتح تذكرة جديدة."}

                # تحديث ذري وسريع لمصفوفة JSONB في PostgreSQL وإرجاع الرسائل المحدثة فوراً
                cur.execute("""
                    UPDATE support_tickets
                    SET messages = COALESCE(messages, '[]'::jsonb) || %s::jsonb,
                        updated_at = CURRENT_TIMESTAMP,
                        has_unread_admin = %s,
                        last_sender = %s,
                        user_info = CASE
                            WHEN %s::jsonb <> '{}'::jsonb THEN COALESCE(user_info, '{}'::jsonb) || %s::jsonb
                            ELSE user_info
                        END
                    WHERE ticket_id = %s
                    RETURNING ticket_id, status, messages
                """, (
                    Json([new_msg]),
                    has_unread,
                    sender,
                    Json(clean_info),
                    Json(clean_info),
                    clean_tid
                ))
                updated = cur.fetchone()
                if not updated:
                    return {"success": False, "message": "فشل تحديث الرسالة في التذكرة"}

                norm = _normalize_ticket_row(updated)
                return {
                    "success": True,
                    "ticket_id": norm["ticket_id"],
                    "status": norm.get("status", "open"),
                    "message_data": new_msg,
                    "messages": norm.get("messages", [])
                }

    except Exception as e:
        logger.error(f"❌ Error in add_support_message: {e}")
        return {"success": False, "message": f"خطأ في حفظ الرسالة: {str(e)}"}


def create_new_user_ticket(uid: str, user_info: dict = None) -> dict:
    """إغلاق أي تذكرة مفتوحة قديمة للمستخدم وإنشاء تذكرة دعم جديدة فوراً في Supabase"""
    uid_str = str(uid).strip()
    if not uid_str:
        return None

    clean_info = _enrich_user_info(uid_str, user_info)
    ticket_id = f"TK-{uid_str[-4:]}-{int(datetime.now().timestamp()) % 100000}"
    now_iso = datetime.now(timezone.utc).isoformat()

    welcome_message = {
        "sender": "admin",
        "text": (
            f"مرحباً بك في تذكرة الدعم الفني الجديدة! 🎧\n"
            f"الكود المرجعي: {ticket_id}\n\n"
            f"تفضل بكتابة استفسارك وسيقوم الفريق بالمتابعة والرد عليك."
        ),
        "timestamp": now_iso
    }

    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # إغلاق التذاكر المفتوحة السابقة لهذا المستخدم
                cur.execute("""
                    UPDATE support_tickets
                    SET status = 'closed',
                        has_unread_admin = FALSE,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE (uid = %s OR user_id = %s) AND status = 'open'
                """, (uid_str, uid_str))

                # إنشاء التذكرة الجديدة
                cur.execute("""
                    INSERT INTO support_tickets (
                        ticket_id, uid, user_id, user_info, status,
                        has_unread_admin, last_sender, messages, created_at, updated_at
                    )
                    VALUES (%s, %s, %s, %s, 'open', FALSE, 'system', %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    RETURNING *
                """, (
                    ticket_id,
                    uid_str,
                    uid_str,
                    Json(clean_info),
                    Json([welcome_message])
                ))
                row = cur.fetchone()
                return _normalize_ticket_row(row)
    except Exception as e:
        logger.error(f"❌ Error in create_new_user_ticket: {e}")
        return None
