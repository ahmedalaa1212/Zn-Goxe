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
    """الحصول على كائن الاتصال بقاعدة البيانات Supabase PostgreSQL"""
    return database.get_db()


def _normalize_ticket_row(row: dict) -> dict:
    """تنسيق بيانات التذكرة المستخرجة من PostgreSQL لتتوافق مع الواجهة الأمامية"""
    if not row:
        return None
    d = dict(row)
    for k in ("created_at", "updated_at"):
        if isinstance(d.get(k), datetime):
            d[k] = format_iso(d[k])

    if isinstance(d.get("user_info"), str):
        try:
            d["user_info"] = json.loads(d["user_info"])
        except Exception:
            d["user_info"] = {}
    elif not isinstance(d.get("user_info"), dict):
        d["user_info"] = {}

    if isinstance(d.get("messages"), str):
        try:
            d["messages"] = json.loads(d["messages"])
        except Exception:
            d["messages"] = []
    elif not isinstance(d.get("messages"), list):
        d["messages"] = []

    return d


def _enrich_user_info(cur, uid_str: str, user_info: dict = None) -> dict:
    """ضمان وجود اسم ومعرف المستخدم داخل user_info لظهورها بشكل واضح عند الأدمن"""
    info = dict(user_info) if isinstance(user_info, dict) else {}
    info["id"] = uid_str
    if not info.get("first_name") or not info.get("username"):
        try:
            cur.execute("""
                SELECT COALESCE(first_name, name, 'مستخدم') AS first_name, COALESCE(username, '') AS username
                FROM users
                WHERE tg_id = %s OR user_id = %s OR telegram_id = %s
                LIMIT 1
            """, (uid_str, uid_str, uid_str))
            u_row = cur.fetchone()
            if u_row:
                if not info.get("first_name"):
                    info["first_name"] = u_row.get("first_name") if isinstance(u_row, dict) else u_row[0]
                if not info.get("username"):
                    info["username"] = u_row.get("username") if isinstance(u_row, dict) else u_row[1]
        except Exception:
            pass
    return info


