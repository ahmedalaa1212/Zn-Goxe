# -*- coding: utf-8 -*-
"""
database.py - نسخة محسنة للسرعة والاستقرار مع Supabase/PostgreSQL

أهم التغييرات:
1) إزالة SELECT 1 من كل عملية get_db_connection()؛ لأن فحص الاتصال في كل طلب
   يضيف Round Trip إضافياً ولا يعالج مشكلة الاتصال الميت بشكل أفضل من التعامل
   مع OperationalError عند الاستخدام.
2) عدم تشغيل CREATE TABLE / CREATE INDEX داخل init_db_pool().
3) Connection Pool أصغر افتراضياً لتفادي إنشاء عدد كبير من الاتصالات مع Gunicorn workers.
4) init_user() أقل عدداً في الاستعلامات.
5) is_user_banned() يجلب is_banned فقط.
6) check_and_bind_device() يعيد استخدام نفس الاتصال بدلاً من فتح اتصال إضافي لفحص المستخدم.
7) atomic_update_balance() أصبح UPDATE ذريّاً واحداً مع RETURNING.
8) الإبقاء على نفس أسماء الدوال الرئيسية حتى لا تحتاج بقية ملفات المشروع لتغييرات.
"""

import json
import os
import math
import threading
from datetime import datetime, timezone
from contextlib import contextmanager

import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor, Json


# =============================================================================
# Configuration
# =============================================================================

db_pool = None
_pool_lock = threading.Lock()
_tables_created = False
_tables_lock = threading.Lock()

# لا تنشئ الجداول والفهارس في كل تشغيل افتراضياً.
# بما أن قاعدة الإنتاج موجودة بالفعل، هذا يمنع تأخير الإقلاع.
AUTO_CREATE_TABLES = os.environ.get("DB_AUTO_CREATE_TABLES", "0").strip().lower() in (
    "1", "true", "yes", "on"
)

POOL_MIN = max(1, int(os.environ.get("DB_POOL_MIN", "1")))
POOL_MAX = max(POOL_MIN, int(os.environ.get("DB_POOL_MAX", "8")))


# =============================================================================
# Supabase / PostgreSQL Connection Pool
# =============================================================================

def get_database_url():
    """استخراج وتنظيف DATABASE_URL من متغيرات البيئة."""
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise ValueError(
            "❌ لم يتم العثور على DATABASE_URL! "
            "تأكد من إضافته في Railway."
        )

    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    return db_url


def init_db_pool():
    """
    إنشاء Pool مرة واحدة لكل Process.

    مهم:
    - لا يوجد هنا SELECT 1.
    - لا يوجد إنشاء للجداول.
    - الاتصال الأول فقط يتم عند أول استخدام.
    """
    global db_pool

    if db_pool is not None and not db_pool.closed:
        return db_pool

    with _pool_lock:
        if db_pool is not None and not db_pool.closed:
            return db_pool

        db_url = get_database_url()

        try:
            db_pool = pool.ThreadedConnectionPool(
                minconn=POOL_MIN,
                maxconn=POOL_MAX,
                dsn=db_url,
                connect_timeout=3,
                keepalives=1,
                keepalives_idle=30,
                keepalives_interval=10,
                keepalives_count=3,
            )

            print(
                f"✅ Supabase pool جاهز "
                f"(min={POOL_MIN}, max={POOL_MAX})"
            )

        except Exception as e:
            print(f"❌ فشل إنشاء Supabase Connection Pool: {e}")
            db_pool = None
            raise

        return db_pool


@contextmanager
def get_db_connection():
    """
    إعطاء اتصال من الـ pool ثم إرجاعه.

    لا يتم تنفيذ SELECT 1 هنا.
    إذا كان الاتصال ميتاً، psycopg2 سيعطي OperationalError أثناء الاستعلام،
    وعندها نغلق الاتصال المكسور حتى يقوم الـ pool بإنشاء بديل.
    """
    pool_obj = init_db_pool()
    conn = None

    try:
        conn = pool_obj.getconn()
        yield conn

    except (psycopg2.OperationalError, psycopg2.InterfaceError):
        if conn is not None:
            try:
                pool_obj.putconn(conn, close=True)
            except Exception:
                pass
            conn = None
        raise

    finally:
        if conn is not None:
            try:
                if not conn.closed:
                    conn.rollback()
                    pool_obj.putconn(conn)
                else:
                    pool_obj.putconn(conn, close=True)
            except Exception:
                try:
                    pool_obj.putconn(conn, close=True)
                except Exception:
                    pass


