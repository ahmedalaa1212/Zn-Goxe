# -*- coding: utf-8 -*-
"""
database.py - النسخة النموذجية المحدثة لإدارة قاعدة بيانات Supabase (PostgreSQL)
مُجهزة بأعمدة وسجلات تتبع المسابقات والمكافآت والمتجر والمعاملات المالية ⚡
"""
import os
import json
from datetime import datetime, timezone
import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor, Json

# ==================== Helper Formatting Functions ====================
def format_iso(dt):
    """تحويل أي كائن تاريخ إلى نمط ISO-8601 القياسي (UTC) المتوافق مع iOS/Android"""
    if dt is None:
        return None
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt.strftime('%Y-%m-%dT%H:%M:%SZ')
    if isinstance(dt, (int, float)):
        return datetime.fromtimestamp(dt, tz=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    s = str(dt).strip().replace(' ', 'T')
    if s.endswith('+00:00'):
        s = s[:-6] + 'Z'
    return s


def safe_parse_datetime(dt_raw, default_dt=None):
    """معالجة آمنة لتحويل أي تاريخ أو ختم زمني إلى UTC مع حماية ضد التواريخ غير المنطقية"""
    if dt_raw is None:
        return default_dt
    try:
        if isinstance(dt_raw, (int, float)):
            if dt_raw < 0 or dt_raw > 4102444800:
                return default_dt
            return datetime.fromtimestamp(dt_raw, tz=timezone.utc)
        elif isinstance(dt_raw, datetime):
            if dt_raw.tzinfo is None:
                return dt_raw.replace(tzinfo=timezone.utc)
            return dt_raw.astimezone(timezone.utc)
        else:
            s = str(dt_raw).strip().replace('Z', '+00:00')
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
    except Exception:
        return default_dt


# ==================== Supabase PostgreSQL Pool ====================
db_pool = None

def get_database_url():
    """استخراج وتنظيف رابط DATABASE_URL مع تفعيل sslmode فوراً"""
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise ValueError("❌ لم يتم العثور على DATABASE_URL في متغيرات البيئة!")
    
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    
    if "sslmode" not in db_url:
        separator = "&" if "?" in db_url else "?"
        db_url += f"{separator}sslmode=require"
        
    return db_url


def init_db_pool():
    """تأسيس بركة اتصالات خفيفة للغاية وخالية من أي عمليات ثقيلة"""
    global db_pool
    if db_pool is None or db_pool.closed:
        db_url = get_database_url()
        db_pool = pool.ThreadedConnectionPool(
            minconn=1,
            maxconn=10,
            dsn=db_url,
            connect_timeout=5
        )
        print("⚡ [Barebones Pool] تم تأسيس بركة الاتصالات بنجاح!")
        
        # إنشاء الجداول وتعديل المخطط فوراً وبطريقة مباشرة
        conn = db_pool.getconn()
        try:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute("""
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
                        is_banned BOOLEAN DEFAULT FALSE,
                        farm_level INT DEFAULT 1,
                        storage_level INT DEFAULT 0,
                        device_id VARCHAR(256),
                        fingerprint_hash VARCHAR(256)
                    );

                    CREATE TABLE IF NOT EXISTS devices (
                        device_id VARCHAR(256) PRIMARY KEY,
                        primary_user_id VARCHAR(128),
                        users JSONB DEFAULT '[]'::jsonb,
                        fingerprint_hash VARCHAR(256),
                        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                        last_seen TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                        is_banned BOOLEAN DEFAULT FALSE
                    );

                    CREATE TABLE IF NOT EXISTS banned_devices (
                        device_id VARCHAR(256) PRIMARY KEY,
                        reason TEXT,
                        banned_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                    );

                    -- جدول الإعدادات العامة (لحفظ إعدادات المزرعة، المتجر، إلخ)
                    CREATE TABLE IF NOT EXISTS settings (
                        key VARCHAR(128) PRIMARY KEY,
                        value JSONB DEFAULT '{}'::jsonb,
                        updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                    );

                    -- جدول المعاملات المكتملة والدفع المباشر
                    CREATE TABLE IF NOT EXISTS processed_txs (
                        tx_hash VARCHAR(256) PRIMARY KEY,
                        tg_id VARCHAR(128),
                        package_id VARCHAR(64),
                        type VARCHAR(64),
                        cost_zn DOUBLE PRECISION DEFAULT 0.0,
                        cost_usd DOUBLE PRECISION DEFAULT 0.0,
                        details JSONB DEFAULT '{}'::jsonb,
                        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                    );

                    -- جدول سجل المشتريات العام للتدقيق المالي
                    CREATE TABLE IF NOT EXISTS purchase_history (
                        id SERIAL PRIMARY KEY,
                        tg_id VARCHAR(128),
                        type VARCHAR(64),
                        item_id VARCHAR(64),
                        cost_zn DOUBLE PRECISION DEFAULT 0.0,
                        cost_usd DOUBLE PRECISION DEFAULT 0.0,
                        tx_hash VARCHAR(256),
                        details JSONB DEFAULT '{}'::jsonb,
                        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                    );

                    -- تحديث جدول users ليكون جاهزاً لكافة بيانات التعدين والمزرعة
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS hourly_rate DOUBLE PRECISION DEFAULT 0.10;
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS mined_points DOUBLE PRECISION DEFAULT 0.0;
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS total_mined DOUBLE PRECISION DEFAULT 0.0;
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS extra_storage DOUBLE PRECISION DEFAULT 0.0;
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS max_cap DOUBLE PRECISION DEFAULT 0.5;
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS last_claim_time TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP;
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS last_daily_claim_date VARCHAR(32);
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS daily_day INT DEFAULT 1;
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS daily_streak INT DEFAULT 1;
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS last_boost_time TIMESTAMPTZ;
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS upgrades JSONB DEFAULT '{}'::jsonb;
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS upgrades_count INT DEFAULT 0;
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS welcome_seen BOOLEAN DEFAULT FALSE;
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS ads_watched INT DEFAULT 0;
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS bot_active BOOLEAN DEFAULT FALSE;
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS bot_expires_at TIMESTAMPTZ;

                    -- أعمدة المسابقات وسجلات المكافآت التفصيلية
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS boost_claims_count INT DEFAULT 0;
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS boost_history JSONB DEFAULT '[]'::jsonb;
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS daily_claims_count INT DEFAULT 0;
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS daily_history JSONB DEFAULT '[]'::jsonb;
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS vip_status JSONB DEFAULT '{}'::jsonb;
                """)
            print("⚡ [Supabase Setup] تم إنشاء الجداول وتحديث مخطط المسابقات والإعدادات بنجاح!")
        except Exception as e:
            print(f"⚠️ خطأ أثناء إنشاء/تحديث الجداول: {e}")
        finally:
            db_pool.putconn(conn)

    return db_pool


from contextlib import contextmanager

@contextmanager
def get_db_connection():
    """مستلم اتصالات خفيف ومباشر مع إدارة تلقائية للإنهاء"""
    pool_obj = init_db_pool()
    conn = pool_obj.getconn()
    try:
        yield conn
    finally:
        if conn:
            pool_obj.putconn(conn)


def get_db():
    return init_db_pool()


# ==================== Helpers & Core Functions ====================

def _sanitize_id(sid):
    if not sid or str(sid).lower() in ("none", "null", "undefined"):
        return None
    return str(sid).strip()


def get_user(telegram_id):
    clean_id = _sanitize_id(telegram_id)
    if not clean_id:
        return None
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM users WHERE tg_id = %s", (clean_id,))
                row = cur.fetchone()
                if row:
                    d = dict(row)
                    for k, v in list(d.items()):
                        if isinstance(v, datetime):
                            d[k] = format_iso(v)
                    return d
                return None
    except Exception as e:
        print(f"❌ خطأ get_user: {e}")
        return None


def init_user(telegram_id, ref_id=None, first_name="لاعب"):
    clean_id = _sanitize_id(telegram_id)
    if not clean_id:
        return {}
    try:
        existing = get_user(clean_id)
        if not existing:
            with get_db_connection() as conn:
                conn.autocommit = True
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO users (tg_id, user_id, telegram_id, first_name, ref_by)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (tg_id) DO NOTHING;
                    """, (clean_id, clean_id, clean_id, str(first_name or 'لاعب'), _sanitize_id(ref_id)))
            return get_user(clean_id) or {}
        return existing
    except Exception as e:
        print(f"❌ خطأ init_user: {e}")
        return {}


def get_setting(key, default=None):
    """جلب إعداد محدد من جدول settings في Supabase"""
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT value FROM settings WHERE key = %s", (key,))
                row = cur.fetchone()
                if row and row.get("value"):
                    return row["value"]
    except Exception as e:
        print(f"⚠️ خطأ جلب الإعداد {key}: {e}")
    return default


def set_setting(key, value):
    """حفظ أو تحديث إعداد في جدول settings في Supabase"""
    try:
        with get_db_connection() as conn:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO settings (key, value, updated_at)
                    VALUES (%s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = CURRENT_TIMESTAMP;
                """, (key, Json(value)))
        return True
    except Exception as e:
        print(f"❌ خطأ حفظ الإعداد {key}: {e}")
        return False


