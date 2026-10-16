# -*- coding: utf-8 -*-
"""
database.py - النسخة الكاملة والمستقرة لإدارة قاعدة بيانات Supabase (PostgreSQL)
مزودة بفحص تلقائي للاتصالات (Auto-Heal Pool) ودعم كامل للأرصدة اللحظية ونظام الأصدقاء ⚡
"""
import os
from datetime import datetime, timezone
import psycopg2
from psycopg2 import pool
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
_schema_initialized = False

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
    """تأسيس بركة اتصالات ذكية مقاومة لانقطاع اتصالات Supabase وإنشاء الجداول تلقائياً"""
    global db_pool, _schema_initialized
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
        
        if not _schema_initialized:
            conn = None
            try:
                conn = db_pool.getconn()
                conn.autocommit = True
                with conn.cursor() as cur:
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS users (
                            tg_id VARCHAR(128) PRIMARY KEY,
                            user_id VARCHAR(128),
                            telegram_id VARCHAR(128),
                            first_name VARCHAR(100) DEFAULT 'لاعب',
                            name VARCHAR(100) DEFAULT 'لاعب',
                            balance DOUBLE PRECISION DEFAULT 0.0,
                            usd_balance DOUBLE PRECISION DEFAULT 0.0,
                            znx_balance DOUBLE PRECISION DEFAULT 0.0,
                            ref_by VARCHAR(128),
                            referred_by VARCHAR(128),
                            referrals_count INT DEFAULT 0,
                            pending_ref_earnings DOUBLE PRECISION DEFAULT 0.0,
                            total_ref_earnings DOUBLE PRECISION DEFAULT 0.0,
                            claimed_ref_tasks JSONB DEFAULT '[]'::jsonb,
                            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                            last_active_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                            interactions INT DEFAULT 1,
                            is_banned BOOLEAN DEFAULT FALSE,
                            farm_level INT DEFAULT 1,
                            storage_level INT DEFAULT 0,
                            device_id VARCHAR(256),
                            fingerprint_hash VARCHAR(256)
                        );

                        CREATE TABLE IF NOT EXISTS user_friends (
                            id BIGSERIAL PRIMARY KEY,
                            referrer_id VARCHAR(128) NOT NULL,
                            friend_id VARCHAR(128) NOT NULL,
                            first_name VARCHAR(100) DEFAULT 'صديق',
                            name VARCHAR(100) DEFAULT 'صديق',
                            earned_from_him DOUBLE PRECISION DEFAULT 0.0,
                            upgrades_count INT DEFAULT 0,
                            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                            CONSTRAINT uq_referrer_friend UNIQUE (referrer_id, friend_id)
                        );

                        CREATE INDEX IF NOT EXISTS idx_user_friends_referrer ON user_friends(referrer_id);
                        CREATE INDEX IF NOT EXISTS idx_user_friends_friend ON user_friends(friend_id);

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

                        ALTER TABLE users ADD COLUMN IF NOT EXISTS name VARCHAR(100) DEFAULT 'لاعب';
                        ALTER TABLE users ADD COLUMN IF NOT EXISTS referred_by VARCHAR(128);
                        ALTER TABLE users ADD COLUMN IF NOT EXISTS pending_ref_earnings DOUBLE PRECISION DEFAULT 0.0;
                        ALTER TABLE users ADD COLUMN IF NOT EXISTS total_ref_earnings DOUBLE PRECISION DEFAULT 0.0;
                        ALTER TABLE users ADD COLUMN IF NOT EXISTS claimed_ref_tasks JSONB DEFAULT '[]'::jsonb;
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
                        ALTER TABLE users ADD COLUMN IF NOT EXISTS is_vip BOOLEAN DEFAULT FALSE;
                        ALTER TABLE users ADD COLUMN IF NOT EXISTS vip_active BOOLEAN DEFAULT FALSE;
                        ALTER TABLE users ADD COLUMN IF NOT EXISTS plan VARCHAR(64);
                        ALTER TABLE users ADD COLUMN IF NOT EXISTS vip_package VARCHAR(64);
                        ALTER TABLE users ADD COLUMN IF NOT EXISTS vip_level VARCHAR(64);
                        ALTER TABLE users ADD COLUMN IF NOT EXISTS vip_expires TIMESTAMPTZ;
                        ALTER TABLE users ADD COLUMN IF NOT EXISTS vip_expires_at TIMESTAMPTZ;
                        ALTER TABLE users ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ;

                        CREATE INDEX IF NOT EXISTS idx_users_ref_by ON users(ref_by);
                        CREATE INDEX IF NOT EXISTS idx_users_referred_by ON users(referred_by);
                    """)
                _schema_initialized = True
                print("⚡ [Supabase Setup] تم التحقق من الجداول والمخطط بنجاح!")
            except Exception as e:
                print(f"⚠️ خطأ أثناء إنشاء/تحديث الجداول: {e}")
            finally:
                if conn:
                    db_pool.putconn(conn)

    return db_pool

@contextmanager
def get_db_connection():
    """مستلم اتصالات ذكي يفحص صلاحية الاتصال ويستبدله فوراً إذا أغلقته Supabase"""
    pool_obj = init_db_pool()
    conn = pool_obj.getconn()
    broken = False

    try:
        if conn.closed:
            broken = True
        else:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
    except Exception:
        broken = True

    if broken:
        try:
            pool_obj.putconn(conn, close=True)
        except Exception:
            pass
        conn = pool_obj.getconn()
        conn.autocommit = True

    try:
        yield conn
    except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
        broken = True
        raise e
    finally:
        if conn:
            try:
                pool_obj.putconn(conn, close=broken or bool(conn.closed))
            except Exception:
                pass

def get_db():
    return init_db_pool()

def initialize_supabase():
    return init_db_pool()

def initialize_firebase():
    """موجودة للتوافق الخلفي فقط حتى لا ينكسر أي استدعاء قديم"""
    return init_db_pool()

# ==================== Core Functions ====================

def _sanitize_id(sid):
    if sid is None:
        return None
    s = str(sid).strip()
    if s.startswith("ref_"):
        s = s.replace("ref_", "", 1).strip()
    if s.endswith(".0"):
        s = s[:-2]
    if not s or s.lower() in ("none", "null", "undefined", "nan", ""):
        return None
    return s

def get_user(telegram_id):
    """جلب بيانات المستخدم كاملة من Supabase"""
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
                    for k, v in list(d.items()):
                        if isinstance(v, datetime):
                            d[k] = format_iso(v)
                    d['balance'] = float(d.get('balance') or 0.0)
                    d['usd_balance'] = float(d.get('usd_balance') or 0.0)
                    d['znx_balance'] = float(d.get('znx_balance') or 0.0)
                    return d
                return None
    except Exception as e:
        print(f"❌ خطأ get_user: {e}")
        return None

def get_user_balances(telegram_id):
    """دالة مخصصة وسريعة لجلب الأرصدة الثلاثة فقط من Supabase"""
    clean_id = _sanitize_id(telegram_id)
    if not clean_id:
        return {'zn_balance': 0.0, 'usdt_balance': 0.0, 'znx_balance': 0.0}
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
                return {'zn_balance': 0.0, 'usdt_balance': 0.0, 'znx_balance': 0.0}
    except Exception as e:
        print(f"❌ خطأ get_user_balances: {e}")
        return {'zn_balance': 0.0, 'usdt_balance': 0.0, 'znx_balance': 0.0}

def init_user(telegram_id, ref_id=None, first_name="لاعب"):
    """إنشاء مستخدم جديد أو تحديث بياناته وربط الإحالة تلقائياً في جدولي users و user_friends"""
    clean_id = _sanitize_id(telegram_id)
    if not clean_id:
        return {}
    clean_ref = _sanitize_id(ref_id)
    if clean_ref == clean_id or (clean_ref and not clean_ref.isdigit()):
        clean_ref = None
    safe_name = str(first_name or 'لاعب').strip()[:100]

    try:
        existing = get_user(clean_id)
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                if not existing:
                    # منع الإحالة العكسية
                    if clean_ref:
                        cur.execute("SELECT ref_by, referred_by FROM users WHERE tg_id = %s LIMIT 1", (clean_ref,))
                        ref_row = cur.fetchone()
                        if ref_row and (ref_row[0] == clean_id or ref_row[1] == clean_id):
                            clean_ref = None

                    cur.execute("""
                        INSERT INTO users (tg_id, user_id, telegram_id, first_name, name, ref_by, referred_by)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (tg_id) DO NOTHING;
                    """, (clean_id, clean_id, clean_id, safe_name, safe_name, clean_ref, clean_ref))

                    if clean_ref:
                        # التأكد من وجود حساب الداعي وإضافة الصديق في جدول user_friends
                        cur.execute("""
                            INSERT INTO users (tg_id, user_id, telegram_id, first_name, name)
                            VALUES (%s, %s, %s, 'لاعب', 'لاعب')
                            ON CONFLICT (tg_id) DO NOTHING;
                        """, (clean_ref, clean_ref, clean_ref))

                        cur.execute("""
                            INSERT INTO user_friends (referrer_id, friend_id, first_name, name, earned_from_him, upgrades_count)
                            VALUES (%s, %s, %s, %s, 0.0, 0)
                            ON CONFLICT (referrer_id, friend_id) DO NOTHING;
                        """, (clean_ref, clean_id, safe_name, safe_name))

                        cur.execute("""
                            UPDATE users
                            SET referrals_count = (
                                SELECT COUNT(*) FROM user_friends WHERE referrer_id = %s
                            )
                            WHERE tg_id = %s;
                        """, (clean_ref, clean_ref))
                else:
                    # إذا كان المستخدم موجوداً مسبقاً بدون داعي وجاء عبر رابط إحالة لأول مرة
                    current_ref = existing.get("ref_by") or existing.get("referred_by")
                    if not current_ref and clean_ref:
                        cur.execute("SELECT ref_by, referred_by FROM users WHERE tg_id = %s LIMIT 1", (clean_ref,))
                        ref_row = cur.fetchone()
                        if not (ref_row and (ref_row[0] == clean_id or ref_row[1] == clean_id)):
                            cur.execute("""
                                UPDATE users
                                SET ref_by = %s, referred_by = %s
                                WHERE tg_id = %s AND ref_by IS NULL AND referred_by IS NULL;
                            """, (clean_ref, clean_ref, clean_id))
                            cur.execute("""
                                INSERT INTO user_friends (referrer_id, friend_id, first_name, name, earned_from_him, upgrades_count)
                                VALUES (%s, %s, %s, %s, 0.0, COALESCE(%s, 0))
                                ON CONFLICT (referrer_id, friend_id) DO NOTHING;
                            """, (clean_ref, clean_id, safe_name, safe_name, int(existing.get("upgrades_count") or 0)))

        return get_user(clean_id) or existing or {}
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
                    SELECT COALESCE(is_banned, FALSE) FROM users
                    WHERE tg_id = %s OR user_id = %s OR telegram_id = %s
                    LIMIT 1
                """, (clean_id, clean_id, clean_id))
                row = cur.fetchone()
                return bool(row[0]) if row else False
    except Exception:
        return False

