# -*- coding: utf-8 -*-
"""
database.py - النسخة المحمية والكاملة لإدارة قاعدة بيانات Supabase (PostgreSQL)
مُجهزة بحماية RLS، وإدارة اتصالات ذكية لا تنقطع، وتحديثات ذرية لحظية ⚡
"""
import os
import json
from datetime import datetime, timezone
import psycopg2
from psycopg2 import pool, OperationalError, InterfaceError
from psycopg2.extras import RealDictCursor, Json
from contextlib import contextmanager

# ==================== Helper Formatting Function ====================
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
    """تأسيس بركة اتصالات قوية مع تفعيل الحماية (RLS) والفهارس السريعة"""
    global db_pool
    if db_pool is None or db_pool.closed:
        db_url = get_database_url()
        db_pool = pool.ThreadedConnectionPool(
            minconn=1,
            maxconn=15,
            dsn=db_url,
            connect_timeout=5,
            keepalives=1,
            keepalives_idle=30,
            keepalives_interval=10,
            keepalives_count=5
        )
        print("⚡ [Supabase Pool] تم تأسيس بركة الاتصالات بنجاح!")
        
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
                        storage_level INT DEFAULT 1,
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

                    CREATE TABLE IF NOT EXISTS settings (
                        key VARCHAR(128) PRIMARY KEY,
                        value JSONB DEFAULT '{}'::jsonb,
                        updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                    );

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

                    -- تحديث أعمدة جدول users
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS hourly_rate DOUBLE PRECISION DEFAULT 0.10;
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS mined_points DOUBLE PRECISION DEFAULT 0.0;
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS total_mined DOUBLE PRECISION DEFAULT 0.0;
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS storage_level INT DEFAULT 0;
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
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS boost_claims_count INT DEFAULT 0;
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS boost_history JSONB DEFAULT '[]'::jsonb;
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS daily_claims_count INT DEFAULT 0;
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS daily_history JSONB DEFAULT '[]'::jsonb;
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS vip_status JSONB DEFAULT '{}'::jsonb;

                    -- إنشاء فهارس لتسريع جلب الأرصدة لحظياً
                    CREATE INDEX IF NOT EXISTS idx_users_user_id ON users(user_id);
                    CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id);

                    -- تفعيل حماية RLS لمنع الوصول الخارجي غير المصرح به (إلغاء UNRESTRICTED)
                    ALTER TABLE users ENABLE ROW LEVEL SECURITY;
                    ALTER TABLE devices ENABLE ROW LEVEL SECURITY;
                    ALTER TABLE banned_devices ENABLE ROW LEVEL SECURITY;
                    ALTER TABLE settings ENABLE ROW LEVEL SECURITY;
                    ALTER TABLE processed_txs ENABLE ROW LEVEL SECURITY;
                    ALTER TABLE purchase_history ENABLE ROW LEVEL SECURITY;
                """)
            print("🛡️ [Supabase Security] تم إعداد الجداول وتفعيل حماية RLS بنجاح!")
        except Exception as e:
            print(f"⚠️ خطأ أثناء إنشاء/تحديث الجداول: {e}")
        finally:
            db_pool.putconn(conn)

    return db_pool

@contextmanager
def get_db_connection():
    """مستلم اتصالات ذكي يتحقق من سلامة الاتصال ويعيد فتحه تلقائياً إذا انقطع"""
    pool_obj = init_db_pool()
    conn = pool_obj.getconn()
    broken = False
    try:
        # فحص سريع للتأكد من أن الاتصال لم ينقطع من جهة السيرفر
        if conn.closed != 0:
            broken = True
            pool_obj.putconn(conn, close=True)
            conn = pool_obj.getconn()
            broken = False
        else:
            try:
                with conn.cursor() as test_cur:
                    test_cur.execute("SELECT 1")
            except (OperationalError, InterfaceError):
                pool_obj.putconn(conn, close=True)
                conn = pool_obj.getconn()

        conn.autocommit = True
        yield conn
    except (OperationalError, InterfaceError) as e:
        broken = True
        print(f"⚠️ انقطاع في اتصال قاعدة البيانات، سيتم استبداله: {e}")
        raise
    finally:
        if conn:
            try:
                pool_obj.putconn(conn, close=broken or (conn.closed != 0))
            except Exception:
                pass

def get_db():
    return init_db_pool()

# ==================== Core Functions ====================

def _sanitize_id(sid):
    if sid is None:
        return None
    s = str(sid).strip()
    if not s or s.lower() in ("none", "null", "undefined", "nan", "[object object]"):
        return None
    return s

def get_user(telegram_id):
    """جلب بيانات المستخدم كاملة مع تنسيق التواريخ والأرصدة"""
    clean_id = _sanitize_id(telegram_id)
    if not clean_id:
        return None
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
                    d['balance'] = float(d.get('balance') or 0.0)
                    d['zn_balance'] = d['balance']
                    d['usd_balance'] = float(d.get('usd_balance') or 0.0)
                    d['usdt_balance'] = d['usd_balance']
                    d['znx_balance'] = float(d.get('znx_balance') or 0.0)
                    for k, v in list(d.items()):
                        if isinstance(v, datetime):
                            d[k] = format_iso(v)
                    return d
                return None
    except Exception as e:
        print(f"❌ خطأ get_user: {e}")
        return None

def get_user_balances(telegram_id):
    """دالة مخصصة وسريعة لجلب الأرصدة الثلاثة فقط"""
    clean_id = _sanitize_id(telegram_id)
    default_bal = {'zn_balance': 0.0, 'usdt_balance': 0.0, 'znx_balance': 0.0}
    if not clean_id:
        return default_bal
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT COALESCE(balance, 0.0), COALESCE(usd_balance, 0.0), COALESCE(znx_balance, 0.0)
                    FROM users 
                    WHERE tg_id = %s OR user_id = %s OR telegram_id = %s
                    LIMIT 1
                """, (clean_id, clean_id, clean_id))
                row = cur.fetchone()
                if row:
                    return {
                        'zn_balance': float(row[0] or 0.0),
                        'usdt_balance': float(row[1] or 0.0),
                        'znx_balance': float(row[2] or 0.0)
                    }
                return default_bal
    except Exception as e:
        print(f"❌ خطأ get_user_balances: {e}")
        return default_bal