def get_db():
    """دالة توافقية مع بقية الموديولات."""
    return init_db_pool()


# =============================================================================
# Optional DB bootstrap
# =============================================================================

def _auto_create_tables():
    """
    إنشاء الجداول والفهارس عند الحاجة فقط.

    لا تُستدعى من init_db_pool().
    لتفعيلها في مشروع جديد:
        DB_AUTO_CREATE_TABLES=1
    """
    global _tables_created

    if _tables_created:
        return True

    with _tables_lock:
        if _tables_created:
            return True

        create_tables_sql = """
        CREATE TABLE IF NOT EXISTS users (
            tg_id VARCHAR(128) PRIMARY KEY,
            user_id VARCHAR(128),
            telegram_id VARCHAR(128),
            first_name VARCHAR(100) DEFAULT 'لاعب',
            balance DOUBLE PRECISION DEFAULT 0.0,
            usd_balance DOUBLE PRECISION DEFAULT 0.0,
            znx_balance DOUBLE PRECISION DEFAULT 0.0,
            ref_by VARCHAR(128),
            referrals_count INT DEFAULT 0,
            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            last_active_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            interactions INT DEFAULT 1,
            last_withdraw_date TIMESTAMPTZ,
            withdraw_count INT DEFAULT 0,
            is_banned BOOLEAN DEFAULT FALSE,
            ban_reason TEXT,
            banned_at TIMESTAMPTZ,
            farm_level INT DEFAULT 1,
            storage_level INT DEFAULT 1,
            last_harvest TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            device_id VARCHAR(256),
            fingerprint_hash VARCHAR(256),
            extra_data JSONB DEFAULT '{}'::jsonb
        );

        CREATE TABLE IF NOT EXISTS devices (
            device_id VARCHAR(256) PRIMARY KEY,
            primary_user_id VARCHAR(128),
            users JSONB DEFAULT '[]'::jsonb,
            fingerprint_hash VARCHAR(256),
            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            last_seen TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            is_banned BOOLEAN DEFAULT FALSE,
            ban_reason TEXT,
            banned_at TIMESTAMPTZ
        );

        CREATE TABLE IF NOT EXISTS banned_devices (
            device_id VARCHAR(256) PRIMARY KEY,
            reason TEXT,
            banned_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            associated_users JSONB DEFAULT '[]'::jsonb,
            fingerprint_hash VARCHAR(256)
        );

        CREATE INDEX IF NOT EXISTS idx_users_balance
            ON users(balance DESC);

        CREATE INDEX IF NOT EXISTS idx_users_ref_by
            ON users(ref_by);

        CREATE INDEX IF NOT EXISTS idx_devices_fingerprint
            ON devices(fingerprint_hash);
        """

        try:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(create_tables_sql)
                conn.commit()

            _tables_created = True
            print("⚡ تم التحقق من جداول Supabase والفهارس.")
            return True

        except Exception as e:
            print(f"⚠️ فشل إعداد جداول Supabase: {e}")
            return False


if AUTO_CREATE_TABLES:
    # استخدم متغير البيئة فقط عندما تحتاج bootstrap لقاعدة جديدة.
    # في الإنتاج الحالي يفضل تركه = 0.
    _auto_create_tables()


# =============================================================================
# Safe Import of ZNX Wallet Module
# =============================================================================

try:
    from znx_wallet.znx_wallet_db import (
        get_leaderboard_data as znx_get_leaderboard_data,
        get_user_data as znx_get_user_data,
        execute_conversion as znx_execute_conversion,
        get_global_stats as znx_get_global_stats
    )
except ImportError:
    znx_get_leaderboard_data = None
    znx_get_user_data = None
    znx_execute_conversion = None
    znx_get_global_stats = None


def get_user_data(telegram_id):
    """جلب بيانات محفظة المستخدم من وحدة ZNX أو fallback."""
    if callable(znx_get_user_data):
        return znx_get_user_data(telegram_id)
    return get_user(telegram_id)


