# -*- coding: utf-8 -*-
"""
بيانات التطبيق الرئيسية مع ربط Supabase (PostgreSQL) عبر Transaction Pooler
نظام الأمان ومنع تعدد الحسابات والأجهزة (Multi-Accounting System)
"""
import json
import os
import math
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urlparse
from contextlib import contextmanager

import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor, Json

# ==================== Supabase / PostgreSQL Connection Pool ====================
db_pool = None

def get_database_url():
    """استخراج وتنظيف رابط DATABASE_URL الخاص بـ Supabase من متغيرات البيئة"""
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise ValueError("❌ لم يتم العثور على المتغير البيئي DATABASE_URL! يرجى التأكد من إضافته في Railway.")
    
    # تحويل postgres:// إلى postgresql:// إذا وُجدت لتتوافق مع psycopg2
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    
    return db_url


def init_db_pool():
    """تهيئة بركة اتصالات خفيفة وسريعة (ThreadedConnectionPool) تعمل بكفاءة مع Transaction Pooler"""
    global db_pool
    if db_pool is None or db_pool.closed:
        try:
            db_url = get_database_url()
            # إعداد البركة لتدعم من 1 إلى 20 اتصال متزامن
            db_pool = pool.ThreadedConnectionPool(
                minconn=1,
                maxconn=20,
                dsn=db_url
            )
            print("✅ تم الاتصال بـ Supabase (Transaction Pooler) وتأسيس Connection Pool بنجاح!")
            _auto_create_tables()
        except Exception as e:
            print(f"❌ خطأ حرِج أثناء التهيئة للاتصال بـ Supabase: {e}")
            raise e
    return db_pool


@contextmanager
def get_db_connection():
    """Context Manager لإدارة أخذ وإعادة الاتصالات لبركة الاتصالات تلقائياً وبأمان"""
    pool_obj = init_db_pool()
    conn = pool_obj.getconn()
    try:
        yield conn
    finally:
        pool_obj.putconn(conn)


def get_db():
    """دالة توافقية مع بقية الموديولات لإعادة الاتصال الحركي"""
    return init_db_pool()