def init_user(telegram_id, ref_id=None, first_name="لاعب"):
    clean_id = _sanitize_id(telegram_id)
    if not clean_id:
        return {}
    try:
        existing = get_user(clean_id)
        if not existing:
            clean_ref = _sanitize_id(ref_id)
            if clean_ref == clean_id:
                clean_ref = None
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO users (tg_id, user_id, telegram_id, first_name, ref_by)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (tg_id) DO NOTHING;
                    """, (clean_id, clean_id, clean_id, str(first_name or 'لاعب')[:100], clean_ref))
            return get_user(clean_id) or {}
        return existing
    except Exception as e:
        print(f"❌ خطأ init_user: {e}")
        return {}

def is_user_banned(telegram_id):
    clean_id = _sanitize_id(telegram_id)
    if not clean_id:
        return False
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT is_banned, device_id FROM users
                    WHERE tg_id = %s OR user_id = %s OR telegram_id = %s
                    LIMIT 1
                """, (clean_id, clean_id, clean_id))
                row = cur.fetchone()
                if not row:
                    return False
                if bool(row[0]):
                    return True
                device_id = row[1]
                if device_id:
                    cur.execute("SELECT 1 FROM banned_devices WHERE device_id = %s LIMIT 1", (device_id,))
                    if cur.fetchone():
                        return True
                return False
    except Exception as e:
        print(f"⚠️ خطأ is_user_banned: {e}")
        return False

def check_and_bind_device(telegram_id, device_id, fingerprint_hash=None):
    clean_id = _sanitize_id(telegram_id)
    clean_dev = _sanitize_id(device_id)
    if not clean_id or not clean_dev:
        return {"allowed": True}
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT reason FROM banned_devices WHERE device_id = %s LIMIT 1", (clean_dev,))
                banned = cur.fetchone()
                if banned:
                    return {"allowed": False, "reason": banned[0] or "هذا الجهاز محظور"}

                cur.execute("""
                    UPDATE users 
                    SET device_id = COALESCE(device_id, %s),
                        fingerprint_hash = COALESCE(fingerprint_hash, %s),
                        last_active_at = CURRENT_TIMESTAMP
                    WHERE tg_id = %s OR user_id = %s OR telegram_id = %s
                """, (clean_dev, fingerprint_hash, clean_id, clean_id, clean_id))
        return {"allowed": True}
    except Exception as e:
        print(f"⚠️ خطأ check_and_bind_device: {e}")
        return {"allowed": True}

ALLOWED_USER_COLUMNS = {
    'first_name', 'balance', 'usd_balance', 'znx_balance', 'ref_by',
    'referrals_count', 'last_active_at', 'interactions', 'is_banned',
    'farm_level', 'storage_level', 'device_id', 'fingerprint_hash',
    'hourly_rate', 'mined_points', 'total_mined', 'extra_storage',
    'max_cap', 'last_claim_time', 'last_daily_claim_date', 'daily_day',
    'daily_streak', 'last_boost_time', 'upgrades', 'upgrades_count',
    'welcome_seen', 'ads_watched', 'bot_active', 'bot_expires_at',
    'boost_claims_count', 'boost_history', 'daily_claims_count',
    'daily_history', 'vip_status'
}