def execute_conversion(telegram_id, amount_zn):
    """تنفيذ تحويل العملات."""
    if callable(znx_execute_conversion):
        return znx_execute_conversion(telegram_id, amount_zn)
    return {
        "success": False,
        "message": "الموديول غير متصل حالياً"
    }


def get_global_stats():
    """جلب الإحصائيات العامة للمحفظة."""
    if callable(znx_get_global_stats):
        return znx_get_global_stats()
    return {
        "total_users": 0,
        "total_converted": 0.0
    }


# =============================================================================
# Security & Input Helpers
# =============================================================================

def _sanitize_telegram_id(telegram_id):
    """تنظيف والتحقق من Telegram ID."""
    if telegram_id is None:
        return None

    s_id = str(telegram_id).strip()

    if not s_id or s_id.lower() in (
        "none", "null", "undefined", "false", "true"
    ):
        return None

    if "/" in s_id or ".." in s_id or "\\" in s_id:
        return None

    if len(s_id) > 128:
        return None

    return s_id


def sanitize_firestore_data(data):
    """تحويل datetime والكائنات القابلة للتحويل إلى شكل آمن."""
    if data is None:
        return None

    if isinstance(data, dict):
        return {
            k: sanitize_firestore_data(v)
            for k, v in data.items()
        }

    if isinstance(data, (list, tuple, set)):
        return [
            sanitize_firestore_data(v)
            for v in data
        ]

    if isinstance(data, datetime):
        return data.isoformat()

    if hasattr(data, "isoformat") and callable(getattr(data, "isoformat")):
        return data.isoformat()

    if hasattr(data, "__dict__"):
        return str(data)

    return data


def _safe_identifier(name):
    """
    حماية أسماء الأعمدة عند استخدام UPDATE ديناميكي.
    القيم نفسها ما زالت تمر عبر parameters.
    """
    if not isinstance(name, str):
        raise ValueError("اسم الحقل غير صالح")

    clean = name.strip()

    if not clean:
        raise ValueError("اسم الحقل فارغ")

    if not (
        clean[0].isalpha() or clean[0] == "_"
    ):
        raise ValueError(f"اسم الحقل غير صالح: {clean}")

    if not all(
        ch.isalnum() or ch == "_"
        for ch in clean
    ):
        raise ValueError(f"اسم الحقل غير صالح: {clean}")

    return clean


# =============================================================================
# Multi-Accounting & Device Security
# =============================================================================

def _ban_user_and_device_in_cursor(
    cur,
    telegram_id,
    device_id=None,
    reason="تعدد حسابات غير مصرح به",
    fingerprint_hash=None,
):
    """نسخة داخلية تعمل داخل نفس الـ transaction."""
    user_id_str = _sanitize_telegram_id(telegram_id)
    now_dt = datetime.now(timezone.utc)

    if user_id_str:
        cur.execute(
            """
            UPDATE users
            SET is_banned = TRUE,
                ban_reason = %s,
                banned_at = %s
            WHERE tg_id = %s
            """,
            (reason, now_dt, user_id_str),
        )

    clean_device_id = str(device_id or "").strip()
    if not clean_device_id or clean_device_id.lower() in (
        "none", "null", "undefined"
    ):
        return

    clean_fp = (
        str(fingerprint_hash).strip()
        if fingerprint_hash
        else None
    )

    cur.execute(
        """
        INSERT INTO banned_devices (
            device_id,
            reason,
            banned_at,
            associated_users,
            fingerprint_hash
        )
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (device_id) DO UPDATE SET
            reason = EXCLUDED.reason,
            banned_at = EXCLUDED.banned_at,
            associated_users = CASE
                WHEN %s IS NOT NULL
                THEN banned_devices.associated_users || %s
                ELSE banned_devices.associated_users
            END,
            fingerprint_hash = COALESCE(
                EXCLUDED.fingerprint_hash,
                banned_devices.fingerprint_hash
            )
        """,
        (
            clean_device_id,
            reason,
            now_dt,
            Json([user_id_str] if user_id_str else []),
            clean_fp,
            user_id_str,
            Json([user_id_str] if user_id_str else []),
        ),
    )

    cur.execute(
        """
        INSERT INTO devices (
            device_id,
            is_banned,
            ban_reason,
            banned_at
        )
        VALUES (%s, TRUE, %s, %s)
        ON CONFLICT (device_id) DO UPDATE SET
            is_banned = TRUE,
            ban_reason = EXCLUDED.ban_reason,
            banned_at = EXCLUDED.banned_at
        """,
        (clean_device_id, reason, now_dt),
    )