def update_user(telegram_id, updates_dict):
    """تحديث ديناميكي لحقول المستخدم في Supabase"""
    clean_id = _sanitize_id(telegram_id)
    if not clean_id or not updates_dict:
        return False
    try:
        set_clauses = []
        params = []
        for key, val in updates_dict.items():
            if isinstance(val, (dict, list)):
                set_clauses.append(f"{key} = %s")
                params.append(Json(val))
            else:
                set_clauses.append(f"{key} = %s")
                params.append(val)

        params.append(clean_id)
        sql = f"UPDATE users SET {', '.join(set_clauses)}, last_active_at = CURRENT_TIMESTAMP WHERE tg_id = %s"

        with get_db_connection() as conn:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(sql, tuple(params))
        return True
    except Exception as e:
        print(f"❌ خطأ update_user: {e}")
        return False


def is_user_banned(telegram_id):
    u = get_user(telegram_id)
    return bool(u and u.get("is_banned"))


def check_and_bind_device(telegram_id, device_id, fingerprint_hash=None):
    return {"allowed": True}


def update_user_last_active(user_id):
    return update_user(user_id, {"interactions": 1})


def atomic_update_balance(telegram_id, amount_change, is_usd=False):
    clean_id = _sanitize_id(telegram_id)
    if not clean_id:
        return False, 0.0
    field = "usd_balance" if is_usd else "balance"
    try:
        with get_db_connection() as conn:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(f"""
                    UPDATE users SET {field} = GREATEST(0.0, {field} + %s)
                    WHERE tg_id = %s RETURNING {field};
                """, (amount_change, clean_id))
                row = cur.fetchone()
                if row:
                    return True, float(row[0])
    except Exception as e:
        print(f"❌ خطأ atomic_update_balance: {e}")
    return False, 0.0


def get_leaderboard_data(limit=50, user_id=None):
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT tg_id, first_name, mined_points, total_mined, balance, hourly_rate
                    FROM users
                    ORDER BY mined_points DESC, total_mined DESC
                    LIMIT %s;
                """, (limit,))
                rows = cur.fetchall()
                leaderboard = []
                for idx, row in enumerate(rows, start=1):
                    item = dict(row)
                    item["rank"] = idx
                    leaderboard.append(item)
                return {"success": True, "leaderboard": leaderboard, "my_rank": "غير مصنف"}
    except Exception as e:
        print(f"❌ خطأ get_leaderboard_data: {e}")
        return {"success": False, "leaderboard": [], "my_rank": "غير مصنف"}


def get_user_data(telegram_id):
    return get_user(telegram_id)


# تشغيل التهيئة الأولية عند الاستيراد
try:
    init_db_pool()
except Exception as e:
    print(f"⚠️ تنبيه الإقلاع: {e}")