def check_and_bind_device(telegram_id, device_id, fingerprint_hash=None):
    clean_id = _sanitize_id(telegram_id)
    if not clean_id or not device_id:
        return {"allowed": True}
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM banned_devices WHERE device_id = %s LIMIT 1", (str(device_id),))
                if cur.fetchone():
                    return {"allowed": False, "reason": "هذا الجهاز محظور"}
                cur.execute("""
                    UPDATE users
                    SET device_id = COALESCE(device_id, %s),
                        fingerprint_hash = COALESCE(fingerprint_hash, %s),
                        last_active_at = CURRENT_TIMESTAMP
                    WHERE tg_id = %s OR user_id = %s OR telegram_id = %s
                """, (str(device_id), str(fingerprint_hash) if fingerprint_hash else None, clean_id, clean_id, clean_id))
        return {"allowed": True}
    except Exception:
        return {"allowed": True}

def update_user(telegram_id, updates_dict):
    """تحديث بيانات المستخدم في Supabase بشكل فعلي وآمن"""
    clean_id = _sanitize_id(telegram_id)
    if not clean_id or not updates_dict or not isinstance(updates_dict, dict):
        return False
    try:
        set_clauses = []
        values = []
        for k, v in updates_dict.items():
            if k in ('tg_id',):
                continue
            set_clauses.append(f"{k} = %s")
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
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, tuple(values))
        return True
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
    except Exception:
        return False