def ban_user_and_device(
    telegram_id,
    device_id=None,
    reason="تعدد حسابات غير مصرح به",
    fingerprint_hash=None,
):
    """حظر المستخدم والجهاز في transaction واحدة."""
    user_id_str = _sanitize_telegram_id(telegram_id)
    if not user_id_str:
        return False

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                _ban_user_and_device_in_cursor(
                    cur,
                    user_id_str,
                    device_id,
                    reason,
                    fingerprint_hash,
                )
            conn.commit()
            return True

    except Exception as e:
        print(f"❌ خطأ حظر المستخدم/الجهاز: {e}")
        return False


def check_and_bind_device(
    telegram_id,
    device_id,
    fingerprint_hash=None,
):
    """فحص وربط الجهاز بأقل عدد ممكن من الاتصالات والاستعلامات."""
    user_id_str = _sanitize_telegram_id(telegram_id)

    if not user_id_str:
        return {
            "allowed": False,
            "banned": True,
            "reason": "معرف المستخدم غير صالح",
        }

    clean_device_id = str(device_id or "").strip()
    clean_fingerprint = str(fingerprint_hash or "").strip()

    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:

                # فحص الحظر من نفس الاتصال بدلاً من استدعاء get_user()
                cur.execute(
                    """
                    SELECT is_banned
                    FROM users
                    WHERE tg_id = %s
                    """,
                    (user_id_str,),
                )
                user_ban_row = cur.fetchone()

                if user_ban_row and user_ban_row.get("is_banned"):
                    return {
                        "allowed": False,
                        "banned": True,
                        "reason": "حسابك محظور من استخدام التطبيق.",
                    }

                if (
                    not clean_device_id
                    or clean_device_id.lower() in (
                        "none", "null", "undefined",
                        "false", "true"
                    )
                ):
                    return {"allowed": True}

                cur.execute(
                    """
                    SELECT
                        device_id,
                        primary_user_id,
                        users,
                        fingerprint_hash,
                        is_banned,
                        ban_reason
                    FROM banned_devices
                    WHERE device_id = %s
                    LIMIT 1
                    """,
                    (clean_device_id,),
                )
                banned_row = cur.fetchone()

                if banned_row:
                    reason = "محاولة استخدام جهاز محظور مسبقاً"
                    _ban_user_and_device_in_cursor(
                        cur,
                        user_id_str,
                        clean_device_id,
                        reason,
                        clean_fingerprint,
                    )
                    conn.commit()
                    return {
                        "allowed": False,
                        "banned": True,
                        "reason": "تم حظر هذا الجهاز وحسابك نهائياً.",
                    }

                cur.execute(
                    """
                    SELECT
                        device_id,
                        primary_user_id,
                        users,
                        fingerprint_hash,
                        is_banned,
                        ban_reason
                    FROM devices
                    WHERE device_id = %s
                    LIMIT 1
                    """,
                    (clean_device_id,),
                )
                dev_data = cur.fetchone()

                if dev_data:
                    if dev_data.get("is_banned"):
                        reason = dev_data.get(
                            "ban_reason",
                            "جهاز محظور"
                        )
                        _ban_user_and_device_in_cursor(
                            cur,
                            user_id_str,
                            clean_device_id,
                            reason,
                            clean_fingerprint,
                        )
                        conn.commit()
                        return {
                            "allowed": False,
                            "banned": True,
                            "reason": "تم حظر هذا الجهاز وحسابك.",
                        }

                    primary_user_id = str(
                        dev_data.get("primary_user_id") or ""
                    ).strip()

                    assoc_users = dev_data.get("users") or []

                    if isinstance(assoc_users, str):
                        try:
                            assoc_users = json.loads(assoc_users)
                        except Exception:
                            assoc_users = []

                    if (
                        primary_user_id
                        and primary_user_id != user_id_str
                    ):
                        reason_msg = (
                            f"اكتشاف تعدد حسابات على نفس الجهاز "
                            f"({clean_device_id})."
                        )

                        _ban_user_and_device_in_cursor(
                            cur,
                            user_id_str,
                            clean_device_id,
                            reason_msg,
                            clean_fingerprint,
                        )

                        _ban_user_and_device_in_cursor(
                            cur,
                            primary_user_id,
                            clean_device_id,
                            reason_msg,
                            clean_fingerprint,
                        )

                        conn.commit()

                        return {
                            "allowed": False,
                            "banned": True,
                            "reason": "تم حظر حسابك لتعدد الحسابات.",
                        }

                    now_dt = datetime.now(timezone.utc)

                    if user_id_str not in assoc_users:
                        assoc_users.append(user_id_str)

                    cur.execute(
                        """
                        UPDATE devices
                        SET last_seen = %s,
                            users = %s
                        WHERE device_id = %s
                        """,
                        (
                            now_dt,
                            Json(assoc_users),
                            clean_device_id,
                        ),
                    )

                    conn.commit()
                    return {"allowed": True}

                # لا يوجد device_id في الجدول: افحص fingerprint
                if clean_fingerprint:
                    cur.execute(
                        """
                        SELECT
                            device_id,
                            primary_user_id
                        FROM devices
                        WHERE fingerprint_hash = %s
                        LIMIT 5
                        """,
                        (clean_fingerprint,),
                    )

                    fp_matches = cur.fetchall()

                    for match in fp_matches:
                        other_primary = str(
                            match.get("primary_user_id") or ""
                        ).strip()

                        if (
                            other_primary
                            and other_primary != user_id_str
                        ):
                            reason_msg = (
                                f"اكتشاف تطابق بصمة الجهاز "
                                f"({clean_fingerprint})"
                            )

                            _ban_user_and_device_in_cursor(
                                cur,
                                user_id_str,
                                clean_device_id,
                                reason_msg,
                                clean_fingerprint,
                            )

                            _ban_user_and_device_in_cursor(
                                cur,
                                other_primary,
                                match.get("device_id"),
                                reason_msg,
                                clean_fingerprint,
                            )

                            conn.commit()

                            return {
                                "allowed": False,
                                "banned": True,
                                "reason": "تم حظر الحساب بتطابق بصمة الجهاز.",
                            }

                now_dt = datetime.now(timezone.utc)

                cur.execute(
                    """
                    INSERT INTO devices (
                        device_id,
                        primary_user_id,
                        users,
                        fingerprint_hash,
                        created_at,
                        last_seen,
                        is_banned
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, FALSE)
                    ON CONFLICT (device_id) DO NOTHING
                    """,
                    (
                        clean_device_id,
                        user_id_str,
                        Json([user_id_str]),
                        clean_fingerprint
                        if clean_fingerprint
                        else None,
                        now_dt,
                        now_dt,
                    ),
                )

                cur.execute(
                    """
                    UPDATE users
                    SET device_id = %s,
                        fingerprint_hash = %s
                    WHERE tg_id = %s
                    """,
                    (
                        clean_device_id,
                        clean_fingerprint
                        if clean_fingerprint
                        else None,
                        user_id_str,
                    ),
                )

                conn.commit()
                return {"allowed": True}

    except Exception as e:
        print(f"❌ خطأ في فحص الجهاز: {e}")
        # نفس السلوك الآمن القديم: لا تمنع مستخدماً بسبب خطأ DB مؤقت.
        return {"allowed": True}