def _auto_create_tables():
    """إنشاء كافة الجداول والفهارس المتقدمة تلقائياً في Supabase عند التشغيل لأول مرة"""
    create_tables_sql = """
    -- 1. جدول المستخدمين
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

    -- 2. جدول الأجهزة المرتبطة
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

    -- 3. جدول الأجهزة المحظورة (القائمة السوداء)
    CREATE TABLE IF NOT EXISTS banned_devices (
        device_id VARCHAR(256) PRIMARY KEY,
        reason TEXT,
        banned_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
        associated_users JSONB DEFAULT '[]'::jsonb,
        fingerprint_hash VARCHAR(256)
    );

    -- تسريع الاستعلامات وعمليات الترتيب باستخدام الفهارس (Indexes)
    CREATE INDEX IF NOT EXISTS idx_users_balance ON users(balance DESC);
    CREATE INDEX IF NOT EXISTS idx_users_ref_by ON users(ref_by);
    CREATE INDEX IF NOT EXISTS idx_devices_fingerprint ON devices(fingerprint_hash);
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(create_tables_sql)
            conn.commit()
            print("⚡ تم التحقق من هيكل الجداول والفهارس وتنفيذ التحديثات تلقائياً في Supabase!")
    except Exception as e:
        print(f"⚠️ خطأ أثناء التحقق من جداول Supabase تلقائياً: {e}")


# ==================== Initial Auto Connection ====================
try:
    init_db_pool()
except Exception as e:
    print(f"⚠️ تنبيه أثناء التهيئة التلقائية لـ Supabase: {e}")


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
    """
    تحويل عناصر البيانات غير القابلة للترميز بـ JSON إلى صيغ نصوص ISO 8601
    لمنع أخطاء 500 Internal Server Error عند إرجاع الاستجابات في Flask.
    """
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
    """
    حظر المستخدم والجهاز وإدراجهما في القائمة السوداء في Supabase لمنع الدخول مستقبلاً.
    """
    user_id_str = _sanitize_telegram_id(telegram_id)
    now_dt = datetime.now(timezone.utc)

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # 1. حظر حساب المستخدم
                if user_id_str:
                    cur.execute("""
                        UPDATE users 
                        SET is_banned = TRUE, ban_reason = %s, banned_at = %s 
                        WHERE tg_id = %s
                    """, (reason, now_dt, user_id_str))
                    print(f"🚫 تم حظر المستخدم {user_id_str} | السبب: {reason}")

                # 2. حظر الجهاز في جدول banned_devices و devices
                if device_id and str(device_id).strip() and str(device_id).lower() not in ('none', 'null', 'undefined'):
                    clean_device_id = str(device_id).strip()
                    clean_fp = str(fingerprint_hash).strip() if fingerprint_hash else None

                    # إضافة/تحديث جدول banned_devices
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

                    # تحديث حالة الجهاز في جدول devices
                    cur.execute("""
                        INSERT INTO devices (device_id, is_banned, ban_reason, banned_at)
                        VALUES (%s, TRUE, %s, %s)
                        ON CONFLICT (device_id) DO UPDATE SET
                            is_banned = TRUE,
                            ban_reason = EXCLUDED.ban_reason,
                            banned_at = EXCLUDED.banned_at
                    """, (clean_device_id, reason, now_dt))

                    print(f"🚫 تم حظر الجهاز {clean_device_id} وإدراجه في banned_devices | السبب: {reason}")
            conn.commit()
            return True
    except Exception as e:
        print(f"❌ خطأ حظر المستخدم/الجهاز {user_id_str}/{device_id}: {e}")
        return False


def check_and_bind_device(telegram_id, device_id, fingerprint_hash=None):
    """
    فحص حظر متعدد الحسابات والأجهزة على Supabase:
    1. التأكد من عدم حظر المستخدم أو الجهاز.
    2. ربط الجهاز بأول حساب يدخل منه (primary_user_id).
    3. إذا حاول حساب مختلف الدخول بنفس الجهاز -> حظر الحسابين والجهاز فوراً.
    """
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
                # أ. فحص ما إذا كان الجهاز في قائمة الحظر
                cur.execute("SELECT * FROM banned_devices WHERE device_id = %s", (clean_device_id,))
                banned_dev = cur.fetchone()
                if banned_dev:
                    ban_user_and_device(user_id_str, clean_device_id, "محاولة استخدام جهاز محظور مسبقاً", clean_fingerprint)
                    return {
                        "allowed": False,
                        "banned": True,
                        "reason": "تم حظر هذا الجهاز وحسابك نهائياً بسبب انتهاك سياسة منع تعدد الحسابات."
                    }

                # ب. فحص سجل الجهاز في جدول devices
                cur.execute("SELECT * FROM devices WHERE device_id = %s", (clean_device_id,))
                dev_data = cur.fetchone()

                if dev_data:
                    if dev_data.get('is_banned'):
                        ban_user_and_device(user_id_str, clean_device_id, dev_data.get('ban_reason', 'جهاز محظور'), clean_fingerprint)
                        return {
                            "allowed": False,
                            "banned": True,
                            "reason": "تم حظر هذا الجهاز وحسابك بسبب انتهاك شروط الاستخدام."
                        }

                    primary_user_id = str(dev_data.get('primary_user_id', '')).strip()
                    assoc_users = dev_data.get('users') or []
                    if isinstance(assoc_users, str):
                        try: assoc_users = json.loads(assoc_users)
                        except Exception: assoc_users = []

                    # اكتشاف تعدد الحسابات
                    if primary_user_id and primary_user_id != user_id_str:
                        reason_msg = f"اكتشاف تعدد حسابات على نفس الجهاز ({clean_device_id}). الحساب الرئيسي: {primary_user_id}، الحساب الجديد: {user_id_str}"
                        print(f"🚨 ALERT: Multi-account detected! Primary: {primary_user_id}, Current: {user_id_str}")

                        ban_user_and_device(user_id_str, clean_device_id, reason_msg, clean_fingerprint)
                        ban_user_and_device(primary_user_id, clean_device_id, reason_msg, clean_fingerprint)
                        for assoc_uid in assoc_users:
                            if assoc_uid and assoc_uid not in (user_id_str, primary_user_id):
                                ban_user_and_device(assoc_uid, clean_device_id, reason_msg, clean_fingerprint)

                        return {
                            "allowed": False,
                            "banned": True,
                            "reason": "تم حظر حسابك وجميع الحسابات المرتبطة بهذا الجهاز فوراً بسبب كشف استخدام أكثر من حساب على نفس الجهاز."
                        }

                    # تحديث سجل الجهاز
                    now_dt = datetime.now(timezone.utc)
                    if user_id_str not in assoc_users:
                        assoc_users.append(user_id_str)

                    cur.execute("""
                        UPDATE devices 
                        SET last_seen = %s, users = %s 
                        WHERE device_id = %s
                    """, (now_dt, Json(assoc_users), clean_device_id))
                    conn.commit()

                    return {"allowed": True}

                else:
                    # ج. جهاز جديد كلياً -> فحص البصمة (fingerprint_hash)
                    if clean_fingerprint:
                        cur.execute("SELECT * FROM devices WHERE fingerprint_hash = %s LIMIT 5", (clean_fingerprint,))
                        fp_matches = cur.fetchall()
                        for match in fp_matches:
                            other_primary = str(match.get('primary_user_id', '')).strip()
                            if other_primary and other_primary != user_id_str:
                                reason_msg = f"اكتشاف تطابق بصمة الجهاز ({clean_fingerprint}) مع حساب آخر ({other_primary})"
                                print(f"🚨 ALERT: Multi-account detected via Fingerprint! Existing: {other_primary}, Current: {user_id_str}")
                                ban_user_and_device(user_id_str, clean_device_id, reason_msg, clean_fingerprint)
                                ban_user_and_device(other_primary, match.get('device_id'), reason_msg, clean_fingerprint)
                                return {
                                    "allowed": False,
                                    "banned": True,
                                    "reason": "تم حظر الحساب والجهاز فوراً بسبب تطابق بصمة الجهاز مع حساب آخر مسجل."
                                }

                    # تسجيل الجهاز الجديد
                    now_dt = datetime.now(timezone.utc)
                    cur.execute("""
                        INSERT INTO devices (device_id, primary_user_id, users, fingerprint_hash, created_at, last_seen, is_banned)
                        VALUES (%s, %s, %s, %s, %s, %s, FALSE)
                    """, (clean_device_id, user_id_str, Json([user_id_str]), clean_fingerprint if clean_fingerprint else None, now_dt, now_dt))

                    cur.execute("""
                        UPDATE users SET device_id = %s, fingerprint_hash = %s WHERE tg_id = %s
                    """, (clean_device_id, clean_fingerprint if clean_fingerprint else None, user_id_str))

                    conn.commit()
                    print(f"✅ تم ربط الجهاز الجديد {clean_device_id} بالحساب الأساسي {user_id_str}")
                    return {"allowed": True}

    except Exception as e:
        print(f"❌ خطأ في فحص الجهاز وتعدد الحسابات للمستخدم {user_id_str}: {e}")
        return {"allowed": True}


# ==================== Core User Operations ====================

def get_user(telegram_id):
    """جلب بيانات المستخدم مباشرة من Supabase مع تحويل البيانات إلى صيغ آمنة"""
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
    """
    إنشاء حساب المستخدم قسرياً في Supabase إن لم يكن موجوداً ومعالجة نظام الإحالات
    """
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

                    # زيادة عداد الإحالة للمُحيل
                    if clean_ref:
                        cur.execute("""
                            UPDATE users SET referrals_count = referrals_count + 1 WHERE tg_id = %s
                        """, (clean_ref,))
                conn.commit()

            print(f"✅ تم إنشاء مستند جديد للمستخدم {user_id_str} بنجاح في Supabase!")
            return get_user(user_id_str) or {}

        return existing_user
    except Exception as e:
        print(f"❌ خطأ أثناء إنشاء/تهيئة حساب المستخدم {telegram_id}: {e}")
        return {}


def is_user_banned(telegram_id):
    """التحقق من حالة حظر المستخدم"""
    user_data = get_user(telegram_id)
    if user_data:
        return user_data.get('is_banned', False)
    return False


def update_user(telegram_id, updates_dict):
    """تحديث بيانات مستند المستخدم مع التحقق من الأمان ودعم حقول PostgreSQL"""
    user_id_str = _sanitize_telegram_id(telegram_id)
    if not user_id_str or not isinstance(updates_dict, dict):
        return False

    sanitized_updates = {}
    for k, v in updates_dict.items():
        if isinstance(k, str) and not k.startswith('_'):
            sanitized_updates[k] = v

    if not sanitized_updates:
        return False

    try:
        set_clauses = []
        values = []

        for field, val in sanitized_updates.items():
            set_clauses.append(f"{field} = %s")
            if isinstance(val, (dict, list)):
                values.append(Json(val))
            else:
                values.append(val)

        values.append(user_id_str)
        sql = f"UPDATE users SET {', '.join(set_clauses)} WHERE tg_id = %s"

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, values)
            conn.commit()
        return True
    except Exception as e:
        print(f"❌ خطأ تحديث مستند المستخدم {user_id_str}: {e}")
        return False


def update_user_last_active(user_id):
    """تحديث وقت آخر نشاط وزيادة عدد التفاعلات بشكل آمن وسريع"""
    user_id_str = _sanitize_telegram_id(user_id)
    if not user_id_str:
        return False

    try:
        now_dt = datetime.now(timezone.utc)
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE users 
                    SET last_active_at = %s, interactions = interactions + 1 
                    WHERE tg_id = %s
                """, (now_dt, user_id_str))
            conn.commit()
        return True
    except Exception as e:
        print(f"❌ خطأ في تحديث نشاط المستخدم {user_id_str}: {e}")
        return False