def get_or_create_active_ticket(uid: str, custom_ticket_id: str = None, user_info: dict = None) -> dict:
    """جلب التذكرة النشطة للمستخدم أو إنشاء تذكرة جديدة في Supabase PostgreSQL"""
    uid_str = str(uid or "").strip()
    if not uid_str:
        return None

    clean_custom_id = str(custom_ticket_id).strip() if custom_ticket_id else None

    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # 1. إذا تم تمرير رقم تذكرة محدد، نتحقق منه ومن ملكيته للمستخدم
                if clean_custom_id:
                    cur.execute("""
                        SELECT * FROM support_tickets
                        WHERE ticket_id = %s AND (uid = %s OR user_id = %s)
                        LIMIT 1
                    """, (clean_custom_id, uid_str, uid_str))
                    row = cur.fetchone()
                    if row:
                        return _normalize_ticket_row(row)

                # 2. البحث عن أي تذكرة مفتوحة حالياً للمستخدم
                cur.execute("""
                    SELECT * FROM support_tickets
                    WHERE (uid = %s OR user_id = %s) AND status = 'open'
                    ORDER BY updated_at DESC
                    LIMIT 1
                """, (uid_str, uid_str))
                row = cur.fetchone()
                if row:
                    if user_info and isinstance(user_info, dict):
                        enriched_info = _enrich_user_info(cur, uid_str, user_info)
                        cur.execute("""
                            UPDATE support_tickets
                            SET user_info = %s
                            WHERE ticket_id = %s
                        """, (Json(enriched_info), row["ticket_id"]))
                        row["user_info"] = enriched_info
                    return _normalize_ticket_row(row)

                # 3. إنشاء تذكرة جديدة في حال عدم وجود تذكرة مفتوحة
                now_iso = datetime.now(timezone.utc).isoformat()
                ticket_id = clean_custom_id or f"TK-{uid_str[-4:]}-{int(datetime.now(timezone.utc).timestamp()) % 100000}"
                enriched_info = _enrich_user_info(cur, uid_str, user_info)

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
                    VALUES (%s, %s, %s, %s, 'open', TRUE, 'system', %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    ON CONFLICT (ticket_id) DO UPDATE
                    SET updated_at = CURRENT_TIMESTAMP
                    RETURNING *
                """, (
                    ticket_id,
                    uid_str,
                    uid_str,
                    Json(enriched_info),
                    Json(messages_list)
                ))
                inserted_row = cur.fetchone()
                return _normalize_ticket_row(inserted_row)

    except Exception as e:
        logger.error(f"❌ [support_db] خطأ في get_or_create_active_ticket: {e}")
        return None


def add_support_message(uid: str, ticket_id: str, text: str, sender: str = "user", user_info: dict = None) -> dict:
    """إضافة رسالة جديدة إلى التذكرة بشكل ذري وسريع في Supabase PostgreSQL"""
    uid_str = str(uid or "").strip()
    clean_ticket_id = str(ticket_id or "").strip()
    clean_text = str(text or "").strip()[:2000]

    if not clean_text:
        return {"success": False, "message": "لا يمكن إرسال رسالة فارغة"}

    if not uid_str or not clean_ticket_id:
        return {"success": False, "message": "بيانات التذكرة أو المستخدم غير مكتملة"}

    now_iso = datetime.now(timezone.utc).isoformat()
    new_msg = {
        "sender": sender,
        "text": clean_text,
        "timestamp": now_iso
    }

    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM support_tickets
                    WHERE ticket_id = %s
                    LIMIT 1
                """, (clean_ticket_id,))
                ticket_row = cur.fetchone()

                if not ticket_row:
                    created_ticket = get_or_create_active_ticket(uid_str, custom_ticket_id=clean_ticket_id, user_info=user_info)
                    if not created_ticket:
                        return {"success": False, "message": "تعذر العثور على التذكرة أو إنشاؤها"}
                    ticket_row = created_ticket
                    clean_ticket_id = created_ticket.get("ticket_id", clean_ticket_id)

                ticket_owner = str(ticket_row.get("uid") or ticket_row.get("user_id") or "")
                if ticket_owner != uid_str:
                    return {"success": False, "message": "غير مصرح لك بالوصول لهذه التذكرة"}

                if ticket_row.get("status") == "closed":
                    return {"success": False, "message": "تم إنهاء هذه المحادثة بالكامل."}

                enriched_info = _enrich_user_info(cur, uid_str, user_info or ticket_row.get("user_info"))
                has_unread = True if sender == "user" else False

                cur.execute("""
                    UPDATE support_tickets
                    SET messages = COALESCE(messages, '[]'::jsonb) || %s::jsonb,
                        user_info = %s,
                        has_unread_admin = %s,
                        last_sender = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE ticket_id = %s
                    RETURNING *
                """, (
                    Json([new_msg]),
                    Json(enriched_info),
                    has_unread,
                    sender,
                    clean_ticket_id
                ))
                updated_row = cur.fetchone()
                normalized = _normalize_ticket_row(updated_row) or {}

                return {
                    "success": True,
                    "ticket_id": clean_ticket_id,
                    "status": normalized.get("status", "open"),
                    "message_data": new_msg,
                    "messages": normalized.get("messages", [])
                }

    except Exception as e:
        logger.error(f"❌ [support_db] خطأ في add_support_message: {e}")
        return {"success": False, "message": "حدث خطأ أثناء حفظ الرسالة في قاعدة البيانات"}


def create_new_user_ticket(uid: str, user_info: dict = None) -> dict:
    """إغلاق أي تذكرة مفتوحة قديمة وإنشاء تذكرة دعم جديدة فوراً في Supabase"""
    uid_str = str(uid or "").strip()
    if not uid_str:
        return None

    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # 1. إغلاق أي تذاكر مفتوحة سابقة للمستخدم
                cur.execute("""
                    UPDATE support_tickets
                    SET status = 'closed',
                        has_unread_admin = FALSE,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE (uid = %s OR user_id = %s) AND status = 'open'
                """, (uid_str, uid_str))

                # 2. إنشاء تذكرة جديدة
                ticket_id = f"TK-{uid_str[-4:]}-{int(datetime.now(timezone.utc).timestamp()) % 100000}"
                now_iso = datetime.now(timezone.utc).isoformat()
                enriched_info = _enrich_user_info(cur, uid_str, user_info)

                welcome_message = {
                    "sender": "admin",
                    "text": (
                        f"مرحباً بك في تذكرة الدعم الفني الجديدة! 🎧\n"
                        f"الكود المرجعي: {ticket_id}\n\n"
                        f"تفضل بكتابة استفسارك وسيقوم الفريق بالمتابعة والرد عليك."
                    ),
                    "timestamp": now_iso
                }

                cur.execute("""
                    INSERT INTO support_tickets (
                        ticket_id, uid, user_id, user_info, status,
                        has_unread_admin, last_sender, messages, created_at, updated_at
                    )
                    VALUES (%s, %s, %s, %s, 'open', TRUE, 'system', %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    RETURNING *
                """, (
                    ticket_id,
                    uid_str,
                    uid_str,
                    Json(enriched_info),
                    Json([welcome_message])
                ))
                new_row = cur.fetchone()
                return _normalize_ticket_row(new_row)

    except Exception as e:
        logger.error(f"❌ [support_db] خطأ في create_new_user_ticket: {e}")
        return None
