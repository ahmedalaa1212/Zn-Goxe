# -*- coding: utf-8 -*-
"""
database.py - النسخة الكاملة والمستقرة لإدارة قاعدة بيانات Supabase (PostgreSQL)
مزودة بفحص تلقائي للاتصالات (Auto-Heal Pool)، نظام المعاملات الذرية (Atomic Transactions)،
ترقية ذاتية لكافة جداول السحب والسجلات والمحافظ، ودعم كامل للأرصدة اللحظية والإدارة ⚡
"""
import os
import math
import json
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
    """تأسيس بركة اتصالات ذكية مقاومة لانقطاع اتصالات Supabase وإنشاء وترقية الجداول تلقائياً"""
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
                            username VARCHAR(100) DEFAULT '',
                            balance DOUBLE PRECISION DEFAULT 0.0,
                            ad_balance DOUBLE PRECISION DEFAULT 0.0,
                            usd_balance DOUBLE PRECISION DEFAULT 0.0,
                            znx_balance DOUBLE PRECISION DEFAULT 0.0,
                            wallet_address TEXT DEFAULT '',
                            wallets JSONB DEFAULT '{}'::jsonb,
                            ref_by VARCHAR(128),
                            referred_by VARCHAR(128),
                            referrals_count INT DEFAULT 0,
                            ref_count INT DEFAULT 0,
                            referral_count INT DEFAULT 0,
                            pending_ref_earnings DOUBLE PRECISION DEFAULT 0.0,
                            total_ref_earnings DOUBLE PRECISION DEFAULT 0.0,
                            claimed_ref_tasks JSONB DEFAULT '[]'::jsonb,
                            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                            last_active_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                            interactions INT DEFAULT 1,
                            is_banned BOOLEAN DEFAULT FALSE,
                            banned BOOLEAN DEFAULT FALSE,
                            ban_reason TEXT,
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
                            banned_user_id VARCHAR(128),
                            reason TEXT,
                            banned_by VARCHAR(128),
                            banned_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                        );

                        CREATE TABLE IF NOT EXISTS settings (
                            key VARCHAR(128) PRIMARY KEY,
                            value JSONB DEFAULT '{}'::jsonb,
                            updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                        );

                        CREATE TABLE IF NOT EXISTS processed_txs (
                            tx_hash VARCHAR(256) PRIMARY KEY DEFAULT md5(random()::text || clock_timestamp()::text),
                            id TEXT DEFAULT md5(random()::text || clock_timestamp()::text),
                            tx_id TEXT,
                            tg_id VARCHAR(128),
                            user_id VARCHAR(128),
                            package_id VARCHAR(64),
                            type VARCHAR(64) DEFAULT 'withdraw',
                            coins NUMERIC DEFAULT 0.0,
                            amount NUMERIC DEFAULT 0.0,
                            fee_usd NUMERIC DEFAULT 0.02,
                            net_coins NUMERIC DEFAULT 0.0,
                            cost_zn DOUBLE PRECISION DEFAULT 0.0,
                            cost_usd DOUBLE PRECISION DEFAULT 0.0,
                            currency VARCHAR(32) DEFAULT 'ZNX',
                            tier_name TEXT DEFAULT '',
                            wallet_address TEXT DEFAULT '',
                            status VARCHAR(50) DEFAULT 'pending',
                            processed_by TEXT,
                            details TEXT DEFAULT '',
                            failure_reason TEXT,
                            processing_started_at TIMESTAMPTZ,
                            processed_at TIMESTAMPTZ,
                            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                        );

                        CREATE TABLE IF NOT EXISTS transactions (
                            id SERIAL PRIMARY KEY,
                            tx_id TEXT,
                            tx_hash TEXT,
                            user_id TEXT,
                            tg_id TEXT,
                            coins NUMERIC DEFAULT 0.0,
                            amount NUMERIC DEFAULT 0.0,
                            fee NUMERIC DEFAULT 0.0,
                            fee_usd NUMERIC DEFAULT 0.0,
                            net_coins NUMERIC DEFAULT 0.0,
                            net_amount NUMERIC DEFAULT 0.0,
                            currency TEXT DEFAULT 'ZNX',
                            tier_name TEXT DEFAULT '',
                            wallet_address TEXT DEFAULT '',
                            network TEXT DEFAULT 'TON',
                            type TEXT DEFAULT 'withdraw',
                            status TEXT DEFAULT 'pending',
                            processed_by TEXT,
                            details TEXT DEFAULT '',
                            failure_reason TEXT,
                            processed_at TIMESTAMPTZ,
                            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                        );

                        CREATE TABLE IF NOT EXISTS withdraw_requests (
                            id SERIAL PRIMARY KEY,
                            tx_id TEXT,
                            user_id VARCHAR(255) NOT NULL,
                            tg_id VARCHAR(255),
                            coins NUMERIC(18, 4) DEFAULT 0.0,
                            amount NUMERIC(18, 4) DEFAULT 0.0,
                            fee NUMERIC(18, 4) DEFAULT 0.0,
                            fee_usd NUMERIC(18, 4) DEFAULT 0.02,
                            net_coins NUMERIC(18, 4) DEFAULT 0.0,
                            net_amount NUMERIC(18, 4) DEFAULT 0.0,
                            currency VARCHAR(32) DEFAULT 'ZNX',
                            tier_name TEXT DEFAULT '',
                            wallet_address TEXT,
                            network VARCHAR(32) DEFAULT 'TON',
                            status VARCHAR(50) DEFAULT 'pending',
                            tx_hash TEXT,
                            processed_by TEXT,
                            failure_reason TEXT,
                            admin_note TEXT,
                            details TEXT,
                            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                            processed_at TIMESTAMPTZ
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

                        CREATE TABLE IF NOT EXISTS admin_logs (
                            id BIGSERIAL PRIMARY KEY,
                            action TEXT NOT NULL,
                            tx_id TEXT,
                            user_id TEXT,
                            admin_id TEXT,
                            admin_name TEXT,
                            status TEXT,
                            amount NUMERIC DEFAULT 0.0,
                            details TEXT,
                            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                        );

                        CREATE TABLE IF NOT EXISTS moderators (
                            tg_id VARCHAR(128) PRIMARY KEY,
                            name VARCHAR(100) NOT NULL,
                            permissions JSONB DEFAULT '{}'::jsonb,
                            added_by VARCHAR(100) DEFAULT 'المدير العام',
                            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                        );

                        CREATE TABLE IF NOT EXISTS broadcasts (
                            id SERIAL PRIMARY KEY,
                            admin_name VARCHAR(100),
                            message_snippet TEXT,
                            total_targets INT DEFAULT 0,
                            success_count INT DEFAULT 0,
                            blocked_count INT DEFAULT 0,
                            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                        );

                        -- ==================== جداول نظام المهام والحملات الإعلانية ====================
                        CREATE TABLE IF NOT EXISTS campaigns (
                            id VARCHAR(128) PRIMARY KEY,
                            creator_id VARCHAR(128) NOT NULL,
                            platform VARCHAR(64) NOT NULL,
                            url TEXT NOT NULL,
                            description TEXT NOT NULL,
                            reward DOUBLE PRECISION NOT NULL DEFAULT 10.0 CHECK (reward > 0),
                            users_needed INT NOT NULL DEFAULT 1 CHECK (users_needed >= 1),
                            users_completed INT NOT NULL DEFAULT 0 CHECK (users_completed >= 0),
                            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                        );

                        CREATE INDEX IF NOT EXISTS idx_campaigns_creator ON campaigns(creator_id);
                        CREATE INDEX IF NOT EXISTS idx_campaigns_active ON campaigns(users_completed, users_needed);

                        CREATE TABLE IF NOT EXISTS completed_tasks (
                            id BIGSERIAL PRIMARY KEY,
                            tg_id VARCHAR(128) NOT NULL,
                            task_id VARCHAR(128) NOT NULL,
                            platform VARCHAR(64) DEFAULT '',
                            completion_scope VARCHAR(32) NOT NULL DEFAULT 'ONCE',
                            completed_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                            CONSTRAINT uq_user_task_scope UNIQUE (tg_id, task_id, completion_scope)
                        );

                        CREATE INDEX IF NOT EXISTS idx_completed_tasks_user ON completed_tasks(tg_id);
                        CREATE INDEX IF NOT EXISTS idx_completed_tasks_lookup ON completed_tasks(tg_id, task_id, completion_scope);

                        CREATE TABLE IF NOT EXISTS task_sessions (
                            tg_id VARCHAR(128) NOT NULL,
                            task_id VARCHAR(128) NOT NULL,
                            started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                            PRIMARY KEY (tg_id, task_id)
                        );

                        CREATE INDEX IF NOT EXISTS idx_task_sessions_started ON task_sessions(started_at);

                        -- ==================== ترقية أعمدة جدول المستخدمين تلقائياً ====================
                        ALTER TABLE users ADD COLUMN IF NOT EXISTS ad_balance DOUBLE PRECISION DEFAULT 0.0;
                        ALTER TABLE users ADD COLUMN IF NOT EXISTS name VARCHAR(100) DEFAULT 'لاعب';
                        ALTER TABLE users ADD COLUMN IF NOT EXISTS username VARCHAR(100) DEFAULT '';
                        ALTER TABLE users ADD COLUMN IF NOT EXISTS wallet_address TEXT DEFAULT '';
                        ALTER TABLE users ADD COLUMN IF NOT EXISTS wallets JSONB DEFAULT '{}'::jsonb;
                        ALTER TABLE users ADD COLUMN IF NOT EXISTS referred_by VARCHAR(128);
                        ALTER TABLE users ADD COLUMN IF NOT EXISTS ref_count INT DEFAULT 0;
                        ALTER TABLE users ADD COLUMN IF NOT EXISTS referral_count INT DEFAULT 0;
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
                        ALTER TABLE users ADD COLUMN IF NOT EXISTS banned BOOLEAN DEFAULT FALSE;
                        ALTER TABLE users ADD COLUMN IF NOT EXISTS ban_reason TEXT;
                        ALTER TABLE users ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP;

                        CREATE INDEX IF NOT EXISTS idx_users_ref_by ON users(ref_by);
                        CREATE INDEX IF NOT EXISTS idx_users_referred_by ON users(referred_by);
                        CREATE INDEX IF NOT EXISTS idx_users_user_id ON users(user_id);
                        CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id);
                    """)

                    # ترقية جداول السحب والمعاملات الموجودة مسبقاً لمنع أي خطأ في الأعمدة
                    cur.execute("""
                        ALTER TABLE banned_devices ADD COLUMN IF NOT EXISTS banned_user_id VARCHAR(128);
                        ALTER TABLE banned_devices ADD COLUMN IF NOT EXISTS banned_by VARCHAR(128);

                        ALTER TABLE processed_txs ADD COLUMN IF NOT EXISTS id TEXT DEFAULT md5(random()::text || clock_timestamp()::text);
                        ALTER TABLE processed_txs ADD COLUMN IF NOT EXISTS tx_hash VARCHAR(256) DEFAULT md5(random()::text || clock_timestamp()::text);
                        ALTER TABLE processed_txs ADD COLUMN IF NOT EXISTS tx_id TEXT;
                        ALTER TABLE processed_txs ADD COLUMN IF NOT EXISTS tg_id VARCHAR(128);
                        ALTER TABLE processed_txs ADD COLUMN IF NOT EXISTS user_id VARCHAR(128);
                        ALTER TABLE processed_txs ADD COLUMN IF NOT EXISTS coins NUMERIC DEFAULT 0.0;
                        ALTER TABLE processed_txs ADD COLUMN IF NOT EXISTS amount NUMERIC DEFAULT 0.0;
                        ALTER TABLE processed_txs ADD COLUMN IF NOT EXISTS fee_usd NUMERIC DEFAULT 0.02;
                        ALTER TABLE processed_txs ADD COLUMN IF NOT EXISTS net_coins NUMERIC DEFAULT 0.0;
                        ALTER TABLE processed_txs ADD COLUMN IF NOT EXISTS currency VARCHAR(32) DEFAULT 'ZNX';
                        ALTER TABLE processed_txs ADD COLUMN IF NOT EXISTS tier_name TEXT DEFAULT '';
                        ALTER TABLE processed_txs ADD COLUMN IF NOT EXISTS wallet_address TEXT DEFAULT '';
                        ALTER TABLE processed_txs ADD COLUMN IF NOT EXISTS type VARCHAR(64) DEFAULT 'withdraw';
                        ALTER TABLE processed_txs ADD COLUMN IF NOT EXISTS status VARCHAR(50) DEFAULT 'pending';
                        ALTER TABLE processed_txs ADD COLUMN IF NOT EXISTS processed_by TEXT;
                        ALTER TABLE processed_txs ADD COLUMN IF NOT EXISTS failure_reason TEXT;
                        ALTER TABLE processed_txs ADD COLUMN IF NOT EXISTS processing_started_at TIMESTAMPTZ;
                        ALTER TABLE processed_txs ADD COLUMN IF NOT EXISTS processed_at TIMESTAMPTZ;
                        ALTER TABLE processed_txs ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP;

                        ALTER TABLE transactions ADD COLUMN IF NOT EXISTS tx_id TEXT;
                        ALTER TABLE transactions ADD COLUMN IF NOT EXISTS tx_hash TEXT;
                        ALTER TABLE transactions ADD COLUMN IF NOT EXISTS user_id TEXT;
                        ALTER TABLE transactions ADD COLUMN IF NOT EXISTS tg_id TEXT;
                        ALTER TABLE transactions ADD COLUMN IF NOT EXISTS coins NUMERIC DEFAULT 0.0;
                        ALTER TABLE transactions ADD COLUMN IF NOT EXISTS amount NUMERIC DEFAULT 0.0;
                        ALTER TABLE transactions ADD COLUMN IF NOT EXISTS fee NUMERIC DEFAULT 0.0;
                        ALTER TABLE transactions ADD COLUMN IF NOT EXISTS fee_usd NUMERIC DEFAULT 0.0;
                        ALTER TABLE transactions ADD COLUMN IF NOT EXISTS net_coins NUMERIC DEFAULT 0.0;
                        ALTER TABLE transactions ADD COLUMN IF NOT EXISTS net_amount NUMERIC DEFAULT 0.0;
                        ALTER TABLE transactions ADD COLUMN IF NOT EXISTS currency TEXT DEFAULT 'ZNX';
                        ALTER TABLE transactions ADD COLUMN IF NOT EXISTS tier_name TEXT DEFAULT '';
                        ALTER TABLE transactions ADD COLUMN IF NOT EXISTS wallet_address TEXT DEFAULT '';
                        ALTER TABLE transactions ADD COLUMN IF NOT EXISTS network TEXT DEFAULT 'TON';
                        ALTER TABLE transactions ADD COLUMN IF NOT EXISTS type TEXT DEFAULT 'withdraw';
                        ALTER TABLE transactions ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'pending';
                        ALTER TABLE transactions ADD COLUMN IF NOT EXISTS processed_by TEXT;
                        ALTER TABLE transactions ADD COLUMN IF NOT EXISTS details TEXT DEFAULT '';
                        ALTER TABLE transactions ADD COLUMN IF NOT EXISTS failure_reason TEXT;
                        ALTER TABLE transactions ADD COLUMN IF NOT EXISTS processed_at TIMESTAMPTZ;
                        ALTER TABLE transactions ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP;

                        ALTER TABLE withdraw_requests ADD COLUMN IF NOT EXISTS tx_id TEXT;
                        ALTER TABLE withdraw_requests ADD COLUMN IF NOT EXISTS tg_id VARCHAR(255);
                        ALTER TABLE withdraw_requests ADD COLUMN IF NOT EXISTS coins NUMERIC(18, 4) DEFAULT 0.0;
                        ALTER TABLE withdraw_requests ADD COLUMN IF NOT EXISTS amount NUMERIC(18, 4) DEFAULT 0.0;
                        ALTER TABLE withdraw_requests ADD COLUMN IF NOT EXISTS fee NUMERIC(18, 4) DEFAULT 0.0;
                        ALTER TABLE withdraw_requests ADD COLUMN IF NOT EXISTS fee_usd NUMERIC(18, 4) DEFAULT 0.02;
                        ALTER TABLE withdraw_requests ADD COLUMN IF NOT EXISTS net_coins NUMERIC(18, 4) DEFAULT 0.0;
                        ALTER TABLE withdraw_requests ADD COLUMN IF NOT EXISTS net_amount NUMERIC(18, 4) DEFAULT 0.0;
                        ALTER TABLE withdraw_requests ADD COLUMN IF NOT EXISTS currency VARCHAR(32) DEFAULT 'ZNX';
                        ALTER TABLE withdraw_requests ADD COLUMN IF NOT EXISTS tier_name TEXT DEFAULT '';
                        ALTER TABLE withdraw_requests ADD COLUMN IF NOT EXISTS wallet_address TEXT;
                        ALTER TABLE withdraw_requests ADD COLUMN IF NOT EXISTS network VARCHAR(32) DEFAULT 'TON';
                        ALTER TABLE withdraw_requests ADD COLUMN IF NOT EXISTS status VARCHAR(50) DEFAULT 'pending';
                        ALTER TABLE withdraw_requests ADD COLUMN IF NOT EXISTS tx_hash TEXT;
                        ALTER TABLE withdraw_requests ADD COLUMN IF NOT EXISTS processed_by TEXT;
                        ALTER TABLE withdraw_requests ADD COLUMN IF NOT EXISTS failure_reason TEXT;
                        ALTER TABLE withdraw_requests ADD COLUMN IF NOT EXISTS admin_note TEXT;
                        ALTER TABLE withdraw_requests ADD COLUMN IF NOT EXISTS details TEXT;
                        ALTER TABLE withdraw_requests ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP;
                        ALTER TABLE withdraw_requests ADD COLUMN IF NOT EXISTS processed_at TIMESTAMPTZ;
                    """)

                    # ضمان وجود قيم افتراضية للأعمدة الأساسية في processed_txs وتحويل details إلى TEXT ليقبل النصوص والـ JSON معاً
                    try:
                        cur.execute("""
                            ALTER TABLE processed_txs ALTER COLUMN tx_hash SET DEFAULT md5(random()::text || clock_timestamp()::text);
                            ALTER TABLE processed_txs ALTER COLUMN id SET DEFAULT md5(random()::text || clock_timestamp()::text);
                            ALTER TABLE processed_txs ALTER COLUMN details TYPE TEXT USING details::TEXT;
                        """)
                    except Exception:
                        pass

                _schema_initialized = True
                print("⚡ [Supabase Setup] تم التحقق من الجداول والمخطط وترقيتها بنجاح!")
            except Exception as e:
                print(f"⚠️ خطأ أثناء إنشاء/تحديث الجداول: {e}")
            finally:
                if conn:
                    db_pool.putconn(conn)

    return db_pool


@contextmanager
def get_db_connection():
    """مستلم اتصالات ذكي يفحص صلاحية الاتصال ويستبدله فوراً إذا أغلقته Supabase (وضع Autocommit للاستعلامات السريعة)"""
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
                if not conn.closed and not broken:
                    conn.autocommit = True
                pool_obj.putconn(conn, close=broken or bool(conn.closed))
            except Exception:
                pass


@contextmanager
def get_db_transaction():
    """
    مدير معاملات ذرية مغلقة (Atomic Transaction) للعمليات المالية الحساسة.
    يفعل وضع المعاملة (autocommit = False)، ويقوم بعمل commit عند النجاح أو rollback فوري عند أي خطأ،
    ويدعم قفل الصفوف عبر SELECT ... FOR UPDATE لمنع الـ Race Conditions والغش.
    """
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

    try:
        conn.autocommit = False
        yield conn
        conn.commit()
    except (psycopg2.OperationalError, psycopg2.InterfaceError) as e:
        broken = True
        try:
            if not conn.closed:
                conn.rollback()
        except Exception:
            pass
        raise e
    except Exception as e:
        try:
            if not conn.closed:
                conn.rollback()
        except Exception:
            pass
        raise e
    finally:
        if conn:
            try:
                if not conn.closed and not broken:
                    conn.autocommit = True
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
                    d['ad_balance'] = float(d.get('ad_balance') or 0.0)
                    d['usd_balance'] = float(d.get('usd_balance') or 0.0)
                    d['znx_balance'] = float(d.get('znx_balance') or 0.0)
                    return d
                return None
    except Exception as e:
        print(f"❌ خطأ get_user: {e}")
        return None


def get_user_balances(telegram_id):
    """دالة مخصصة وسريعة لجلب الأرصدة الأربعة من Supabase"""
    clean_id = _sanitize_id(telegram_id)
    if not clean_id:
        return {'zn_balance': 0.0, 'usdt_balance': 0.0, 'znx_balance': 0.0, 'ad_balance': 0.0}
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT COALESCE(balance, 0.0), COALESCE(usd_balance, 0.0), COALESCE(znx_balance, 0.0), COALESCE(ad_balance, 0.0)
                    FROM users 
                    WHERE tg_id = %s OR user_id = %s OR telegram_id = %s
                    LIMIT 1
                """, (clean_id, clean_id, clean_id))
                row = cur.fetchone()
                if row:
                    return {
                        'zn_balance': float(row[0] or 0.0),
                        'usdt_balance': float(row[1] or 0.0),
                        'znx_balance': float(row[2] or 0.0),
                        'ad_balance': float(row[3] or 0.0)
                    }
                return {'zn_balance': 0.0, 'usdt_balance': 0.0, 'znx_balance': 0.0, 'ad_balance': 0.0}
    except Exception as e:
        print(f"❌ خطأ get_user_balances: {e}")
        return {'zn_balance': 0.0, 'usdt_balance': 0.0, 'znx_balance': 0.0, 'ad_balance': 0.0}


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
                    SELECT COALESCE(is_banned, FALSE) OR COALESCE(banned, FALSE) FROM users
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
                    return {"allowed": False, "banned": True, "reason": "هذا الجهاز محظور"}
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
            SET {', '.join(set_clauses)}, last_active_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
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


