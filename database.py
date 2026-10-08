# -*- coding: utf-8 -*-
"""
بيانات التطبيق الرئيسية مع ربط Supabase (PostgreSQL) عبر Transaction Pooler
نظام الأمان ومنع تعدد الحسابات والأجهزة (Multi-Accounting System) - النسخة فائقة السرعة
"""
import json
import os
import math
import sys
import time
import threading
from datetime import datetime, timezone
from urllib.parse import urlparse
from contextlib import contextmanager

import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor, Json

# ==================== Supabase / PostgreSQL Connection Pool ====================
db_pool = None
_tables_initialized = False
_init_lock = threading.Lock()

def get_database_url():
    """استخراج وتنظيف رابط DATABASE_URL الخاص بـ Supabase من متغيرات البيئة"""
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise ValueError("❌ لم يتم العثور على المتغير البيئي DATABASE_URL! يرجى التأكد من إضافته في Railway.")
    
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    
    return db_url


def init_db_pool():
    """تهيئة بركة اتصالات خفيفة وسريعة جدًا بدون استعلامات حظر خيط التنفيذ"""
    global db_pool, _tables_initialized
    if db_pool is None or db_pool.closed:
        with _init_lock:
            if db_pool is None or db_pool.closed:
                try:
                    db_url = get_database_url()
                    # إعداد البركة بدون مهلات انتظار أو فحص أولي
                    db_pool = pool.ThreadedConnectionPool(
                        minconn=1,
                        maxconn=20,
                        dsn=db_url,
                        connect_timeout=3,
                        keepalives=1,
                        keepalives_idle=30,
                        keepalives_interval=10,
                        keepalives_count=3
                    )
                    print("✅ تم تأسيس Connection Pool بـ Supabase بنجاح!")
                    
                    # تشغيل إنشاء الجداول والفهارس في الخلفية كـ Daemon Thread حتى لا تعطل الستارت
                    if not _tables_initialized:
                        _tables_initialized = True
                        threading.Thread(target=_async_create_tables, daemon=True).start()

                except Exception as e:
                    print(f"❌ خطأ حرِج أثناء التهيئة للاتصال بـ Supabase: {e}")
                    raise e
    return db_pool


@contextmanager
def get_db_connection():
    """Context Manager متاح مباشرة بدون فحص Ping مسبق لتقليل وقت الاستجابة إلى أقصى حد"""
    pool_obj = init_db_pool()
    conn = None
    try:
        conn = pool_obj.getconn()
        
        # إذا كان الاتصال مقفولاً من الجذر نطلب اتصالاً نظيفاً
        if conn and conn.closed != 0:
            try: pool_obj.putconn(conn, close=True)
            except Exception: pass
            conn = pool_obj.getconn()

        yield conn
    except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
        # عند حدوث خطأ في الاتصال، يتم التخلص منه وتفريغه من البركة
        if conn:
            try: pool_obj.putconn(conn, close=True)
            except Exception: pass
            conn = None
        raise e
    finally:
        if conn and conn.closed == 0:
            try:
                conn.rollback()  # تنظيف المعاملة
            except Exception:
                pass
            pool_obj.putconn(conn)


def get_db():
    """دالة توافقية مع بقية الموديولات لإعادة الاتصال الحركي"""
    return init_db_pool()


