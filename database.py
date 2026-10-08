# -*- coding: utf-8 -*-
"""
بيانات التطبيق الرئيسية - الربط التلقائي بقاعدة بيانات Supabase PostgreSQL
نظام الأمان ومنع تعدد الحسابات والأجهزة (Multi-Accounting System)
"""
import json
import os
import math
import sys
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import ThreadedConnectionPool
from contextlib import contextmanager

# ==================== Supabase / PostgreSQL Core Engine ====================

DATABASE_URL = os.environ.get("DATABASE_URL")

# إنشاء مجمع اتصالات دائم (Connection Pool) لمنع فتح وإغلاق TCP Connection في كل طلب
db_pool = None

def init_connection_pool():
    global db_pool
    if DATABASE_URL and db_pool is None:
        try:
            # minconn: عدد الاتصالات المفتوحة دائمًا، maxconn: أقصى عدد اتصالات متزامنة
            db_pool = ThreadedConnectionPool(minconn=2, maxconn=20, dsn=DATABASE_URL)
            print("⚡ تم تشغيل مجمع اتصالات Supabase (Connection Pool) بنجاح!")
        except Exception as e:
            print(f"❌ خطأ في إنشاء Connection Pool: {e}")

# تشغيل المجمع فور استيراد الملف
init_connection_pool()

@contextmanager
def get_db_cursor():
    """مدير سياق يسحب اتصالاً جاهزاً من المجمع ويعيده فوراً لتوفير وقت الاتصال الشبكي"""
    conn = None
    cursor = None
    if db_pool:
        try:
            conn = db_pool.getconn()
        except Exception:
            conn = None

    if not conn:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        yield conn, cursor
    except Exception as e:
        if conn:
            conn.rollback()
        raise e
    finally:
        if cursor:
            cursor.close()
        if db_pool and conn:
            db_pool.putconn(conn)
        elif conn:
            conn.close()

def get_connection():
    """دالة توافقية مع الملفات القديمة التي تطلب اتصال مباشر"""
    if db_pool:
        try:
            return db_pool.getconn()
        except Exception:
            pass
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)


class SupabaseDBProxy:
    """كائن توافقي لمنع أخطاء AttributeError في الملفات القديمة التي تبحث عن db"""
    def collection(self, *args, **kwargs):
        return self
    def doc(self, *args, **kwargs):
        return self
    def get(self, *args, **kwargs):
        return None
    def set(self, *args, **kwargs):
        return None
    def update(self, *args, **kwargs):
        return None

db = SupabaseDBProxy()

def initialize_firebase(*args, **kwargs):
    """دالة توافقية لمنع كسر استدعاءات Firebase القديمة"""
    print("ℹ️ نظام قاعدة البيانات يعمل حالياً عبر Supabase PostgreSQL.")
    return True


