# -*- coding: utf-8 -*-
# admin_chat/admin_chat_db.py
import json
from datetime import datetime
from psycopg2.extras import RealDictCursor, Json
import database
from database import get_db_connection, format_iso


def get_db():
    """ضمان الحصول على كائن قاعدة البيانات Supabase Pool"""
    return database.get_db()


def _normalize_ticket(row):
    """تنسيق بيانات التذكرة لتتوافق مع واجهة الأدمن"""
    if not row:
        return None
    t = dict(row)
    for k in ('created_at', 'updated_at'):
        if isinstance(t.get(k), datetime):
            t[k] = format_iso(t[k])

    if isinstance(t.get('user_info'), str):
        try:
            t['user_info'] = json.loads(t['user_info'])
        except Exception:
            t['user_info'] = {}
    elif not isinstance(t.get('user_info'), dict):
        t['user_info'] = {}

    if isinstance(t.get('messages'), str):
        try:
            t['messages'] = json.loads(t['messages'])
        except Exception:
            t['messages'] = []
    elif not isinstance(t.get('messages'), list):
        t['messages'] = []

    t['has_unread_admin'] = bool(t.get('has_unread_admin', False))
    return t


def get_all_tickets_from_db(limit=100):
    """جلب أحدث تذاكر الدعم الفني من Supabase مرتبة حسب آخر رسالة أو تحديث"""
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT
                        st.*,
                        u.first_name AS db_first_name,
                        u.username AS db_username
                    FROM support_tickets st
                    LEFT JOIN users u ON st.uid = u.tg_id
                    ORDER BY
                        CASE WHEN st.has_unread_admin = TRUE AND st.status <> 'closed' THEN 0 ELSE 1 END,
                        st.updated_at DESC
                    LIMIT %s
                """, (int(limit),))
                rows = cur.fetchall()
                tickets = []
                for r in rows:
                    db_first_name = r.pop('db_first_name', None)
                    db_username = r.pop('db_username', None)
                    t = _normalize_ticket(r)
                    if not t['user_info'].get('first_name') and db_first_name:
                        t['user_info']['first_name'] = db_first_name
                    if not t['user_info'].get('username') and db_username:
                        t['user_info']['username'] = db_username
                    tickets.append(t)
                return tickets
    except Exception as e:
        print(f"⚠️ [Supabase Admin Tickets Error]: {e}")
        return []


def get_ticket_by_id_from_db(ticket_id):
    """جلب تذكرة واحدة فقط برقم التذكرة من Supabase"""
    clean_tid = str(ticket_id or '').strip()
    if not clean_tid:
        return None

    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT
                        st.*,
                        u.first_name AS db_first_name,
                        u.username AS db_username
                    FROM support_tickets st
                    LEFT JOIN users u ON st.uid = u.tg_id
                    WHERE st.ticket_id = %s
                    LIMIT 1
                """, (clean_tid,))
                row = cur.fetchone()
                if not row:
                    return None
                db_first_name = row.pop('db_first_name', None)
                db_username = row.pop('db_username', None)
                t = _normalize_ticket(row)
                if not t['user_info'].get('first_name') and db_first_name:
                    t['user_info']['first_name'] = db_first_name
                if not t['user_info'].get('username') and db_username:
                    t['user_info']['username'] = db_username
                return t
    except Exception as e:
        print(f"⚠️ [get_ticket_by_id_from_db Error]: {e}")
        return None


def mark_ticket_read_in_db(ticket_id):
    """تحديث حالة التذكرة إلى مقروءة بواسطة الأدمن بشكل مباشر في Supabase"""
    clean_tid = str(ticket_id or '').strip()
    if not clean_tid:
        return False

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE support_tickets
                    SET has_unread_admin = FALSE
                    WHERE ticket_id = %s
                """, (clean_tid,))
        return True
    except Exception as e:
        print(f"⚠️ [mark_ticket_read_in_db Error]: {e}")
        return False


def add_admin_reply_to_db(ticket_id, text, now_str):
    """إضافة رد الأدمن ذرياً في Supabase وتحديث حالة التذكرة وإرجاع الرسائل المحدثة"""
    clean_tid = str(ticket_id or '').strip()
    clean_text = str(text or '').strip()
    if not clean_tid or not clean_text:
        return False, None, "بيانات التذكرة أو الرسالة ناقصة"

    new_msg = {
        'sender': 'admin',
        'text': clean_text,
        'timestamp': now_str
    }

    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    UPDATE support_tickets
                    SET messages = COALESCE(messages, '[]'::jsonb) || %s::jsonb,
                        updated_at = CURRENT_TIMESTAMP,
                        has_unread_admin = FALSE,
                        last_sender = 'admin',
                        status = 'open'
                    WHERE ticket_id = %s
                    RETURNING uid, user_id, user_info
                """, (Json([new_msg]), clean_tid))
                row = cur.fetchone()
                if not row:
                    return False, None, "التذكرة غير موجودة"

                u_info = row.get('user_info') if isinstance(row.get('user_info'), dict) else {}
                user_id = row.get('uid') or row.get('user_id') or u_info.get('id')
                return True, user_id, None
    except Exception as e:
        print(f"⚠️ [add_admin_reply_to_db Error]: {e}")
        return False, None, f"خطأ قاعدة البيانات: {str(e)}"


def close_ticket_in_db(ticket_id, now_str):
    """إغلاق التذكرة وتحديث حالتها إلى closed في Supabase"""
    clean_tid = str(ticket_id or '').strip()
    if not clean_tid:
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
                """, (clean_tid,))
        return True
    except Exception as e:
        print(f"⚠️ [close_ticket_in_db Error]: {e}")
        return False