def _async_create_tables():
    """إنشاء كافة الجداول والفهارس في الخلفية لمنع تعطيل استجابة المستخدم"""
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

    CREATE INDEX IF NOT EXISTS idx_users_balance ON users(balance DESC);
    CREATE INDEX IF NOT EXISTS idx_users_ref_by ON users(ref_by);
    CREATE INDEX IF NOT EXISTS idx_devices_fingerprint ON devices(fingerprint_hash);
    """
    try:
        pool_obj = init_db_pool()
        conn = pool_obj.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute(create_tables_sql)
            conn.commit()
            print("⚡ [Background] تم التحقق من هيكل الجداول والفهارس بنجاح!")
        finally:
            pool_obj.putconn(conn)
    except Exception as e:
        print(f"⚠️ [Background] تنبيه أثناء التحقق من جداول Supabase: {e}")


def _auto_create_tables():
    """دالة متوافقة للتحقق السريع"""
    _async_create_tables()


# ==================== Safe Import of ZNX Wallet Module ====================
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
    """جلب بيانات محفظة المستخدم من znx_wallet_db أو Fallback من المستخدم الرئيسي"""
    if callable(znx_get_user_data):
        return znx_get_user_data(telegram_id)
    return get_user(telegram_id)


def execute_conversion(telegram_id, amount_zn):
    """تنفيذ عملية تحويل العملات من znx_wallet_db"""
    if callable(znx_execute_conversion):
        return znx_execute_conversion(telegram_id, amount_zn)
    return {"success": False, "message": "الموديول غير متصل حالياً"}


def get_global_stats():
    """جلب الإحصائيات العامة للمحفظة"""
    if callable(znx_get_global_stats):
        return znx_get_global_stats()
    return {"total_users": 0, "total_converted": 0.0}


# ==================== Security & Input Helpers ====================

def _sanitize_telegram_id(telegram_id):
    """تطهير والتحقق من صحة معرف التليجرام لمنع ثغرات Injection"""
    if telegram_id is None:
        return None
    s_id = str(telegram_id).strip()
    if not s_id or s_id.lower() in ("none", "null", "undefined", "false", "true"):
        return None
    if '/' in s_id or '..' in s_id or '\\' in s_id:
        return None
    if len(s_id) > 128:
        return None
    return s_id


def sanitize_firestore_data(data):
    """تحويل عناصر البيانات إلى صيغ نصوص ISO 8601 لمنع أخطاء 500 في Flask"""
    if data is None:
        return None
    if isinstance(data, dict):
        return {k: sanitize_firestore_data(v) for k, v in data.items()}
    elif isinstance(data, (list, tuple, set)):
        return [sanitize_firestore_data(v) for v in data]
    elif isinstance(data, datetime):
        return data.isoformat()
    elif hasattr(data, 'isoformat') and callable(getattr(data, 'isoformat')):
        return data.isoformat()
    elif hasattr(data, '__dict__'):
        return str(data)
    else:
        return data


# ==================== Multi-Accounting & Device Security Engine ====================

def ban_user_and_device(telegram_id, device_id=None, reason="تعدد حسابات غير مصرح به", fingerprint_hash=None):
    """حظر المستخدم والجهاز وإدراجهما في القائمة السوداء"""
    user_id_str = _sanitize_telegram_id(telegram_id)
    now_dt = datetime.now(timezone.utc)

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                if user_id_str:
                    cur.execute("""
                        UPDATE users 
                        SET is_banned = TRUE, ban_reason = %s, banned_at = %s 
                        WHERE tg_id = %s
                    """, (reason, now_dt, user_id_str))

                if device_id and str(device_id).strip() and str(device_id).lower() not in ('none', 'null', 'undefined'):
                    clean_device_id = str(device_id).strip()
                    clean_fp = str(fingerprint_hash).strip() if fingerprint_hash else None

                    cur.execute("""
                        INSERT INTO banned_devices (device_id, reason, banned_at, associated_users, fingerprint_hash)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (device_id) DO UPDATE SET
                            reason = EXCLUDED.reason,
                            banned_at = EXCLUDED.banned_at,
                            associated_users = CASE 
                                WHEN %s IS NOT NULL THEN banned_devices.associated_users || %s
                                ELSE banned_devices.associated_users
                            END,
                            fingerprint_hash = COALESCE(EXCLUDED.fingerprint_hash, banned_devices.fingerprint_hash)
                    """, (
                        clean_device_id, reason, now_dt, Json([user_id_str] if user_id_str else []), clean_fp,
                        user_id_str, Json([user_id_str] if user_id_str else [])
                    ))

                    cur.execute("""
                        INSERT INTO devices (device_id, is_banned, ban_reason, banned_at)
                        VALUES (%s, TRUE, %s, %s)
                        ON CONFLICT (device_id) DO UPDATE SET
                            is_banned = TRUE,
                            ban_reason = EXCLUDED.ban_reason,
                            banned_at = EXCLUDED.banned_at
                    """, (clean_device_id, reason, now_dt))

            conn.commit()
            return True
    except Exception as e:
        print(f"❌ خطأ حظر المستخدم/الجهاز: {e}")
        return False


def check_and_bind_device(telegram_id, device_id, fingerprint_hash=None):
    """فحص وسحب بيانات حظر تعدد الحسابات بسرعة"""
    user_id_str = _sanitize_telegram_id(telegram_id)
    if not user_id_str:
        return {"allowed": False, "banned": True, "reason": "معرف المستخدم غير صالح"}

    clean_device_id = str(device_id or '').strip()
    clean_fingerprint = str(fingerprint_hash or '').strip()

    if not clean_device_id or clean_device_id.lower() in ('none', 'null', 'undefined', 'false', 'true'):
        if is_user_banned(user_id_str):
            return {"allowed": False, "banned": True, "reason": "حسابك محظور من استخدام التطبيق."}
        return {"allowed": True}

    if is_user_banned(user_id_str):
        return {"allowed": False, "banned": True, "reason": "حسابك محظور من استخدام التطبيق."}

    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM banned_devices WHERE device_id = %s", (clean_device_id,))
                if cur.fetchone():
                    ban_user_and_device(user_id_str, clean_device_id, "محاولة استخدام جهاز محظور مسبقاً", clean_fingerprint)
                    return {"allowed": False, "banned": True, "reason": "تم حظر هذا الجهاز وحسابك نهائياً."}

                cur.execute("SELECT * FROM devices WHERE device_id = %s", (clean_device_id,))
                dev_data = cur.fetchone()

                if dev_data:
                    if dev_data.get('is_banned'):
                        ban_user_and_device(user_id_str, clean_device_id, dev_data.get('ban_reason', 'جهاز محظور'), clean_fingerprint)
                        return {"allowed": False, "banned": True, "reason": "تم حظر هذا الجهاز وحسابك."}

                    primary_user_id = str(dev_data.get('primary_user_id', '')).strip()
                    assoc_users = dev_data.get('users') or []
                    if isinstance(assoc_users, str):
                        try: assoc_users = json.loads(assoc_users)
                        except Exception: assoc_users = []

                    if primary_user_id and primary_user_id != user_id_str:
                        reason_msg = f"اكتشاف تعدد حسابات على نفس الجهاز ({clean_device_id})."
                        ban_user_and_device(user_id_str, clean_device_id, reason_msg, clean_fingerprint)
                        ban_user_and_device(primary_user_id, clean_device_id, reason_msg, clean_fingerprint)
                        return {"allowed": False, "banned": True, "reason": "تم حظر حسابك لتعدد الحسابات."}

                    now_dt = datetime.now(timezone.utc)
                    if user_id_str not in assoc_users:
                        assoc_users.append(user_id_str)

                    cur.execute("UPDATE devices SET last_seen = %s, users = %s WHERE device_id = %s", (now_dt, Json(assoc_users), clean_device_id))
                    conn.commit()
                    return {"allowed": True}

                else:
                    if clean_fingerprint:
                        cur.execute("SELECT * FROM devices WHERE fingerprint_hash = %s LIMIT 5", (clean_fingerprint,))
                        fp_matches = cur.fetchall()
                        for match in fp_matches:
                            other_primary = str(match.get('primary_user_id', '')).strip()
                            if other_primary and other_primary != user_id_str:
                                reason_msg = f"اكتشاف تطابق بصمة الجهاز ({clean_fingerprint})"
                                ban_user_and_device(user_id_str, clean_device_id, reason_msg, clean_fingerprint)
                                ban_user_and_device(other_primary, match.get('device_id'), reason_msg, clean_fingerprint)
                                return {"allowed": False, "banned": True, "reason": "تم حظر الحساب بتطابق بصمة الجهاز."}

                    now_dt = datetime.now(timezone.utc)
                    cur.execute("""
                        INSERT INTO devices (device_id, primary_user_id, users, fingerprint_hash, created_at, last_seen, is_banned)
                        VALUES (%s, %s, %s, %s, %s, %s, FALSE)
                    """, (clean_device_id, user_id_str, Json([user_id_str]), clean_fingerprint if clean_fingerprint else None, now_dt, now_dt))

                    cur.execute("UPDATE users SET device_id = %s, fingerprint_hash = %s WHERE tg_id = %s", (clean_device_id, clean_fingerprint if clean_fingerprint else None, user_id_str))

                    conn.commit()
                    return {"allowed": True}

    except Exception as e:
        print(f"❌ خطأ في فحص الجهاز: {e}")
        return {"allowed": True}


# ==================== Core User Operations ====================

def get_user(telegram_id):
    """جلب بيانات المستخدم مباشرة وسريعة من Supabase"""
    user_id_str = _sanitize_telegram_id(telegram_id)
    if not user_id_str:
        return None
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM users WHERE tg_id = %s", (user_id_str,))
                user_row = cur.fetchone()
                if user_row:
                    user_dict = dict(user_row)
                    user_dict['user_id'] = user_dict.get('user_id') or user_id_str
                    user_dict['telegram_id'] = user_dict.get('telegram_id') or user_id_str
                    return sanitize_firestore_data(user_dict)
                return None
    except Exception as e:
        print(f"❌ خطأ قراءة بيانات المستخدم {telegram_id}: {e}")
        return None


def init_user(telegram_id, ref_id=None, first_name="لاعب"):
    """إنشاء حساب المستخدم في Supabase فوراً"""
    user_id_str = _sanitize_telegram_id(telegram_id)
    if not user_id_str:
        return {}

    try:
        clean_first_name = str(first_name or 'لاعب').strip()[:50]
        existing_user = get_user(user_id_str)

        if not existing_user:
            clean_ref = _sanitize_telegram_id(ref_id)
            if clean_ref == user_id_str:
                clean_ref = None

            now_dt = datetime.now(timezone.utc)

            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO users (
                            tg_id, user_id, telegram_id, first_name, balance, usd_balance, znx_balance,
                            ref_by, referrals_count, created_at, last_active_at, interactions,
                            is_banned, farm_level, storage_level, last_harvest
                        ) VALUES (%s, %s, %s, %s, 0.0, 0.0, 0.0, %s, 0, %s, %s, 1, FALSE, 1, 1, %s)
                        ON CONFLICT (tg_id) DO NOTHING
                    """, (user_id_str, user_id_str, user_id_str, clean_first_name, clean_ref, now_dt, now_dt, now_dt))

                    if clean_ref:
                        cur.execute("UPDATE users SET referrals_count = referrals_count + 1 WHERE tg_id = %s", (clean_ref,))
                conn.commit()

            return get_user(user_id_str) or {}

        return existing_user
    except Exception as e:
        print(f"❌ خطأ أثناء إنشاء حساب المستخدم {telegram_id}: {e}")
        return {}