def update_user(telegram_id, updates_dict):
    """تحديث بيانات المستخدم في Supabase بأمان تام"""
    clean_id = _sanitize_id(telegram_id)
    if not clean_id or not isinstance(updates_dict, dict) or not updates_dict:
        return False

    set_clauses = []
    values = []

    for k, v in updates_dict.items():
        col = k
        if col == 'zn_balance':
            col = 'balance'
        elif col == 'usdt_balance':
            col = 'usd_balance'

        if col not in ALLOWED_USER_COLUMNS:
            continue

        set_clauses.append(f"{col} = %s")
        if isinstance(v, (dict, list)):
            values.append(Json(v))
        else:
            values.append(v)

    if not set_clauses:
        return True

    values.extend([clean_id, clean_id, clean_id])
    query = f"""
        UPDATE users 
        SET {', '.join(set_clauses)}, last_active_at = CURRENT_TIMESTAMP
        WHERE tg_id = %s OR user_id = %s OR telegram_id = %s
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, tuple(values))
                return cur.rowcount > 0
    except Exception as e:
        print(f"❌ خطأ update_user: {e}")
        return False

def update_user_last_active(user_id):
    clean_id = _sanitize_id(user_id)
    if not clean_id:
        return False
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE users 
                    SET last_active_at = CURRENT_TIMESTAMP,
                        interactions = COALESCE(interactions, 0) + 1
                    WHERE tg_id = %s OR user_id = %s OR telegram_id = %s
                """, (clean_id, clean_id, clean_id))
                return True
    except Exception as e:
        print(f"⚠️ خطأ update_user_last_active: {e}")
        return False

def atomic_update_balance(telegram_id, amount_change, is_usd=False, is_znx=False):
    """تحديث ذري ومؤمّن للرصيد يمنع التلاعب أو الرصيد السالب"""
    clean_id = _sanitize_id(telegram_id)
    if not clean_id:
        return False, 0.0
    try:
        delta = float(amount_change)
        if delta != delta or delta == float('inf') or delta == float('-inf'):
            return False, 0.0
    except (ValueError, TypeError):
        return False, 0.0

    col = 'znx_balance' if is_znx else ('usd_balance' if is_usd else 'balance')

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                if delta < 0:
                    # التأكد من كفاية الرصيد عند الخصم لمنع الاختراق
                    cur.execute(f"""
                        UPDATE users
                        SET {col} = COALESCE({col}, 0.0) + %s,
                            last_active_at = CURRENT_TIMESTAMP
                        WHERE (tg_id = %s OR user_id = %s OR telegram_id = %s)
                          AND COALESCE({col}, 0.0) + %s >= -0.000001
                        RETURNING {col}
                    """, (delta, clean_id, clean_id, clean_id, delta))
                else:
                    cur.execute(f"""
                        UPDATE users
                        SET {col} = GREATEST(0.0, COALESCE({col}, 0.0) + %s),
                            last_active_at = CURRENT_TIMESTAMP
                        WHERE tg_id = %s OR user_id = %s OR telegram_id = %s
                        RETURNING {col}
                    """, (delta, clean_id, clean_id, clean_id))
                
                row = cur.fetchone()
                if row is not None:
                    return True, float(row[0] or 0.0)
                return False, 0.0
    except Exception as e:
        print(f"❌ خطأ atomic_update_balance: {e}")
        return False, 0.0

def get_leaderboard_data(limit=50, user_id=None):
    clean_id = _sanitize_id(user_id)
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT tg_id, first_name, COALESCE(balance, 0.0) AS balance, COALESCE(referrals_count, 0) AS referrals_count
                    FROM users
                    WHERE is_banned = FALSE
                    ORDER BY COALESCE(balance, 0.0) DESC
                    LIMIT %s
                """, (int(limit),))
                leaders = [dict(r) for r in cur.fetchall()]
                
                my_rank = "غير مصنف"
                if clean_id:
                    cur.execute("""
                        SELECT rank FROM (
                            SELECT tg_id, user_id, telegram_id,
                                   ROW_NUMBER() OVER (ORDER BY COALESCE(balance, 0.0) DESC) as rank
                            FROM users WHERE is_banned = FALSE
                        ) sub
                        WHERE tg_id = %s OR user_id = %s OR telegram_id = %s
                        LIMIT 1
                    """, (clean_id, clean_id, clean_id))
                    r = cur.fetchone()
                    if r:
                        my_rank = r['rank']

                return {"success": True, "leaderboard": leaders, "my_rank": my_rank}
    except Exception as e:
        print(f"⚠️ خطأ get_leaderboard_data: {e}")
        return {"success": True, "leaderboard": [], "my_rank": "غير مصنف"}

def get_user_data(telegram_id):
    return get_user(telegram_id)

# تشغيل التهيئة الأولية عند الاستيراد
try:
    init_db_pool()
except Exception as e:
    print(f"⚠️ تنبيه الإقلاع: {e}")
