# -*- coding: utf-8 -*-
# admin_chat/admin_chat_db.py
import json
from datetime import datetime
from psycopg2.extras import RealDictCursor, Json
import database
from database import get_db_connection, format_iso


def get_db():
    """ضمان الحصول على كائن قاعدة البيانات Supabase PostgreSQL"""
    return database.get_db()


def _format_ticket(row: dict) -> dict:
    """تنسيق سجل التذكرة المستخرج من قاعدة البيانات ودمج بيانات المستخدم"""
    if not row:
        return None
    t = dict(row)
    for k in ("created_at", "updated_at"):
        if isinstance(t.get(k), datetime):
            t[k] = format_iso(t[k])

    if isinstance(t.get("user_info"), str):
        try:
            t["user_info"] = json.loads(t["user_info"])
        except Exception:
            t["user_info"] = {}
    elif not isinstance(t.get("user_info"), dict):
        t["user_info"] = {}

    # إثراء user_info من جدول users إذا كانت ناقصة
    u_first_name = t.pop("_u_first_name", None)
    u_username = t.pop("_u_username", None)
    if not t["user_info"].get("first_name") and u_first_name:
        t["user_info"]["first_name"] = u_first_name
    if not t["user_info"].get("username") and u_username:
        t["user_info"]["username"] = u_username
    if not t["user_info"].get("id"):
        t["user_info"]["id"] = t.get("uid") or t.get("user_id") or ""

    if isinstance(t.get("messages"), str):
        try:
            t["messages"] = json.loads(t["messages"])
        except Exception:
            t["messages"] = []
    elif not isinstance(t.get("messages"), list):
        t["messages"] = []

    return t


def get_all_tickets_from_db(limit=50):
    """جلب أحدث تذاكر الدعم الفني من Supabase مرتبة حسب آخر تحديث"""
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT
                        st.*,
                        COALESCE(u.first_name, u.name) AS _u_first_name,
                        u.username AS _u_username
                    FROM support_tickets st
                    LEFT JOIN users u ON u.tg_id = st.uid
                    ORDER BY st.updated_at DESC
                    LIMIT %s
                """, (int(limit),))
                rows = cur.fetchall()
                return [_format_ticket(r) for r in rows]
    except Exception as e:
        print(f"⚠️ [Admin Chat DB Warning - get_all_tickets_from_db]: {e}")
        return []


def get_ticket_by_id_from_db(ticket_id):
    """جلب تذكرة واحدة فقط برقم التذكرة من Supabase"""
    clean_id = str(ticket_id or "").strip()
    if not clean_id:
        return None
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT
                        st.*,
                        COALESCE(u.first_name, u.name) AS _u_first_name,
                        u.username AS _u_username
                    FROM support_tickets st
                    LEFT JOIN users u ON u.tg_id = st.uid
                    WHERE st.ticket_id = %s
                    LIMIT 1
                """, (clean_id,))
                row = cur.fetchone()
                if not row:
                    return None
                return _format_ticket(row)
    except Exception as e:
        print(f"⚠️ [Admin Chat DB Warning - get_ticket_by_id_from_db]: {e}")
        return None


def mark_ticket_read_in_db(ticket_id):
    """تحديث حالة التذكرة إلى مقروءة بواسطة الأدمن في Supabase"""
    clean_id = str(ticket_id or "").strip()
    if not clean_id:
        return False
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE support_tickets
                    SET has_unread_admin = FALSE
                    WHERE ticket_id = %s
                """, (clean_id,))
        return True
    except Exception as e:
        print(f"⚠️ [Admin Chat DB Warning - mark_ticket_read_in_db]: {e}")
        return False


def add_admin_reply_to_db(ticket_id, text, now_str):
    """إضافة رد الأدمن وتحديث بيانات التذكرة في Supabase، وإرجاع user_id"""
    clean_id = str(ticket_id or "").strip()
    clean_text = str(text or "").strip()
    if not clean_id or not clean_text:
        return False, None, "بيانات التذكرة أو الرسالة ناقصة"

    new_msg = {
        "sender": "admin",
        "text": clean_text,
        "timestamp": now_str
    }

    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    UPDATE support_tickets
                    SET messages = COALESCE(messages, '[]'::jsonb) || %s::jsonb,
                        has_unread_admin = FALSE,
                        last_sender = 'admin',
                        status = 'open',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE ticket_id = %s
                    RETURNING uid, user_id, user_info
                """, (Json([new_msg]), clean_id))
                row = cur.fetchone()
                if not row:
                    return False, None, "التذكرة غير موجودة"

                u_info = row.get("user_info") if isinstance(row.get("user_info"), dict) else {}
                user_id = row.get("uid") or row.get("user_id") or u_info.get("id")
                return True, user_id, None
    except Exception as e:
        print(f"⚠️ [Admin Chat DB Warning - add_admin_reply_to_db]: {e}")
        return False, None, f"خطأ في قاعدة البيانات: {str(e)}"


def close_ticket_in_db(ticket_id, now_str):
    """إغلاق التذكرة وتحديث حالتها إلى closed في Supabase"""
    clean_id = str(ticket_id or "").strip()
    if not clean_id:
        return False
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE support_tickets
                    SET status = 'closed',
                        has_unread_admin = FALSE,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE ticket_id = %s
                """, (clean_id,))
        return True
    except Exception as e:
        print(f"⚠️ [Admin Chat DB Warning - close_ticket_in_db]: {e}")
        return False
