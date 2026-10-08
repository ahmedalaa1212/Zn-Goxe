# -*- coding: utf-8 -*-
"""
بيانات التطبيق الرئيسية مع ربط Supabase (PostgreSQL)
نسخة الأداء الأقصى والاستقرار العالي
"""
import json
import os
import math
import sys
import time
import threading
from datetime import datetime, timezone
from contextlib import contextmanager

import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor, Json

# ==================== Supabase / PostgreSQL Connection Pool ====================
db_pool = None
_tables_initialized = False
_init_lock = threading.Lock()

def get_database_url():
    """استخراج وتنظيف رابط DATABASE_URL"""
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise ValueError("❌ لم يتم العثور على المتغير البيئي DATABASE_URL!")
    
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    
    return db_url


def init_db_pool():
    """تهيئة بركة الاتصالات بسعة أكبر وإعدادات شبكة مباشرة"""
    global db_pool, _tables_initialized
    if db_pool is None or db_pool.closed:
        with _init_lock:
            if db_pool is None or db_pool.closed:
                try:
                    db_url = get_database_url()
                    db_pool = pool.ThreadedConnectionPool(
                        minconn=2,
                        maxconn=30,
                        dsn=db_url,
                        connect_timeout=5,
                        keepalives=1,
                        keepalives_idle=30,
                        keepalives_interval=10,
                        keepalives_count=5
                    )
                    print("⚡ [Supabase Pool] تم تأسيس بركة الاتصالات عالية السعة بنجاح!")
                    
                    if not _tables_initialized:
                        _tables_initialized = True
                        threading.Thread(target=_async_create_tables, daemon=True).start()

                except Exception as e:
                    print(f"❌ خطأ حرِج أثناء الاتصال بـ Supabase: {e}")
                    raise e
    return db_pool


@contextmanager
def get_db_connection():
    """Context Manager آمن للتعامل مع اتصالات قاعدة البيانات"""
    pool_obj = init_db_pool()
    conn = pool_obj.getconn()
    is_broken = False
    try:
        conn.autocommit = True
        yield conn
    except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
        is_broken = True
        raise e
    except Exception:
        raise
    finally:
        if conn:
            try:
                pool_obj.putconn(conn, close=is_broken)
            except Exception:
                pass


def get_db():
    return init_db_pool()


def _async_create_tables():
    """إنشاء الهيكل في الخلفية عند بدء التشغيل"""
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
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(create_tables_sql)
    except Exception as e:
        print(f"⚠️ تنبيه الجداول: {e}")


def _auto_create_tables():
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
    if callable(znx_get_user_data):
        return znx_get_user_data(telegram_id)
    return get_user(telegram_id)


def execute_conversion(telegram_id, amount_zn):
    if callable(znx_execute_conversion):
        return znx_execute_conversion(telegram_id, amount_zn)
    return {"success": False, "message": "الموديول غير متصل حالياً"}


def get_global_stats():
    if callable(znx_get_global_stats):
        return znx_get_global_stats()
    return {"total_users": 0, "total_converted": 0.0}


# ==================== Security & Input Helpers ====================

def _sanitize_telegram_id(telegram_id):
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


# ==================== Fast Engine ====================