def atomic_update_balance(telegram_id, amount_change, is_usd=False, is_znx=False, is_ad=False):
    """تحديث ذري ولحظي للأرصدة في Supabase وإرجاع الرصيد الجديد الفعلي مع حماية من القيم غير الصالحة"""
    clean_id = _sanitize_id(telegram_id)
    if not clean_id:
        return False, 0.0
    col = 'ad_balance' if is_ad else ('znx_balance' if is_znx else ('usd_balance' if is_usd else 'balance'))
    try:
        delta = float(amount_change)
        if not math.isfinite(delta):
            return False, 0.0
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f"""
                    UPDATE users
                    SET {col} = GREATEST(0.0, COALESCE({col}, 0.0) + %s),
                        last_active_at = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
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


# ==================== دوال الإدارة والمشرفين والسجلات (Admin & Moderators) ====================

def is_admin_or_mod(telegram_id):
    """التحقق مما إذا كان المستخدم أدمن رئيسي أو مشرف معتمد في قاعدة البيانات"""
    clean_id = _sanitize_id(telegram_id)
    if not clean_id:
        return False
    admin_env = os.environ.get("ADMIN_ID", "5102387551").strip()
    if clean_id == admin_env:
        return True
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM moderators WHERE tg_id = %s LIMIT 1", (clean_id,))
                if cur.fetchone():
                    return True
                cur.execute("SELECT value FROM settings WHERE key = 'moderators' LIMIT 1")
                row = cur.fetchone()
                if row and row[0]:
                    val = row[0] if isinstance(row[0], (dict, list)) else json.loads(str(row[0]))
                    if isinstance(val, dict) and clean_id in val:
                        return True
                    if isinstance(val, list) and any(str(m.get('id') or m.get('tg_id')) == clean_id for m in val if isinstance(m, dict)):
                        return True
    except Exception as e:
        print(f"⚠️ خطأ فحص صلاحية المشرف is_admin_or_mod: {e}")
    return False


def get_moderators():
    """جلب قائمة المشرفين المعتمدين"""
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT tg_id AS id, name, permissions, added_by AS \"addedBy\", created_at FROM moderators ORDER BY created_at DESC")
                rows = [dict(r) for r in cur.fetchall()]
                for r in rows:
                    if isinstance(r.get("created_at"), datetime):
                        r["created_at"] = format_iso(r["created_at"])
                return rows
    except Exception as e:
        print(f"⚠️ خطأ جلب المشرفين get_moderators: {e}")
        return []


def add_moderator(mod_id, mod_name, permissions=None, added_by="المدير العام"):
    """إضافة أو تحديث مشرف في جدول moderators"""
    clean_id = _sanitize_id(mod_id)
    if not clean_id or not mod_name:
        return False
    perms = permissions if isinstance(permissions, dict) else {}
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO moderators (tg_id, name, permissions, added_by)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (tg_id) DO UPDATE
                    SET name = EXCLUDED.name,
                        permissions = EXCLUDED.permissions,
                        added_by = EXCLUDED.added_by;
                """, (clean_id, str(mod_name).strip(), Json(perms), str(added_by or "المدير العام")))
        return True
    except Exception as e:
        print(f"⚠️ خطأ إضافة مشرف add_moderator: {e}")
        return False