# ==================== Atomic Transactions (منع التزامن والثغرات المالية) ====================

def atomic_update_balance(telegram_id, amount_change, is_usd=False):
    """
    تحديث رصيد المستخدم معاملاتيًا باستخدام PostgreSQL Transactions وقفل السجل (FOR UPDATE)
    لمنع ثغرات Race Condition والتلاعب بالرصيد.
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

    # مرونة اختيار حقل الرصيد المطلوب
    if is_usd is True or str(is_usd).lower() in ('usd', 'usd_balance'):
        field_name = 'usd_balance'
    elif str(is_usd).lower() in ('znx', 'znx_balance'):
        field_name = 'znx_balance'
    else:
        field_name = 'balance'

    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # 1. قفل السجل المعني داخل المعاملة (Row-level Lock)
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

                # 2. تحديث الرصيد وحفظ المعاملة
                cur.execute(f"UPDATE users SET {field_name} = %s WHERE tg_id = %s", (new_balance, user_id_str))
            conn.commit()
            return True, new_balance

    except Exception as e:
        print(f"❌ خطأ في معاملة تحديث الرصيد للمستخدم {user_id_str}: {e}")
        return False, str(e)


# ==================== Leaderboard Bridge & Fallback System ====================

def get_leaderboard_rankings_legacy(limit=50):
    """🌉 جسر توافقي لأي موديول قديم يستدعي get_leaderboard_rankings_legacy"""
    return get_leaderboard_data(limit=limit)


def _fallback_get_leaderboard_data(limit=50, user_id=None):
    """جلب قائمة المتصدرين مباشرة بأقصى سرعة عبر SQL Query في Supabase"""
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

                # حساب ترتيب المستخدم إذا لم يكن ضمن القائمة الأولى
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
        print(f"❌ خطأ أثناء جلب قائمة المتصدرين من Supabase: {e}")
        return {
            'success': False,
            'error': str(e),
            'leaderboard': [],
            'my_rank': "غير مصنف"
        }


def get_leaderboard_data(limit=50, user_id=None):
    """دالة الجسر (Bridge Pattern) لربط طلبات الترتيب"""
    if callable(znx_get_leaderboard_data):
        try:
            res = znx_get_leaderboard_data(limit=limit, user_id=user_id)
            if res and isinstance(res, dict) and res.get('success', False):
                return res
        except Exception as e:
            print(f"⚠️ تعذر استدعاء المتصدرين عبر الجسر من znx_wallet_db: {e}")

    return _fallback_get_leaderboard_data(limit=limit, user_id=user_id)


# ==================== Sub-Modules Re-exports ====================

# 0. Admin Database Module (أكواد المكافآت والإدارة العامة)
try:
    from admin_database import *
except Exception as e:
    print(f"⚠️ خطأ في تحميل admin_database: {e}")

# 1. Admin Chat Module
try:
    from admin_chat.admin_chat_db import *
except Exception as e:
    print(f"⚠️ خطأ في تحميل admin_chat_db: {e}")

# 2. Farm Module
try:
    from farm.farm_db import *
except Exception as e:
    print(f"⚠️ خطأ في تحميل farm_db: {e}")

# 3. Friends Module
try:
    from friends.friends_db import *
except Exception as e:
    print(f"⚠️ خطأ في تحميل friends_db: {e}")

# 4. Games Module
try:
    from games.games_db import *
    if 'init_all_games_db' in locals():
        init_all_games_db()
except Exception as e:
    print(f"⚠️ خطأ في تحميل games_db: {e}")

# 5. Settings Module
try:
    from settings.settings_db import *
except Exception as e:
    print(f"⚠️ خطأ في تحميل settings_db: {e}")

# 6. Shop Module
try:
    from shop.shop_db import *
except Exception as e:
    print(f"⚠️ خطأ في تحميل shop_db: {e}")

# 7. Super Admin Module
try:
    from super_admin.super_admin_db import *
except Exception as e:
    print(f"⚠️ خطأ في تحميل super_admin_db: {e}")

# 8. Support Module
try:
    from support.support_db import *
except Exception as e:
    print(f"⚠️ خطأ في تحميل support_db: {e}")

# 9. Tasks Module
try:
    from tasks.tasks_db import *
except Exception as e:
    print(f"⚠️ خطأ في تحميل tasks_db: {e}")

# 10. Users Module
try:
    from users.users_db import *
except Exception as e:
    print(f"⚠️ خطأ في تحميل users_db: {e}")

# 11. Wallet Module
try:
    from wallet.wallet_db import *
    from wallet.deposit.deposit_db import *
    from wallet.history.history_db import *
    from wallet.withdraw.withdraw_db import *
    from wallet.exchange.exchange_db import *
except Exception as e:
    print(f"⚠️ خطأ في تحميل wallet_db وموديولاتها الفرعية: {e}")

# 12. Offers, ZNX Wallet & Ads Modules
try:
    from offers.offers_db import *
except Exception:
    pass

try:
    from ads.ads_db import *
except Exception:
    pass