# =============================================================================
# Core User Operations
# =============================================================================

def get_user(telegram_id):
    """جلب بيانات المستخدم."""
    user_id_str = _sanitize_telegram_id(telegram_id)

    if not user_id_str:
        return None

    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM users WHERE tg_id = %s",
                    (user_id_str,),
                )
                user_row = cur.fetchone()

                if user_row:
                    user_dict = dict(user_row)
                    user_dict["user_id"] = (
                        user_dict.get("user_id")
                        or user_id_str
                    )
                    user_dict["telegram_id"] = (
                        user_dict.get("telegram_id")
                        or user_id_str
                    )
                    return sanitize_firestore_data(user_dict)

                return None

    except Exception as e:
        print(
            f"❌ خطأ قراءة بيانات المستخدم "
            f"{telegram_id}: {e}"
        )
        return None


def init_user(
    telegram_id,
    ref_id=None,
    first_name="لاعب",
):
    """إنشاء المستخدم بأقل عدد ممكن من الاستعلامات."""
    user_id_str = _sanitize_telegram_id(telegram_id)

    if not user_id_str:
        return {}

    clean_first_name = str(
        first_name or "لاعب"
    ).strip()[:50]

    clean_ref = _sanitize_telegram_id(ref_id)
    if clean_ref == user_id_str:
        clean_ref = None

    try:
        now_dt = datetime.now(timezone.utc)

        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO users (
                        tg_id,
                        user_id,
                        telegram_id,
                        first_name,
                        balance,
                        usd_balance,
                        znx_balance,
                        ref_by,
                        referrals_count,
                        created_at,
                        last_active_at,
                        interactions,
                        is_banned,
                        farm_level,
                        storage_level,
                        last_harvest
                    )
                    VALUES (
                        %s, %s, %s, %s,
                        0.0, 0.0, 0.0,
                        %s, 0, %s, %s, 1,
                        FALSE, 1, 1, %s
                    )
                    ON CONFLICT (tg_id) DO NOTHING
                    RETURNING *
                    """,
                    (
                        user_id_str,
                        user_id_str,
                        user_id_str,
                        clean_first_name,
                        clean_ref,
                        now_dt,
                        now_dt,
                        now_dt,
                    ),
                )

                inserted_row = cur.fetchone()

                # إذا تم إنشاء الحساب فعلاً، زد عداد الإحالات.
                if inserted_row and clean_ref:
                    cur.execute(
                        """
                        UPDATE users
                        SET referrals_count = referrals_count + 1
                        WHERE tg_id = %s
                        """,
                        (clean_ref,),
                    )

                if inserted_row:
                    conn.commit()

                    user_dict = dict(inserted_row)
                    user_dict["user_id"] = (
                        user_dict.get("user_id")
                        or user_id_str
                    )
                    user_dict["telegram_id"] = (
                        user_dict.get("telegram_id")
                        or user_id_str
                    )
                    return sanitize_firestore_data(user_dict)

                # الحساب موجود بالفعل.
                cur.execute(
                    """
                    SELECT *
                    FROM users
                    WHERE tg_id = %s
                    """,
                    (user_id_str,),
                )

                existing_row = cur.fetchone()
                conn.commit()

                if existing_row:
                    user_dict = dict(existing_row)
                    user_dict["user_id"] = (
                        user_dict.get("user_id")
                        or user_id_str
                    )
                    user_dict["telegram_id"] = (
                        user_dict.get("telegram_id")
                        or user_id_str
                    )
                    return sanitize_firestore_data(user_dict)

                return {}

    except Exception as e:
        print(
            f"❌ خطأ أثناء إنشاء حساب المستخدم "
            f"{telegram_id}: {e}"
        )
        return {}


def is_user_banned(telegram_id):
    """التحقق من الحظر باستعلام صغير بدلاً من SELECT *."""
    user_id_str = _sanitize_telegram_id(telegram_id)

    if not user_id_str:
        return False

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT is_banned
                    FROM users
                    WHERE tg_id = %s
                    LIMIT 1
                    """,
                    (user_id_str,),
                )
                row = cur.fetchone()
                return bool(row[0]) if row else False

    except Exception as e:
        print(
            f"❌ خطأ التحقق من حظر المستخدم "
            f"{user_id_str}: {e}"
        )
        return False