def is_user_banned(telegram_id):
    """التحقق السريع من حالة حظر المستخدم"""
    user_data = get_user(telegram_id)
    if user_data:
        return user_data.get('is_banned', False)
    return False


def update_user(telegram_id, updates_dict):
    """تحديث بيانات مستند المستخدم"""
    user_id_str = _sanitize_telegram_id(telegram_id)
    if not user_id_str or not isinstance(updates_dict, dict):
        return False

    sanitized_updates = {k: v for k, v in updates_dict.items() if isinstance(k, str) and not k.startswith('_')}
    if not sanitized_updates:
        return False

    try:
        set_clauses = []
        values = []

        for field, val in sanitized_updates.items():
            set_clauses.append(f"{field} = %s")
            values.append(Json(val) if isinstance(val, (dict, list)) else val)

        values.append(user_id_str)
        sql = f"UPDATE users SET {', '.join(set_clauses)} WHERE tg_id = %s"

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, values)
            conn.commit()
        return True
    except Exception as e:
        print(f"❌ خطأ تحديث بيانات المستخدم {user_id_str}: {e}")
        return False


def update_user_last_active(user_id):
    """تحديث وقت آخر نشاط بخصائص سريعة للغاية"""
    user_id_str = _sanitize_telegram_id(user_id)
    if not user_id_str:
        return False

    try:
        now_dt = datetime.now(timezone.utc)
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE users SET last_active_at = %s, interactions = interactions + 1 WHERE tg_id = %s", (now_dt, user_id_str))
            conn.commit()
        return True
    except Exception as e:
        print(f"❌ خطأ في تحديث نشاط المستخدم {user_id_str}: {e}")
        return False