def fast_login_check(telegram_id, device_id=None, fingerprint_hash=None):
    """
    تسجيل الدخول السريع: تقليل عدد الاستعلامات إلى أدنى حد ممكن
    """
    user_id_str = _sanitize_telegram_id(telegram_id)
    if not user_id_str:
        return {"allowed": False, "reason": "معرف غير صالح", "user": None}

    clean_dev = str(device_id or '').strip()
    if clean_dev.lower() in ('none', 'null', 'undefined', 'false', 'true'):
        clean_dev = ''
    clean_fp = str(fingerprint_hash or '').strip() if fingerprint_hash else None

    now_dt = datetime.now(timezone.utc)

    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # 1. تحديث أو إنشاء المستخدم واسترجاع بياناته بضربة واحدة
                cur.execute("""
                    INSERT INTO users (tg_id, user_id, telegram_id, first_name, created_at, last_active_at, interactions)
                    VALUES (%s, %s, %s, 'لاعب', %s, %s, 1)
                    ON CONFLICT (tg_id) DO UPDATE 
                    SET last_active_at = EXCLUDED.last_active_at, interactions = users.interactions + 1
                    RETURNING *;
                """, (user_id_str, user_id_str, user_id_str, now_dt, now_dt))
                
                user_row = cur.fetchone()

                if user_row and user_row.get('is_banned'):
                    return {
                        "allowed": False, 
                        "reason": user_row.get('ban_reason') or "حسابك محظور.", 
                        "user": sanitize_firestore_data(dict(user_row))
                    }

                if not clean_dev:
                    return {"allowed": True, "user": sanitize_firestore_data(dict(user_row))}

                # 2. فحص الحظر وربط الجهاز في استعلام واحد مدمج
                cur.execute("""
                    SELECT 
                        (SELECT reason FROM banned_devices WHERE device_id = %s) AS ban_reason,
                        (SELECT row_to_json(d) FROM devices d WHERE device_id = %s) AS dev_data;
                """, (clean_dev, clean_dev))
                
                chk = cur.fetchone()
                
                if chk and chk.get('ban_reason'):
                    cur.execute("UPDATE users SET is_banned = TRUE, ban_reason = %s, banned_at = %s WHERE tg_id = %s",
                                ("استخدام جهاز محظور", now_dt, user_id_str))
                    return {"allowed": False, "reason": "تم حظر هذا الجهاز وحسابك.", "user": None}

                dev_data = chk.get('dev_data') if chk else None
                if isinstance(dev_data, str):
                    try: dev_data = json.loads(dev_data)
                    except Exception: dev_data = None

                if dev_data:
                    if dev_data.get('is_banned'):
                        return {"allowed": False, "reason": "الجهاز محظور.", "user": None}

                    primary_user = str(dev_data.get('primary_user_id', '')).strip()
                    if primary_user and primary_user != user_id_str:
                        reason_msg = f"تعدد حسابات على الجهاز ({clean_dev})"
                        cur.execute("UPDATE users SET is_banned = TRUE, ban_reason = %s, banned_at = %s WHERE tg_id IN (%s, %s)",
                                    (reason_msg, now_dt, user_id_str, primary_user))
                        cur.execute("""
                            INSERT INTO banned_devices (device_id, reason, banned_at, associated_users)
                            VALUES (%s, %s, %s, %s) ON CONFLICT (device_id) DO NOTHING;
                        """, (clean_dev, reason_msg, now_dt, Json([user_id_str, primary_user])))
                        return {"allowed": False, "reason": "تم حظر الحساب لتعدد الحسابات.", "user": None}

                    assoc_users = dev_data.get('users') or []
                    if isinstance(assoc_users, str):
                        try: assoc_users = json.loads(assoc_users)
                        except Exception: assoc_users = []
                    if user_id_str not in assoc_users:
                        assoc_users.append(user_id_str)

                    cur.execute("UPDATE devices SET last_seen = %s, users = %s WHERE device_id = %s", (now_dt, Json(assoc_users), clean_dev))
                else:
                    cur.execute("""
                        INSERT INTO devices (device_id, primary_user_id, users, fingerprint_hash, created_at, last_seen, is_banned)
                        VALUES (%s, %s, %s, %s, %s, %s, FALSE) ON CONFLICT (device_id) DO NOTHING;
                    """, (clean_dev, user_id_str, Json([user_id_str]), clean_fp, now_dt, now_dt))
                    cur.execute("UPDATE users SET device_id = %s, fingerprint_hash = %s WHERE tg_id = %s", (clean_dev, clean_fp, user_id_str))

                return {"allowed": True, "user": sanitize_firestore_data(dict(user_row))}

    except Exception as e:
        print(f"❌ خطأ تسجيل الدخول: {e}")
        user_data = get_user(user_id_str)
        return {"allowed": True, "user": user_data}


def check_and_bind_device(telegram_id, device_id, fingerprint_hash=None):
    res = fast_login_check(telegram_id, device_id, fingerprint_hash)
    return {"allowed": res["allowed"], "banned": not res["allowed"], "reason": res.get("reason", "")}


def ban_user_and_device(telegram_id, device_id=None, reason="تعدد حسابات غير مصرح به", fingerprint_hash=None):
    user_id_str = _sanitize_telegram_id(telegram_id)
    now_dt = datetime.now(timezone.utc)

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                if user_id_str:
                    cur.execute("UPDATE users SET is_banned = TRUE, ban_reason = %s, banned_at = %s WHERE tg_id = %s", (reason, now_dt, user_id_str))

                if device_id and str(device_id).strip() and str(device_id).lower() not in ('none', 'null', 'undefined'):
                    clean_device_id = str(device_id).strip()
                    cur.execute("""
                        INSERT INTO banned_devices (device_id, reason, banned_at, associated_users, fingerprint_hash)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (device_id) DO UPDATE SET
                            reason = EXCLUDED.reason,
                            banned_at = EXCLUDED.banned_at;
                    """, (clean_device_id, reason, now_dt, Json([user_id_str] if user_id_str else []), fingerprint_hash))

            return True
    except Exception as e:
        print(f"❌ خطأ حظر: {e}")
        return False