def atomic_update_balance(telegram_id, amount_change, is_usd=False, is_znx=False):
    """تحديث ذري ولحظي للأرصدة في Supabase وإرجاع الرصيد الجديد الفعلي"""
    clean_id = _sanitize_id(telegram_id)
    if not clean_id:
        return False, 0.0
    col = 'znx_balance' if is_znx else ('usd_balance' if is_usd else 'balance')
    try:
        delta = float(amount_change)
        with get_db_connection() as conn:
            with conn.cursor() as cur:
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
                    SELECT tg_id, first_name, COALESCE(balance, 0.0) AS balance
                    FROM users
                    WHERE COALESCE(is_banned, FALSE) = FALSE
                    ORDER BY COALESCE(balance, 0.0) DESC
                    LIMIT %s
                """, (int(limit),))
                rows = [dict(r) for r in cur.fetchall()]
                my_rank = "غير مصنف"
                if clean_id:
                    cur.execute("""
                        SELECT COUNT(*) + 1 AS rank FROM users
                        WHERE COALESCE(is_banned, FALSE) = FALSE
                          AND COALESCE(balance, 0.0) > COALESCE((
                              SELECT balance FROM users
                              WHERE tg_id = %s OR user_id = %s OR telegram_id = %s
                              LIMIT 1
                          ), 0.0)
                    """, (clean_id, clean_id, clean_id))
                    r_row = cur.fetchone()
                    if r_row and r_row.get('rank'):
                        my_rank = int(r_row['rank'])
                return {"success": True, "leaderboard": rows, "my_rank": my_rank}
    except Exception as e:
        print(f"❌ خطأ get_leaderboard_data: {e}")
        return {"success": True, "leaderboard": [], "my_rank": "غير مصنف"}

def get_user_data(telegram_id):
    return get_user(telegram_id)

# تشغيل التهيئة الأولية عند الاستيراد
try:
    init_db_pool()
except Exception as e:
    print(f"⚠️ تنبيه الإقلاع: {e}")