# ==================== Atomic Transactions (منع التزامن والثغرات المالية) ====================

def atomic_update_balance(telegram_id, amount_change, is_usd=False):
    """تحديث الرصيد بمعاملة فائقة السرعة مع منع ثغرات السباق (Race Condition)"""
    user_id_str = _sanitize_telegram_id(telegram_id)
    if not user_id_str:
        return False, "المعرف غير صالح"

    try:
        amount = float(amount_change)
        if math.isnan(amount) or math.isinf(amount):
            return False, "قيمة المبلغ غير صالحة"
    except (ValueError, TypeError):
        return False, "المبلغ يجب أن يكون رقماً صحيحاً أو عشرياً"

    if is_usd is True or str(is_usd).lower() in ('usd', 'usd_balance'):
        field_name = 'usd_balance'
    elif str(is_usd).lower() in ('znx', 'znx_balance'):
        field_name = 'znx_balance'
    else:
        field_name = 'balance'

    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(f"SELECT {field_name} FROM users WHERE tg_id = %s FOR UPDATE", (user_id_str,))
                row = cur.fetchone()
                if not row:
                    conn.rollback()
                    return False, "المستخدم غير موجود"

                current_balance = float(row.get(field_name) or 0.0)
                new_balance = round(current_balance + amount, 6)

                if new_balance < 0:
                    conn.rollback()
                    return False, "الرصيد غير كافٍ"

                cur.execute(f"UPDATE users SET {field_name} = %s WHERE tg_id = %s", (new_balance, user_id_str))
            conn.commit()
            return True, new_balance

    except Exception as e:
        print(f"❌ خطأ في معاملة تحديث الرصيد للمستخدم {user_id_str}: {e}")
        return False, str(e)


