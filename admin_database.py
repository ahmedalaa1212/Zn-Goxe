# -*- coding: utf-8 -*-
"""
ملف admin_database.py
يعمل كوسيط (Facade Router) يربط بين ملفات قاعدة البيانات الفرعية للموديولات
(مثل addons_db، admin_chat_db، super_admin_db إلخ) وقاعدة البيانات الرئيسية (Supabase PostgreSQL)
بدون أي اعتماد على Firebase.
"""

from datetime import datetime
from psycopg2.extras import RealDictCursor, Json
from database import (
    get_db,
    get_db_connection,
    _sanitize_id,
    format_iso,
    get_moderators,
    add_moderator,
    delete_moderator,
    get_admin_logs as _db_get_admin_logs,
    get_system_global_analytics as _db_get_system_global_analytics
)


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
    print(f"⚠️ Note: super_admin_db module import warning, using Supabase SQL fallbacks: {e}")

    # 🚫 دالة حظر مستخدم وحجب جهازه في Supabase PostgreSQL
    def ban_user_db(tg_id, reason="تم الحظر من قبل الإدارة العليا", admin_name="السوبر أدمن"):
        clean_id = _sanitize_id(tg_id)
        if not clean_id:
            return False, "معرف المستخدم غير صالح"
        try:
            with get_db_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        UPDATE users
                        SET is_banned = TRUE,
                            banned = TRUE,
                            ban_reason = %s,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE tg_id = %s OR user_id = %s OR telegram_id = %s
                        RETURNING device_id
                    """, (str(reason), clean_id, clean_id, clean_id))
                    rows = cur.fetchall()

                    device_ids = set()
                    for r in rows:
                        if r.get("device_id"):
                            device_ids.add(str(r["device_id"]).strip())

                    cur.execute("SELECT device_id FROM devices WHERE primary_user_id = %s", (clean_id,))
                    for d in cur.fetchall():
                        if d.get("device_id"):
                            device_ids.add(str(d["device_id"]).strip())

                    for dev_id in device_ids:
                        if dev_id:
                            cur.execute("""
                                INSERT INTO banned_devices (device_id, banned_user_id, reason, banned_by, banned_at)
                                VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                                ON CONFLICT (device_id) DO UPDATE
                                SET banned_user_id = EXCLUDED.banned_user_id,
                                    reason = EXCLUDED.reason,
                                    banned_by = EXCLUDED.banned_by,
                                    banned_at = CURRENT_TIMESTAMP
                            """, (dev_id, clean_id, str(reason), str(admin_name)))

                    cur.execute("""
                        INSERT INTO admin_logs (action, user_id, admin_id, status, details, created_at)
                        VALUES ('ban_user', %s, %s, 'completed', %s, CURRENT_TIMESTAMP)
                    """, (clean_id, str(admin_name), str(reason)))

            return True, f"تم حظر المستخدم {clean_id} وحظر الأجهزة المرتبطة به بنجاح"
        except Exception as err:
            return False, f"خطأ أثناء حظر المستخدم في Supabase: {err}"

    # 🟢 دالة فك الحظر عن المستخدم وجهازه في Supabase PostgreSQL
    def unban_user_db(tg_id, admin_name="السوبر أدمن"):
        clean_id = _sanitize_id(tg_id)
        if not clean_id:
            return False, "معرف المستخدم غير صالح"
        try:
            with get_db_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        UPDATE users
                        SET is_banned = FALSE,
                            banned = FALSE,
                            ban_reason = NULL,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE tg_id = %s OR user_id = %s OR telegram_id = %s
                        RETURNING device_id
                    """, (clean_id, clean_id, clean_id))
                    rows = cur.fetchall()

                    device_ids = set()
                    for r in rows:
                        if r.get("device_id"):
                            device_ids.add(str(r["device_id"]).strip())

                    cur.execute("SELECT device_id FROM devices WHERE primary_user_id = %s", (clean_id,))
                    for d in cur.fetchall():
                        if d.get("device_id"):
                            device_ids.add(str(d["device_id"]).strip())

                    for dev_id in device_ids:
                        if dev_id:
                            cur.execute("DELETE FROM banned_devices WHERE device_id = %s", (dev_id,))

                    cur.execute("DELETE FROM banned_devices WHERE banned_user_id = %s", (clean_id,))

                    cur.execute("""
                        INSERT INTO admin_logs (action, user_id, admin_id, status, details, created_at)
                        VALUES ('unban_user', %s, %s, 'completed', 'فك الحظر عن المستخدم', CURRENT_TIMESTAMP)
                    """, (clean_id, str(admin_name)))

            return True, f"تم فك الحظر عن المستخدم {clean_id} وجميع الأجهزة المربوطة به بنجاح"
        except Exception as err:
            return False, f"خطأ أثناء فك الحظر في Supabase: {err}"

    # 📊 دالة التحليلات الكلية من Supabase
    def get_system_global_analytics():
        return _db_get_system_global_analytics()

    # 👤 دوال المشرفين والسجلات
    def add_moderator_db(tg_id, name, permissions=None, admin_name="السوبر أدمن"):
        ok = add_moderator(tg_id, name, permissions, added_by=admin_name)
        return (True, "تمت إضافة المشرف بنجاح") if ok else (False, "تعذر إضافة المشرف")

    def list_moderators_db():
        return get_moderators()

    def remove_moderator_db(tg_id, admin_name="السوبر أدمن"):
        ok = delete_moderator(tg_id, deleted_by=admin_name)
        return (True, "تم حذف المشرف بنجاح") if ok else (False, "تعذر حذف المشرف")

    def get_admin_logs(limit=50):
        return _db_get_admin_logs(limit=limit)

    def modify_user_balance_admin(tg_id, amount, balance_type="balance", operation="add", admin_name="السوبر أدمن"):
        clean_id = _sanitize_id(tg_id)
        if not clean_id:
            return False, "معرف المستخدم غير صالح", 0.0
        col_map = {
            "balance": "balance",
            "zn": "balance",
            "znx": "znx_balance",
            "znx_balance": "znx_balance",
            "usd": "usd_balance",
            "usdt": "usd_balance",
            "usd_balance": "usd_balance",
            "ad": "ad_balance",
            "ad_balance": "ad_balance"
        }
        col = col_map.get(str(balance_type).lower(), "balance")
        try:
            val = float(amount)
            delta = -abs(val) if str(operation).lower() in ("sub", "subtract", "minus") else abs(val)
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    if str(operation).lower() == "set":
                        cur.execute(f"""
                            UPDATE users
                            SET {col} = GREATEST(0.0, %s), updated_at = CURRENT_TIMESTAMP
                            WHERE tg_id = %s OR user_id = %s OR telegram_id = %s
                            RETURNING {col}
                        """, (max(0.0, val), clean_id, clean_id, clean_id))
                    else:
                        cur.execute(f"""
                            UPDATE users
                            SET {col} = GREATEST(0.0, COALESCE({col}, 0.0) + %s), updated_at = CURRENT_TIMESTAMP
                            WHERE tg_id = %s OR user_id = %s OR telegram_id = %s
                            RETURNING {col}
                        """, (delta, clean_id, clean_id, clean_id))
                    row = cur.fetchone()
                    if not row:
                        return False, "المستخدم غير موجود", 0.0
                    new_bal = float(row[0] or 0.0)
                    cur.execute("""
                        INSERT INTO admin_logs (action, user_id, admin_id, status, amount, details, created_at)
                        VALUES (%s, %s, %s, 'completed', %s, %s, CURRENT_TIMESTAMP)
                    """, (f"modify_{col}_{operation}", clean_id, str(admin_name), val, f"رصيد جديد: {new_bal}"))
                    return True, "تم تحديث الرصيد بنجاح", new_bal
        except Exception as err:
            return False, f"خطأ تعديل الرصيد: {err}", 0.0

    def reset_user_account_admin(tg_id, admin_name="السوبر أدمن"):
        clean_id = _sanitize_id(tg_id)
        if not clean_id:
            return False, "معرف المستخدم غير صالح"
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE users
                        SET balance = 0.0,
                            znx_balance = 0.0,
                            usd_balance = 0.0,
                            ad_balance = 0.0,
                            farm_level = 1,
                            storage_level = 0,
                            upgrades_count = 0,
                            upgrades = '{}'::jsonb,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE tg_id = %s OR user_id = %s OR telegram_id = %s
                    """, (clean_id, clean_id, clean_id))
                    cur.execute("""
                        INSERT INTO admin_logs (action, user_id, admin_id, status, details, created_at)
                        VALUES ('reset_account', %s, %s, 'completed', 'تصفير الحساب', CURRENT_TIMESTAMP)
                    """, (clean_id, str(admin_name)))
            return True, f"تم تصفير حساب المستخدم {clean_id} بنجاح"
        except Exception as err:
            return False, f"خطأ تصفير الحساب: {err}"

    # 📢 دوال الإشعارات والبث الجماعي في Supabase
    def get_all_user_ids():
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT tg_id FROM users
                        WHERE COALESCE(is_banned, FALSE) = FALSE
                          AND COALESCE(banned, FALSE) = FALSE
                          AND tg_id IS NOT NULL
                    """)
                    return [str(r[0]) for r in cur.fetchall() if r and r[0]]
        except Exception as err:
            print(f"❌ Error fetching user ids from Supabase: {err}")
            return []

    def log_broadcast_campaign(admin_name, message, total_targets, success_count, blocked_count):
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO broadcasts (admin_name, message_snippet, total_targets, success_count, blocked_count, created_at)
                        VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    """, (str(admin_name), str(message or "")[:100], int(total_targets or 0), int(success_count or 0), int(blocked_count or 0)))
            return True
        except Exception as err:
            print(f"❌ Error logging broadcast in Supabase: {err}")
            return False

    def get_user_by_id(user_id):
        clean_id = _sanitize_id(user_id)
        if not clean_id:
            return False, None
        try:
            with get_db_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT * FROM users
                        WHERE tg_id = %s OR user_id = %s OR telegram_id = %s
                        LIMIT 1
                    """, (clean_id, clean_id, clean_id))
                    row = cur.fetchone()
                    if row:
                        d = dict(row)
                        for k, v in list(d.items()):
                            if isinstance(v, datetime):
                                d[k] = format_iso(v)
                        return True, d
                    return False, None
        except Exception as err:
            print(f"❌ Error fetching user in Supabase: {err}")
            return False, None

    def get_latest_broadcast_stats():
        try:
            with get_db_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("SELECT * FROM broadcasts ORDER BY created_at DESC LIMIT 1")
                    row = cur.fetchone()
                    if row:
                        d = dict(row)
                        if isinstance(d.get("created_at"), datetime):
                            d["created_at"] = format_iso(d["created_at"])
                        return d
                    return None
        except Exception as err:
            print(f"❌ Error getting latest campaign from Supabase: {err}")
            return None


# ==================== إعادة توجيه وظائف محادثات الدعم والإدارة (Admin Chat) ====================
try:
    from admin_chat.admin_chat_db import *
except ImportError:
    pass