def init_db():
    """إنشاء الهيكل والجداول والفهارس تلقائياً في Supabase فور تشغيل السيرفر"""
    if not DATABASE_URL:
        print("⚠️ DATABASE_URL غير موجود في متغيرات البيئة!")
        return

    try:
        with get_db_cursor() as (conn, cursor):
            # 1. جدول المستخدمين (users)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id VARCHAR(128) PRIMARY KEY,
                    telegram_id VARCHAR(128),
                    first_name VARCHAR(255) DEFAULT 'لاعب',
                    balance NUMERIC(18, 8) DEFAULT 0.0,
                    usd_balance NUMERIC(18, 8) DEFAULT 0.0,
                    znx_balance NUMERIC(18, 8) DEFAULT 0.0,
                    ref_by VARCHAR(128),
                    referrals_count INT DEFAULT 0,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    last_active_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    interactions INT DEFAULT 1,
                    last_withdraw_date TIMESTAMP WITH TIME ZONE,
                    withdraw_count INT DEFAULT 0,
                    is_banned BOOLEAN DEFAULT FALSE,
                    ban_reason TEXT,
                    banned_at TIMESTAMP WITH TIME ZONE,
                    farm_level INT DEFAULT 1,
                    storage_level INT DEFAULT 1,
                    last_harvest TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    device_id VARCHAR(255),
                    fingerprint_hash VARCHAR(255)
                );
            """)

            # 2. جدول الأجهزة المسجلة (devices)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS devices (
                    device_id VARCHAR(255) PRIMARY KEY,
                    primary_user_id VARCHAR(128),
                    users TEXT[] DEFAULT '{}',
                    fingerprint_hash VARCHAR(255),
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    last_seen TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    is_banned BOOLEAN DEFAULT FALSE,
                    ban_reason TEXT,
                    banned_at TIMESTAMP WITH TIME ZONE
                );
            """)

            # 3. جدول الأجهزة المحظورة (banned_devices)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS banned_devices (
                    device_id VARCHAR(255) PRIMARY KEY,
                    reason TEXT,
                    banned_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    associated_users TEXT[] DEFAULT '{}',
                    fingerprint_hash VARCHAR(255)
                );
            """)

            # 4. إضافة فهارس تسريع الاستعلامات (Indexes)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_balance ON users(balance DESC);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_is_banned ON users(is_banned);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_devices_device_id ON devices(device_id);")

            conn.commit()
            print("✅ تم الاتصال بـ Supabase وإنشاء/فحص جميع الجداول والفهارس بنجاح!")
    except Exception as e:
        print(f"❌ خطأ أثناء إنشاء جداول Supabase: {e}")


# تشغيل الفحص والتأسيس التلقائي للجداول عند استيراد الملف
try:
    init_db()
except Exception as e:
    print(f"⚠️ تنبيه أثناء التهيئة التلقائية لقاعدة البيانات: {e}")


def get_db():
    """دالة توافقية لإرجاع الاتصال لقاعدة البيانات"""
    try:
        return get_connection()
    except Exception as e:
        print(f"❌ خطأ في الحصول على اتصال قاعدة البيانات: {e}")
        return None


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
    """جلب بيانات محفظة المستخدم"""
    if callable(znx_get_user_data):
        return znx_get_user_data(telegram_id)
    return get_user(telegram_id)


def execute_conversion(telegram_id, amount_zn):
    """تنفيذ عملية تحويل العملات"""
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
    """تطهير والتحقق من صحة معرف التليجرام"""
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
    """تحويل قيم Datetime والأحجام المعقدة إلى صيغة JSON آمنة"""
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
    else:
        return data


# ==================== Multi-Accounting & Device Security Engine ====================

def ban_user_and_device(telegram_id, device_id=None, reason="تعدد حسابات غير مصرح به", fingerprint_hash=None):
    """حظر المستخدم والجهاز وإدراجهما في القائمة السوداء"""
    user_id_str = _sanitize_telegram_id(telegram_id)

    try:
        with get_db_cursor() as (conn, cursor):
            # 1. حظر المستخدم
            if user_id_str:
                cursor.execute("""
                    UPDATE users 
                    SET is_banned = TRUE, ban_reason = %s, banned_at = CURRENT_TIMESTAMP
                    WHERE user_id = %s;
                """, (reason, user_id_str))

            # 2. حظر الجهاز
            if device_id and str(device_id).strip() and str(device_id).lower() not in ('none', 'null', 'undefined'):
                clean_device_id = str(device_id).strip()
                clean_fp = str(fingerprint_hash).strip() if fingerprint_hash else None

                cursor.execute("""
                    INSERT INTO banned_devices (device_id, reason, banned_at, associated_users, fingerprint_hash)
                    VALUES (%s, %s, CURRENT_TIMESTAMP, ARRAY[%s]::TEXT[], %s)
                    ON CONFLICT (device_id) DO UPDATE 
                    SET reason = EXCLUDED.reason,
                        banned_at = CURRENT_TIMESTAMP,
                        associated_users = ARRAY_CAT(banned_devices.associated_users, EXCLUDED.associated_users),
                        fingerprint_hash = COALESCE(EXCLUDED.fingerprint_hash, banned_devices.fingerprint_hash);
                """, (clean_device_id, reason, user_id_str or '', clean_fp))

                cursor.execute("""
                    UPDATE devices
                    SET is_banned = TRUE, ban_reason = %s, banned_at = CURRENT_TIMESTAMP
                    WHERE device_id = %s;
                """, (reason, clean_device_id))

            conn.commit()
            print(f"🚫 تم حظر المستخدم {user_id_str} والجهاز {device_id} بنجاح في Supabase!")
            return True
    except Exception as e:
        print(f"❌ خطأ حظر المستخدم/الجهاز في Supabase: {e}")
        return False


def check_and_bind_device(telegram_id, device_id, fingerprint_hash=None):
    """فحص حظر متعدد الحسابات والأجهزة وربط الجهاز بالحساب الأول"""
    user_id_str = _sanitize_telegram_id(telegram_id)
    if not user_id_str:
        return {"allowed": False, "banned": True, "reason": "معرف المستخدم غير صالح"}

    clean_device_id = str(device_id or '').strip()
    clean_fingerprint = str(fingerprint_hash or '').strip()

    if is_user_banned(user_id_str):
        return {"allowed": False, "banned": True, "reason": "حسابك محظور من استخدام التطبيق."}

    if not clean_device_id or clean_device_id.lower() in ('none', 'null', 'undefined', 'false', 'true'):
        return {"allowed": True}

    try:
        with get_db_cursor() as (conn, cursor):
            cursor.execute("SELECT * FROM banned_devices WHERE device_id = %s;", (clean_device_id,))
            banned_dev = cursor.fetchone()
            if banned_dev:
                ban_user_and_device(user_id_str, clean_device_id, "محاولة استخدام جهاز محظور مسبقاً", clean_fingerprint)
                return {
                    "allowed": False,
                    "banned": True,
                    "reason": "تم حظر هذا الجهاز وحسابك نهائياً بسبب انتهاك سياسة منع تعدد الحسابات."
                }

            cursor.execute("SELECT * FROM devices WHERE device_id = %s;", (clean_device_id,))
            dev_data = cursor.fetchone()

            if dev_data:
                if dev_data.get('is_banned', False):
                    ban_user_and_device(user_id_str, clean_device_id, dev_data.get('ban_reason', 'جهاز محظور'), clean_fingerprint)
                    return {
                        "allowed": False,
                        "banned": True,
                        "reason": "تم حظر هذا الجهاز وحسابك بسبب انتهاك شروط الاستخدام."
                    }

                primary_user_id = str(dev_data.get('primary_user_id') or '').strip()
                associated_users = dev_data.get('users') or []

                if primary_user_id and primary_user_id != user_id_str:
                    reason_msg = f"اكتشاف تعدد حسابات على الجهاز ({clean_device_id}). الأساسي: {primary_user_id}، الجديد: {user_id_str}"
                    ban_user_and_device(user_id_str, clean_device_id, reason_msg, clean_fingerprint)
                    ban_user_and_device(primary_user_id, clean_device_id, reason_msg, clean_fingerprint)
                    for assoc_uid in associated_users:
                        if assoc_uid and assoc_uid not in (user_id_str, primary_user_id):
                            ban_user_and_device(assoc_uid, clean_device_id, reason_msg, clean_fingerprint)

                    return {
                        "allowed": False,
                        "banned": True,
                        "reason": "تم حظر حسابك وجميع الحسابات المرتبطة بهذا الجهاز فوراً بسبب كشف استخدام أكثر من حساب."
                    }

                cursor.execute("""
                    UPDATE devices
                    SET last_seen = CURRENT_TIMESTAMP,
                        users = ARRAY_APPEND(ARRAY_REMOVE(users, %s), %s)
                    WHERE device_id = %s;
                """, (user_id_str, user_id_str, clean_device_id))
                conn.commit()
                return {"allowed": True}

            else:
                cursor.execute("""
                    INSERT INTO devices (device_id, primary_user_id, users, fingerprint_hash, created_at, last_seen, is_banned)
                    VALUES (%s, %s, ARRAY[%s]::TEXT[], %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, FALSE);
                """, (clean_device_id, user_id_str, user_id_str, clean_fingerprint or None))

                cursor.execute("""
                    UPDATE users
                    SET device_id = %s, fingerprint_hash = %s
                    WHERE user_id = %s;
                """, (clean_device_id, clean_fingerprint or None, user_id_str))

                conn.commit()
                print(f"✅ تم ربط الجهاز الجديد {clean_device_id} بالحساب {user_id_str}")
                return {"allowed": True}

    except Exception as e:
        print(f"❌ خطأ فحص الجهاز وتعدد الحسابات في Supabase: {e}")
        return {"allowed": True}


# ==================== Core User Operations ====================

def get_user(telegram_id):
    """جلب بيانات المستخدم مباشرة وسريعة عبر المجمع"""
    user_id_str = _sanitize_telegram_id(telegram_id)
    if not user_id_str:
        return None
    try:
        with get_db_cursor() as (conn, cursor):
            cursor.execute("SELECT * FROM users WHERE user_id = %s;", (user_id_str,))
            row = cursor.fetchone()
            if row:
                return sanitize_firestore_data(dict(row))
            return None
    except Exception as e:
        print(f"❌ خطأ قراءة بيانات المستخدم {telegram_id} من Supabase: {e}")
        return None


def init_user(telegram_id, ref_id=None, first_name="لاعب"):
    """إنشاء مستند المستخدم بسرعة فائقة في استعلام واحد متكامل"""
    user_id_str = _sanitize_telegram_id(telegram_id)
    if not user_id_str:
        return {}

    try:
        clean_first_name = str(first_name or 'لاعب').strip()[:50]
        clean_ref = _sanitize_telegram_id(ref_id)
        if clean_ref == user_id_str:
            clean_ref = None

        with get_db_cursor() as (conn, cursor):
            # إدراج أو تحديث نشاط المستخدم مع إرجاع البيانات فوراً (RETURNING *)
            cursor.execute("""
                INSERT INTO users (
                    user_id, telegram_id, first_name, balance, usd_balance, znx_balance,
                    ref_by, referrals_count, created_at, last_active_at, interactions,
                    is_banned, farm_level, storage_level, last_harvest
                ) VALUES (
                    %s, %s, %s, 0.0, 0.0, 0.0,
                    %s, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1,
                    FALSE, 1, 1, CURRENT_TIMESTAMP
                )
                ON CONFLICT (user_id) DO UPDATE 
                SET last_active_at = CURRENT_TIMESTAMP
                RETURNING *;
            """, (user_id_str, user_id_str, clean_first_name, clean_ref))

            row = cursor.fetchone()
            user_data = dict(row) if row else {}

            # زيادة عداد الإحالة فقط عند الإنشاء الجديد أول مرة
            if clean_ref and row and row.get('referrals_count', 0) == 0:
                cursor.execute("""
                    UPDATE users
                    SET referrals_count = referrals_count + 1
                    WHERE user_id = %s;
                """, (clean_ref,))

            conn.commit()
            return sanitize_firestore_data(user_data)

    except Exception as e:
        print(f"❌ خطأ إنشاء/تهيئة حساب المستخدم {telegram_id} في Supabase: {e}")
        return get_user(user_id_str) or {}


def is_user_banned(telegram_id):
    """التحقق من حالة حظر المستخدم"""
    user_data = get_user(telegram_id)
    if user_data:
        return user_data.get('is_banned', False)
    return False


def update_user(telegram_id, updates_dict):
    """تحديث بيانات مستند المستخدم في Supabase"""
    user_id_str = _sanitize_telegram_id(telegram_id)
    if not user_id_str or not isinstance(updates_dict, dict):
        return False

    sanitized_updates = {k: v for k, v in updates_dict.items() if isinstance(k, str) and not k.startswith('_')}
    if not sanitized_updates:
        return False

    try:
        set_clauses = []
        values = []
        for k, v in sanitized_updates.items():
            set_clauses.append(f"{k} = %s")
            values.append(v)

        values.append(user_id_str)
        sql_query = f"UPDATE users SET {', '.join(set_clauses)} WHERE user_id = %s;"

        with get_db_cursor() as (conn, cursor):
            cursor.execute(sql_query, tuple(values))
            conn.commit()
            return True
    except Exception as e:
        print(f"❌ خطأ تحديث مستند المستخدم {user_id_str} في Supabase: {e}")
        return False


def update_user_last_active(user_id):
    """تحديث وقت آخر نشاط للمستخدم"""
    user_id_str = _sanitize_telegram_id(user_id)
    if not user_id_str:
        return False

    try:
        with get_db_cursor() as (conn, cursor):
            cursor.execute("""
                UPDATE users
                SET last_active_at = CURRENT_TIMESTAMP,
                    interactions = interactions + 1
                WHERE user_id = %s;
            """, (user_id_str,))
            conn.commit()
            return True
    except Exception as e:
        print(f"❌ خطأ تحديث نشاط المستخدم {user_id_str} في Supabase: {e}")
        return False


# ==================== Atomic Transactions ====================

def atomic_update_balance(telegram_id, amount_change, is_usd=False):
    """تحديث رصيد المستخدم بشكل آمن ومعاملي لمنع التزامن والتلاعب"""
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
        with get_db_cursor() as (conn, cursor):
            sql = f"""
                UPDATE users
                SET {field_name} = {field_name} + %s
                WHERE user_id = %s AND ({field_name} + %s) >= 0
                RETURNING {field_name};
            """
            cursor.execute(sql, (amount, user_id_str, amount))
            row = cursor.fetchone()

            if row:
                new_balance = float(row[field_name])
                conn.commit()
                return True, new_balance
            else:
                conn.rollback()
                return False, "الرصيد غير كافٍ أو المستخدم غير موجود"

    except Exception as e:
        print(f"❌ خطأ في معاملة تحديث الرصيد للمستخدم {user_id_str} في Supabase: {e}")
        return False, str(e)


# ==================== Leaderboard Bridge & Fallback System ====================

def get_leaderboard_rankings_legacy(limit=50):
    return get_leaderboard_data(limit=limit)


def _fallback_get_leaderboard_data(limit=50, user_id=None):
    """جلب قائمة المتصدرين مباشرة من Supabase"""
    try:
        with get_db_cursor() as (conn, cursor):
            safe_limit = max(1, min(int(limit or 50), 100))

            cursor.execute("""
                SELECT user_id, first_name, balance, usd_balance, znx_balance, farm_level
                FROM users
                WHERE is_banned = FALSE
                ORDER BY balance DESC
                LIMIT %s;
            """, (safe_limit,))

            rows = cursor.fetchall()

            leaderboard = []
            rank = 1
            user_rank = None
            target_user_id = _sanitize_telegram_id(user_id)

            for row in rows:
                u_id = str(row['user_id'])
                leaderboard.append({
                    'rank': rank,
                    'user_id': u_id,
                    'first_name': str(row.get('first_name', 'لاعب')),
                    'balance': float(row.get('balance', 0.0)),
                    'usd_balance': float(row.get('usd_balance', 0.0)),
                    'znx_balance': float(row.get('znx_balance', 0.0)),
                    'farm_level': row.get('farm_level', 1)
                })
                if target_user_id and u_id == target_user_id:
                    user_rank = rank
                rank += 1

            if target_user_id and not user_rank:
                cursor.execute("""
                    SELECT COUNT(*) as higher_count
                    FROM users
                    WHERE balance > (SELECT COALESCE(balance, 0) FROM users WHERE user_id = %s)
                      AND is_banned = FALSE;
                """, (target_user_id,))
                res = cursor.fetchone()
                if res:
                    user_rank = res['higher_count'] + 1

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
    if callable(znx_get_leaderboard_data):
        try:
            res = znx_get_leaderboard_data(limit=limit, user_id=user_id)
            if res and isinstance(res, dict) and res.get('success', False):
                return res
        except Exception as e:
            print(f"⚠️ تعذر استدعاء المتصدرين عبر الجسر: {e}")

    return _fallback_get_leaderboard_data(limit=limit, user_id=user_id)


# ==================== Sub-Modules Re-exports ====================

try:
    from admin_database import *
except Exception as e:
    print(f"⚠️ خطأ في تحميل admin_database: {e}")

try:
    from admin_chat.admin_chat_db import *
except Exception as e:
    print(f"⚠️ خطأ في تحميل admin_chat_db: {e}")

try:
    from farm.farm_db import *
except Exception as e:
    print(f"⚠️ خطأ في تحميل farm_db: {e}")

try:
    from friends.friends_db import *
except Exception as e:
    print(f"⚠️ خطأ في تحميل friends_db: {e}")

try:
    from games.games_db import *
    if 'init_all_games_db' in locals():
        init_all_games_db()
except Exception as e:
    print(f"⚠️ خطأ في تحميل games_db: {e}")

try:
    from settings.settings_db import *
except Exception as e:
    print(f"⚠️ خطأ في تحميل settings_db: {e}")

try:
    from shop.shop_db import *
except Exception as e:
    print(f"⚠️ خطأ في تحميل shop_db: {e}")

try:
    from super_admin.super_admin_db import *
except Exception as e:
    print(f"⚠️ خطأ في تحميل super_admin_db: {e}")

try:
    from support.support_db import *
except Exception as e:
    print(f"⚠️ خطأ في تحميل support_db: {e}")

try:
    from tasks.tasks_db import *
except Exception as e:
    print(f"⚠️ خطأ في تحميل tasks_db: {e}")

try:
    from users.users_db import *
except Exception as e:
    print(f"⚠️ خطأ في تحميل users_db: {e}")

try:
    from wallet.wallet_db import *
    from wallet.deposit.deposit_db import *
    from wallet.history.history_db import *
    from wallet.withdraw.withdraw_db import *
    from wallet.exchange.exchange_db import *
except Exception as e:
    print(f"⚠️ خطأ في تحميل wallet_db وموديولاتها الفرعية: {e}")

try:
    from offers.offers_db import *
except Exception:
    pass

try:
    from ads.ads_db import *
except Exception:
    pass