# ==================== Leaderboard Bridge & Fallback System ====================

def get_leaderboard_rankings_legacy(limit=50):
    return get_leaderboard_data(limit=limit)


def _fallback_get_leaderboard_data(limit=50, user_id=None):
    """جلب المتصدرين مباشرة بأقصى سرعة"""
    try:
        safe_limit = max(1, min(int(limit or 50), 100))
        target_user_id = _sanitize_telegram_id(user_id)

        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT tg_id AS user_id, first_name, balance, usd_balance, znx_balance, farm_level
                    FROM users
                    ORDER BY balance DESC
                    LIMIT %s
                """, (safe_limit,))
                rows = cur.fetchall()

                leaderboard = []
                rank = 1
                user_rank = None
                user_in_top = False

                for row in rows:
                    u_id = str(row.get('user_id'))
                    user_entry = {
                        'rank': rank,
                        'user_id': u_id,
                        'first_name': str(row.get('first_name') or 'لاعب'),
                        'balance': float(row.get('balance') or 0.0),
                        'usd_balance': float(row.get('usd_balance') or 0.0),
                        'znx_balance': float(row.get('znx_balance') or 0.0),
                        'farm_level': row.get('farm_level') or 1
                    }
                    leaderboard.append(user_entry)

                    if target_user_id and u_id == target_user_id:
                        user_rank = rank
                        user_in_top = True

                    rank += 1

                if target_user_id and not user_in_top:
                    cur.execute("SELECT balance FROM users WHERE tg_id = %s", (target_user_id,))
                    target_row = cur.fetchone()
                    if target_row:
                        target_bal = float(target_row.get('balance') or 0.0)
                        cur.execute("SELECT COUNT(*) AS higher_count FROM users WHERE balance > %s", (target_bal,))
                        count_row = cur.fetchone()
                        higher_count = count_row.get('higher_count') if count_row else 0
                        user_rank = higher_count + 1

        return {
            'success': True,
            'leaderboard': leaderboard,
            'my_rank': user_rank or "غير مصنف"
        }
    except Exception as e:
        print(f"❌ خطأ أثناء جلب قائمة المتصدرين: {e}")
        return {
            'success': False,
            'error': str(e),
            'leaderboard': [],
            'my_rank': "غير مصنف"
        }


def get_leaderboard_data(limit=50, user_id=None):
    if callable(znx_get_leaderboard_data):
        try:
            res = znx_get_leaderboard_data(limit=limit, user_id=user_id)
            if res and isinstance(res, dict) and res.get('success', False):
                return res
        except Exception as e:
            print(f"⚠️ تعذر استدعاء المتصدرين عبر الجسر: {e}")

    return _fallback_get_leaderboard_data(limit=limit, user_id=user_id)


# ==================== Sub-Modules Re-exports ====================

try: from admin_database import *
except Exception as e: pass

try: from admin_chat.admin_chat_db import *
except Exception as e: pass

try: from farm.farm_db import *
except Exception as e: pass

try: from friends.friends_db import *
except Exception as e: pass

try: from games.games_db import *
except Exception as e: pass

try: from settings.settings_db import *
except Exception as e: pass

try: from shop.shop_db import *
except Exception as e: pass

try: from super_admin.super_admin_db import *
except Exception as e: pass

try: from support.support_db import *
except Exception as e: pass

try: from tasks.tasks_db import *
except Exception as e: pass

try: from users.users_db import *
except Exception as e: pass

try:
    from wallet.wallet_db import *
    from wallet.deposit.deposit_db import *
    from wallet.history.history_db import *
    from wallet.withdraw.withdraw_db import *
    from wallet.exchange.exchange_db import *
except Exception as e: pass

try: from offers.offers_db import *
except Exception: pass

try: from ads.ads_db import *
except Exception: pass