def get_user(telegram_id):
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
        print(f"❌ خطأ جلب المستخدم: {e}")
        return None


def init_user(telegram_id, ref_id=None, first_name="لاعب"):
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
                        ON CONFLICT (tg_id) DO NOTHING;
                    """, (user_id_str, user_id_str, user_id_str, clean_first_name, clean_ref, now_dt, now_dt, now_dt))

                    if clean_ref:
                        cur.execute("UPDATE users SET referrals_count = referrals_count + 1 WHERE tg_id = %s", (clean_ref,))

            return get_user(user_id_str) or {}

        return existing_user
    except Exception as e:
        print(f"❌ خطأ إنشاء المستخدم: {e}")
        return {}


def is_user_banned(telegram_id):
    user_id_str = _sanitize_telegram_id(telegram_id)
    if not user_id_str:
        return False
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT is_banned FROM users WHERE tg_id = %s", (user_id_str,))
                row = cur.fetchone()
                return bool(row[0]) if row else False
    except Exception:
        return False


def update_user(telegram_id, updates_dict):
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
        return True
    except Exception as e:
        print(f"❌ خطأ تحديث البيانات: {e}")
        return False


def update_user_last_active(user_id):
    user_id_str = _sanitize_telegram_id(user_id)
    if not user_id_str:
        return False

    try:
        now_dt = datetime.now(timezone.utc)
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE users SET last_active_at = %s, interactions = interactions + 1 WHERE tg_id = %s", (now_dt, user_id_str))
        return True
    except Exception:
        return False


# ==================== Atomic Transactions ====================

def atomic_update_balance(telegram_id, amount_change, is_usd=False):
    user_id_str = _sanitize_telegram_id(telegram_id)
    if not user_id_str:
        return False, "المعرف غير صالح"

    try:
        amount = float(amount_change)
        if math.isnan(amount) or math.isinf(amount):
            return False, "قيمة غير صالحة"
    except (ValueError, TypeError):
        return False, "المبلغ يجب أن يكون رقماً"

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
                    return False, "المستخدم غير موجود"

                current_balance = float(row.get(field_name) or 0.0)
                new_balance = round(current_balance + amount, 6)

                if new_balance < 0:
                    return False, "الرصيد غير كافٍ"

                cur.execute(f"UPDATE users SET {field_name} = %s WHERE tg_id = %s", (new_balance, user_id_str))
            return True, new_balance

    except Exception as e:
        return False, str(e)


# ==================== Leaderboard Bridge & Fallback System ====================

def get_leaderboard_rankings_legacy(limit=50):
    return get_leaderboard_data(limit=limit)


def _fallback_get_leaderboard_data(limit=50, user_id=None):
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
        except Exception:
            pass

    return _fallback_get_leaderboard_data(limit=limit, user_id=user_id)


# التسخين المسبق لـ Connection Pool
try:
    threading.Thread(target=init_db_pool, daemon=True).start()
except Exception:
    pass

# ==================== Sub-Modules Re-exports ====================

try: from admin_database import *
except Exception: pass
try: from admin_chat.admin_chat_db import *
except Exception: pass
try: from farm.farm_db import *
except Exception: pass
try: from friends.friends_db import *
except Exception: pass
try: from games.games_db import *
except Exception: pass
try: from settings.settings_db import *
except Exception: pass
try: from shop.shop_db import *
except Exception: pass
try: from super_admin.super_admin_db import *
except Exception: pass
try: from support.support_db import *
except Exception: pass
try: from tasks.tasks_db import *
except Exception: pass
try: from users.users_db import *
except Exception: pass
try:
    from wallet.wallet_db import *
    from wallet.deposit.deposit_db import *
    from wallet.history.history_db import *
    from wallet.withdraw.withdraw_db import *
    from wallet.exchange.exchange_db import *
except Exception: pass
try: from offers.offers_db import *
except Exception: pass
try: from ads.ads_db import *
except Exception: pass