def update_user(telegram_id, updates_dict):
    """تحديث بيانات المستخدم."""
    user_id_str = _sanitize_telegram_id(telegram_id)

    if not user_id_str or not isinstance(updates_dict, dict):
        return False

    sanitized_updates = {}

    for key, value in updates_dict.items():
        if not isinstance(key, str) or key.startswith("_"):
            continue

        try:
            safe_key = _safe_identifier(key)
        except ValueError:
            continue

        sanitized_updates[safe_key] = value

    if not sanitized_updates:
        return False

    try:
        set_clauses = []
        values = []

        for field, value in sanitized_updates.items():
            set_clauses.append(f"{field} = %s")
            values.append(
                Json(value)
                if isinstance(value, (dict, list))
                else value
            )

        values.append(user_id_str)

        sql = (
            f"UPDATE users "
            f"SET {', '.join(set_clauses)} "
            f"WHERE tg_id = %s"
        )

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, values)
            conn.commit()

        return True

    except Exception as e:
        print(
            f"❌ خطأ تحديث بيانات المستخدم "
            f"{user_id_str}: {e}"
        )
        return False


def update_user_last_active(user_id):
    """تحديث آخر نشاط."""
    user_id_str = _sanitize_telegram_id(user_id)

    if not user_id_str:
        return False

    try:
        now_dt = datetime.now(timezone.utc)

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE users
                    SET last_active_at = %s,
                        interactions = interactions + 1
                    WHERE tg_id = %s
                    """,
                    (now_dt, user_id_str),
                )
            conn.commit()

        return True

    except Exception as e:
        print(
            f"❌ خطأ في تحديث نشاط المستخدم "
            f"{user_id_str}: {e}"
        )
        return False


# =============================================================================
# Atomic Transactions
# =============================================================================

def atomic_update_balance(
    telegram_id,
    amount_change,
    is_usd=False,
):
    """
    تحديث ذري للرصيد في UPDATE واحد فقط.

    هذا أسرع من:
        SELECT ... FOR UPDATE
        ثم UPDATE

    وما زال يمنع السباق (Race Condition) لأن PostgreSQL ينفذ
    UPDATE بشكل ذري.
    """
    user_id_str = _sanitize_telegram_id(telegram_id)

    if not user_id_str:
        return False, "المعرف غير صالح"

    try:
        amount = float(amount_change)

        if math.isnan(amount) or math.isinf(amount):
            return False, "قيمة المبلغ غير صالحة"

    except (ValueError, TypeError):
        return False, "المبلغ يجب أن يكون رقماً صحيحاً أو عشرياً"

    if (
        is_usd is True
        or str(is_usd).lower() in (
            "usd",
            "usd_balance",
        )
    ):
        field_name = "usd_balance"

    elif str(is_usd).lower() in (
        "znx",
        "znx_balance",
    ):
        field_name = "znx_balance"

    else:
        field_name = "balance"

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    UPDATE users
                    SET {field_name} = ROUND(
                        ({field_name} + %s)::numeric,
                        6
                    )::double precision
                    WHERE tg_id = %s
                      AND ({field_name} + %s) >= 0
                    RETURNING {field_name}
                    """,
                    (
                        amount,
                        user_id_str,
                        amount,
                    ),
                )

                row = cur.fetchone()

            if row is None:
                conn.rollback()

                # نفرق بين عدم وجود الحساب وعدم كفاية الرصيد.
                with conn.cursor() as check_cur:
                    check_cur.execute(
                        """
                        SELECT 1
                        FROM users
                        WHERE tg_id = %s
                        LIMIT 1
                        """,
                        (user_id_str,),
                    )
                    exists = check_cur.fetchone()

                if exists:
                    return False, "الرصيد غير كافٍ"

                return False, "المستخدم غير موجود"

            conn.commit()

            new_balance = float(row[0] or 0.0)
            return True, new_balance

    except Exception as e:
        print(
            f"❌ خطأ في معاملة تحديث الرصيد "
            f"{user_id_str}: {e}"
        )
        return False, str(e)