def delete_moderator(mod_id, deleted_by="المدير العام"):
    """حذف مشرف من جدول moderators"""
    clean_id = _sanitize_id(mod_id)
    if not clean_id:
        return False
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM moderators WHERE tg_id = %s", (clean_id,))
        return True
    except Exception as e:
        print(f"⚠️ خطأ حذف مشرف delete_moderator: {e}")
        return False


def get_admin_logs(limit=50):
    """جلب سجل عمليات الإدارة من جدول admin_logs"""
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM admin_logs
                    ORDER BY created_at DESC
                    LIMIT %s
                """, (int(limit),))
                rows = [dict(r) for r in cur.fetchall()]
                for r in rows:
                    if isinstance(r.get("created_at"), datetime):
                        r["created_at"] = format_iso(r["created_at"])
                    if r.get("amount") is not None:
                        r["amount"] = float(r["amount"] or 0.0)
                return rows
    except Exception as e:
        print(f"⚠️ خطأ جلب سجلات الإدارة get_admin_logs: {e}")
        return []


def get_system_global_analytics():
    """جلب إحصائيات لوحة التحكم الشاملة من Supabase"""
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT
                        COUNT(*) AS total_users,
                        COUNT(*) FILTER (WHERE COALESCE(is_banned, FALSE) = TRUE OR COALESCE(banned, FALSE) = TRUE) AS banned_users,
                        COUNT(*) FILTER (WHERE last_active_at >= NOW() - INTERVAL '24 hours') AS active_today,
                        COALESCE(SUM(balance), 0.0) AS total_circulating_zn,
                        COALESCE(SUM(znx_balance), 0.0) AS total_circulating_znx,
                        COALESCE(SUM(usd_balance), 0.0) AS total_circulating_usd
                    FROM users;
                """)
                stats = dict(cur.fetchone() or {})
                cur.execute("""
                    SELECT tg_id, first_name, COALESCE(balance, 0.0) AS balance, COALESCE(znx_balance, 0.0) AS znx_balance, COALESCE(interactions, 0) AS interactions
                    FROM users
                    WHERE COALESCE(is_banned, FALSE) = FALSE
                    ORDER BY COALESCE(interactions, 0) DESC
                    LIMIT 10;
                """)
                top_users = [dict(r) for r in cur.fetchall()]
                return {
                    "total_users": int(stats.get("total_users") or 0),
                    "active_today": int(stats.get("active_today") or 0),
                    "banned_users": int(stats.get("banned_users") or 0),
                    "total_circulating_zn": float(stats.get("total_circulating_zn") or 0.0),
                    "total_circulating_znx": float(stats.get("total_circulating_znx") or 0.0),
                    "total_circulating_usd": float(stats.get("total_circulating_usd") or 0.0),
                    "top_active_users": top_users
                }
    except Exception as e:
        print(f"⚠️ خطأ get_system_global_analytics: {e}")
        return {"total_users": 0, "active_today": 0, "banned_users": 0, "total_circulating_zn": 0.0, "top_active_users": []}


def get_admin_dashboard_stats():
    return get_system_global_analytics()


# تشغيل التهيئة الأولية عند الاستيراد
try:
    init_db_pool()
except Exception as e:
    print(f"⚠️ تنبيه الإقلاع: {e}")