# =============================================================================
# Leaderboard Bridge & Fallback
# =============================================================================

def get_leaderboard_rankings_legacy(limit=50):
    return get_leaderboard_data(limit=limit)


def _fallback_get_leaderboard_data(
    limit=50,
    user_id=None,
):
    """جلب المتصدرين."""
    try:
        safe_limit = max(
            1,
            min(int(limit or 50), 100)
        )

        target_user_id = _sanitize_telegram_id(user_id)

        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT
                        tg_id AS user_id,
                        first_name,
                        balance,
                        usd_balance,
                        znx_balance,
                        farm_level
                    FROM users
                    ORDER BY balance DESC
                    LIMIT %s
                    """,
                    (safe_limit,),
                )

                rows = cur.fetchall()

                leaderboard = []
                rank = 1
                user_rank = None
                user_in_top = False

                for row in rows:
                    u_id = str(
                        row.get("user_id")
                        or ""
                    )

                    user_entry = {
                        "rank": rank,
                        "user_id": u_id,
                        "first_name": str(
                            row.get("first_name")
                            or "لاعب"
                        ),
                        "balance": float(
                            row.get("balance")
                            or 0.0
                        ),
                        "usd_balance": float(
                            row.get("usd_balance")
                            or 0.0
                        ),
                        "znx_balance": float(
                            row.get("znx_balance")
                            or 0.0
                        ),
                        "farm_level": (
                            row.get("farm_level")
                            or 1
                        ),
                    }

                    leaderboard.append(user_entry)

                    if (
                        target_user_id
                        and u_id == target_user_id
                    ):
                        user_rank = rank
                        user_in_top = True

                    rank += 1

                if target_user_id and not user_in_top:
                    cur.execute(
                        """
                        SELECT balance
                        FROM users
                        WHERE tg_id = %s
                        """,
                        (target_user_id,),
                    )

                    target_row = cur.fetchone()

                    if target_row:
                        target_bal = float(
                            target_row.get("balance")
                            or 0.0
                        )

                        cur.execute(
                            """
                            SELECT COUNT(*) AS higher_count
                            FROM users
                            WHERE balance > %s
                            """,
                            (target_bal,),
                        )

                        count_row = cur.fetchone()

                        higher_count = (
                            count_row.get("higher_count")
                            if count_row
                            else 0
                        )

                        user_rank = higher_count + 1

        return {
            "success": True,
            "leaderboard": leaderboard,
            "my_rank": user_rank or "غير مصنف",
        }

    except Exception as e:
        print(
            f"❌ خطأ أثناء جلب قائمة المتصدرين: {e}"
        )

        return {
            "success": False,
            "error": str(e),
            "leaderboard": [],
            "my_rank": "غير مصنف",
        }


def get_leaderboard_data(
    limit=50,
    user_id=None,
):
    if callable(znx_get_leaderboard_data):
        try:
            res = znx_get_leaderboard_data(
                limit=limit,
                user_id=user_id,
            )

            if (
                res
                and isinstance(res, dict)
                and res.get("success", False)
            ):
                return res

        except Exception as e:
            print(
                f"⚠️ تعذر استدعاء المتصدرين عبر الجسر: {e}"
            )

    return _fallback_get_leaderboard_data(
        limit=limit,
        user_id=user_id,
    )


# =============================================================================
# Sub-Modules / Re-exports
# =============================================================================
# لا نغيّر أسماء الوحدات حتى يبقى المشروع متوافقاً.

try:
    from admin_database import *
except Exception as e:
    print(f"⚠️ admin_database: {e}")

try:
    from admin_chat.admin_chat_db import *
except Exception as e:
    print(f"⚠️ admin_chat_db: {e}")

try:
    from farm.farm_db import *
except Exception as e:
    print(f"⚠️ farm_db: {e}")

try:
    from friends.friends_db import *
except Exception as e:
    print(f"⚠️ friends_db: {e}")

try:
    from games.games_db import *
    if "init_all_games_db" in locals():
        # نحافظ على السلوك الحالي كما هو؛ لو بقي الإقلاع بطيئاً
        # بعد هذا الملف، فالخطوة التالية هي فحص init_all_games_db()
        # داخل games/games_db.py.
        init_all_games_db()
except Exception as e:
    print(f"⚠️ games_db: {e}")

try:
    from settings.settings_db import *
except Exception as e:
    print(f"⚠️ settings_db: {e}")

try:
    from shop.shop_db import *
except Exception as e:
    print(f"⚠️ shop_db: {e}")

try:
    from super_admin.super_admin_db import *
except Exception as e:
    print(f"⚠️ super_admin_db: {e}")

try:
    from support.support_db import *
except Exception as e:
    print(f"⚠️ support_db: {e}")

try:
    from tasks.tasks_db import *
except Exception as e:
    print(f"⚠️ tasks_db: {e}")

try:
    from users.users_db import *
except Exception as e:
    print(f"⚠️ users_db: {e}")

try:
    from wallet.wallet_db import *
    from wallet.deposit.deposit_db import *
    from wallet.history.history_db import *
    from wallet.withdraw.withdraw_db import *
    from wallet.exchange.exchange_db import *
except Exception as e:
    print(f"⚠️ wallet modules: {e}")

try:
    from offers.offers_db import *
except Exception as e:
    print(f"⚠️ offers_db: {e}")

try:
    from ads.ads_db import *
except Exception as e:
    print(f"⚠️ ads_db: {e}")
