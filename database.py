# -*- coding: utf-8 -*-
"""
database.py - النسخة الكاملة والمؤمنة لإدارة قاعدة بيانات Supabase (PostgreSQL)
مزودة بنظام كشف وحظر تعدد الحسابات وبصمة الجهاز تلقائياً (Multi-Account & Fingerprint Anti-Cheat)،
فحص تلقائي للاتصالات (Auto-Heal Pool)، والمعاملات الذرية الآمنة (Atomic Transactions) ⚡
"""
import os
import re
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


# ==================== القائمة البيضاء لأعمدة جدول users لمنع SQL Injection ====================
ALLOWED_USER_COLUMNS = {
    "user_id", "telegram_id", "first_name", "name", "username",
    "balance", "ad_balance", "usd_balance", "znx_balance",
    "wallet_address", "wallets", "ref_by", "referred_by",
    "referrals_count", "ref_count", "referral_count",
    "pending_ref_earnings", "total_ref_earnings", "claimed_ref_tasks",
    "last_active_at", "interactions", "is_banned", "banned", "ban",
    "status", "ban_reason", "banned_at", "banned_by", "unbanned_at", "unbanned_by",
    "farm_level", "storage_level", "device_id", "fingerprint_hash",
    "hourly_rate", "mined_points", "total_mined", "extra_storage", "max_cap",
    "last_claim_time", "last_daily_claim_date", "daily_day", "daily_streak",
    "last_boost_time", "upgrades", "upgrades_count", "welcome_seen",
    "ads_watched", "bot_active", "bot_expires_at", "boost_claims_count",
    "boost_history", "daily_claims_count", "daily_history", "vip_status",
    "is_vip", "vip_active", "plan", "vip_package", "vip_level",
    "vip_expires", "vip_expires_at", "expires_at", "completed_tasks",
    "total_bets", "total_wins", "total_losses", "tap_count"
}

_SAFE_COL_REGEX = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')


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
                            status VARCHAR(32) DEFAULT 'active',
                            ban_reason TEXT,
                            banned_at TIMESTAMPTZ,
                            banned_by VARCHAR(128),
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
                            is_banned BOOLEAN DEFAULT FALSE,
                            ban_reason TEXT,
                            banned_at TIMESTAMPTZ,
                            banned_by VARCHAR(128)
                        );

                        CREATE TABLE IF NOT EXISTS banned_devices (
                            device_id VARCHAR(256) PRIMARY KEY,
                            fingerprint_hash VARCHAR(256),
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
                            role VARCHAR(50) DEFAULT 'moderator',
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
                            failed_count INT DEFAULT 0,
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

                        -- ==================== ترقية أعمدة جدول المستخدمين والأجهزة تلقائياً ====================
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
                        ALTER TABLE users ADD COLUMN IF NOT EXISTS status VARCHAR(32) DEFAULT 'active';
                        ALTER TABLE users ADD COLUMN IF NOT EXISTS ban_reason TEXT;
                        ALTER TABLE users ADD COLUMN IF NOT EXISTS banned_at TIMESTAMPTZ;
                        ALTER TABLE users ADD COLUMN IF NOT EXISTS banned_by VARCHAR(128);
                        ALTER TABLE users ADD COLUMN IF NOT EXISTS unbanned_at TIMESTAMPTZ;
                        ALTER TABLE users ADD COLUMN IF NOT EXISTS unbanned_by VARCHAR(128);
                        ALTER TABLE users ADD COLUMN IF NOT EXISTS device_id VARCHAR(256);
                        ALTER TABLE users ADD COLUMN IF NOT EXISTS fingerprint_hash VARCHAR(256);
                        ALTER TABLE users ADD COLUMN IF NOT EXISTS total_bets DOUBLE PRECISION DEFAULT 0.0;
                        ALTER TABLE users ADD COLUMN IF NOT EXISTS total_wins DOUBLE PRECISION DEFAULT 0.0;
                        ALTER TABLE users ADD COLUMN IF NOT EXISTS total_losses DOUBLE PRECISION DEFAULT 0.0;
                        ALTER TABLE users ADD COLUMN IF NOT EXISTS tap_count INT DEFAULT 0;
                        ALTER TABLE users ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP;

                        CREATE INDEX IF NOT EXISTS idx_users_ref_by ON users(ref_by);
                        CREATE INDEX IF NOT EXISTS idx_users_referred_by ON users(referred_by);
                        CREATE INDEX IF NOT EXISTS idx_users_user_id ON users(user_id);
                        CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id);
                        CREATE INDEX IF NOT EXISTS idx_users_device_id ON users(device_id);
                        CREATE INDEX IF NOT EXISTS idx_users_fingerprint_hash ON users(fingerprint_hash);
                    """)

                    # ترقية جداول الأجهزة والحظر والمعاملات
                    cur.execute("""
                        ALTER TABLE devices ADD COLUMN IF NOT EXISTS fingerprint_hash VARCHAR(256);
                        ALTER TABLE devices ADD COLUMN IF NOT EXISTS is_banned BOOLEAN DEFAULT FALSE;
                        ALTER TABLE devices ADD COLUMN IF NOT EXISTS ban_reason TEXT;
                        ALTER TABLE devices ADD COLUMN IF NOT EXISTS banned_at TIMESTAMPTZ;
                        ALTER TABLE devices ADD COLUMN IF NOT EXISTS banned_by VARCHAR(128);
                        CREATE INDEX IF NOT EXISTS idx_devices_fingerprint ON devices(fingerprint_hash);
                        CREATE INDEX IF NOT EXISTS idx_devices_primary_user ON devices(primary_user_id);

                        ALTER TABLE banned_devices ADD COLUMN IF NOT EXISTS fingerprint_hash VARCHAR(256);
                        ALTER TABLE banned_devices ADD COLUMN IF NOT EXISTS banned_user_id VARCHAR(128);
                        ALTER TABLE banned_devices ADD COLUMN IF NOT EXISTS banned_by VARCHAR(128);
                        CREATE INDEX IF NOT EXISTS idx_banned_devices_fp ON banned_devices(fingerprint_hash);
                        CREATE INDEX IF NOT EXISTS idx_banned_devices_user ON banned_devices(banned_user_id);

                        ALTER TABLE moderators ADD COLUMN IF NOT EXISTS role VARCHAR(50) DEFAULT 'moderator';
                        ALTER TABLE broadcasts ADD COLUMN IF NOT EXISTS failed_count INT DEFAULT 0;

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
                if not conn.closed and not broken:
                    conn.autocommit = True
                pool_obj.putconn(conn, close=broken or bool(conn.closed))
            except Exception:
                pass


@contextmanager
def get_db_transaction():
    """مدير معاملات ذرية مغلقة (Atomic Transaction) للعمليات المالية الحساسة ومنع Race Conditions"""
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


def is_admin_exempt(telegram_id):
    """التحقق مما إذا كان الحساب هو حساب المالك/الأدمن الرئيسي لإعفائه من الحظر التلقائي"""
    clean_id = _sanitize_id(telegram_id)
    if not clean_id:
        return False
    admin_env = os.environ.get("ADMIN_ID", "5102387551").strip()
    super_admin_env = os.environ.get("SUPER_ADMIN_ID", "").strip()
    return clean_id in (admin_env, super_admin_env, "5102387551")


def log_admin_action(admin_name, details, user_id=None, action="admin_action", tx_id=None, amount=0.0, status="completed"):
    """تسجيل العمليات الإدارية وعمليات الحظر التلقائي في جدول admin_logs"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO admin_logs (action, tx_id, user_id, admin_id, admin_name, status, amount, details, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                """, (
                    str(action or "admin_action"),
                    str(tx_id) if tx_id else None,
                    str(user_id) if user_id else None,
                    str(admin_name or "النظام"),
                    str(admin_name or "النظام"),
                    str(status or "completed"),
                    float(amount or 0.0),
                    str(details or "")
                ))
        return True
    except Exception as e:
        print(f"⚠️ خطأ أثناء تسجيل حركة الأدمن log_admin_action: {e}")
        return False


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
                        cur.execute("SELECT ref_by, referred_by, is_banned, banned FROM users WHERE tg_id = %s LIMIT 1", (clean_ref,))
                        ref_row = cur.fetchone()
                        if ref_row and (ref_row[0] == clean_id or ref_row[1] == clean_id or ref_row[2] or ref_row[3]):
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
                        cur.execute("SELECT ref_by, referred_by, is_banned, banned FROM users WHERE tg_id = %s LIMIT 1", (clean_ref,))
                        ref_row = cur.fetchone()
                        if not (ref_row and (ref_row[0] == clean_id or ref_row[1] == clean_id or ref_row[2] or ref_row[3])):
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
    """فحص شامل وسريع لحالة حظر المستخدم أو جهازه"""
    clean_id = _sanitize_id(telegram_id)
    if not clean_id:
        return False
    if is_admin_exempt(clean_id):
        return False
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT
                        COALESCE(is_banned, FALSE) OR COALESCE(banned, FALSE) OR (status = 'banned'),
                        device_id,
                        fingerprint_hash
                    FROM users
                    WHERE tg_id = %s OR user_id = %s OR telegram_id = %s
                    LIMIT 1
                """, (clean_id, clean_id, clean_id))
                row = cur.fetchone()
                if not row:
                    return False
                if bool(row[0]):
                    return True
                dev_id = row[1]
                fp_hash = row[2]
                if dev_id or fp_hash:
                    cur.execute("""
                        SELECT 1 FROM banned_devices
                        WHERE (device_id IS NOT NULL AND device_id = %s)
                           OR (fingerprint_hash IS NOT NULL AND fingerprint_hash = %s)
                           OR (banned_user_id IS NOT NULL AND banned_user_id = %s)
                        LIMIT 1
                    """, (str(dev_id or ''), str(fp_hash or ''), clean_id))
                    if cur.fetchone():
                        return True
                return False
    except Exception:
        return False


def check_and_bind_device(telegram_id, device_id, fingerprint_hash=None):
    """
    نظام الحماية الصارم لمنع تعدد الحسابات (1 جهاز / متصفح = 1 حساب فقط):
    - يفحص معرّف الجهاز (device_id) وبصمة العتاد الصلبة (fingerprint_hash) التي تكشف المتصفحات الأخرى والوضع الخفي.
    - إذا تم اكتشاف أي حساب آخر يستخدم نفس الجهاز أو نفس البصمة: يتم فوراً حظر جميع الحسابات المشتركة وحظر الجهاز والبصمة.
    """
    clean_id = _sanitize_id(telegram_id)
    clean_dev = str(device_id).strip() if device_id and str(device_id).strip().lower() not in ("none", "null", "undefined", "") else None
    clean_fp = str(fingerprint_hash).strip() if fingerprint_hash and str(fingerprint_hash).strip().lower() not in ("none", "null", "undefined", "") else None

    if not clean_id:
        return {"allowed": False, "banned": True, "reason": "معرف المستخدم غير صالح"}

    # إعفاء الأدمن الرئيسي من الحظر التلقائي
    if is_admin_exempt(clean_id):
        return {"allowed": True, "banned": False}

    # إذا لم يتم إرسال أي بصمة أو معرف جهاز، نتحقق فقط من حالة حظر الحساب
    if not clean_dev and not clean_fp:
        if is_user_banned(clean_id):
            return {"allowed": False, "banned": True, "reason": "حسابك محظور لمخالفة شروط الاستخدام."}
        return {"allowed": True, "banned": False}

    effective_dev_id = clean_dev or f"fp_dev_{clean_fp}"

    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # 1. التأكد من وجود سجل للمستخدم أولاً
                cur.execute("""
                    SELECT tg_id, is_banned, banned, status, ban_reason, device_id, fingerprint_hash
                    FROM users
                    WHERE tg_id = %s OR user_id = %s OR telegram_id = %s
                    LIMIT 1
                """, (clean_id, clean_id, clean_id))
                user_row = cur.fetchone()

                if user_row and (user_row.get("is_banned") or user_row.get("banned") or user_row.get("status") == "banned"):
                    return {
                        "allowed": False,
                        "banned": True,
                        "reason": user_row.get("ban_reason") or "تم حظر هذا الحساب والجهاز لمخالفة القوانين."
                    }

                # 2. فحص هل الجهاز أو البصمة مدرج مسبقاً في banned_devices أو محظور في devices
                cur.execute("""
                    SELECT device_id, fingerprint_hash, banned_user_id, reason
                    FROM banned_devices
                    WHERE device_id = %s
                       OR (%s IS NOT NULL AND device_id = %s)
                       OR (%s IS NOT NULL AND fingerprint_hash = %s)
                    LIMIT 1
                """, (effective_dev_id, clean_fp, clean_fp, clean_fp, clean_fp))
                banned_dev_row = cur.fetchone()

                if banned_dev_row:
                    ban_reason = banned_dev_row.get("reason") or "تم حظر حسابك تلقائياً لمحاولة الدخول من جهاز/متصفح محظور بسبب تعدد الحسابات."
                    cur.execute("""
                        UPDATE users
                        SET is_banned = TRUE,
                            banned = TRUE,
                            status = 'banned',
                            ban_reason = %s,
                            device_id = COALESCE(device_id, %s),
                            fingerprint_hash = COALESCE(fingerprint_hash, %s),
                            banned_at = CURRENT_TIMESTAMP,
                            banned_by = 'النظام الأمني التلقائي',
                            updated_at = CURRENT_TIMESTAMP
                        WHERE tg_id = %s OR user_id = %s OR telegram_id = %s
                    """, (ban_reason, effective_dev_id, clean_fp, clean_id, clean_id, clean_id))
                    return {"allowed": False, "banned": True, "reason": ban_reason}

                # 3. البحث الشامل عن أي حسابات أخرى مرتبطة بنفس الـ device_id أو نفس الـ fingerprint_hash
                associated_users = set()
                associated_devices = {effective_dev_id}
                if clean_fp:
                    associated_fps = {clean_fp}
                else:
                    associated_fps = set()

                # أ) فحص جدول users عن أي مستخدم آخر يملك نفس device_id أو نفس fingerprint_hash
                if clean_dev and clean_fp:
                    cur.execute("""
                        SELECT tg_id, device_id, fingerprint_hash FROM users
                        WHERE (device_id = %s OR fingerprint_hash = %s)
                    """, (clean_dev, clean_fp))
                elif clean_dev:
                    cur.execute("""
                        SELECT tg_id, device_id, fingerprint_hash FROM users
                        WHERE device_id = %s
                    """, (clean_dev,))
                else:
                    cur.execute("""
                        SELECT tg_id, device_id, fingerprint_hash FROM users
                        WHERE fingerprint_hash = %s
                    """, (clean_fp,))

                for r in cur.fetchall():
                    uid = _sanitize_id(r.get("tg_id"))
                    if uid and not is_admin_exempt(uid):
                        associated_users.add(uid)
                    if r.get("device_id"):
                        associated_devices.add(str(r["device_id"]).strip())
                    if r.get("fingerprint_hash"):
                        associated_fps.add(str(r["fingerprint_hash"]).strip())

                # ب) فحص جدول devices عن أي سجل يطابق device_id أو fingerprint_hash
                if clean_dev and clean_fp:
                    cur.execute("""
                        SELECT device_id, primary_user_id, users, fingerprint_hash, is_banned
                        FROM devices
                        WHERE device_id = %s OR fingerprint_hash = %s
                    """, (clean_dev, clean_fp))
                elif clean_dev:
                    cur.execute("""
                        SELECT device_id, primary_user_id, users, fingerprint_hash, is_banned
                        FROM devices
                        WHERE device_id = %s
                    """, (clean_dev,))
                else:
                    cur.execute("""
                        SELECT device_id, primary_user_id, users, fingerprint_hash, is_banned
                        FROM devices
                        WHERE fingerprint_hash = %s
                    """, (clean_fp,))

                for d_row in cur.fetchall():
                    if d_row.get("device_id"):
                        associated_devices.add(str(d_row["device_id"]).strip())
                    if d_row.get("fingerprint_hash"):
                        associated_fps.add(str(d_row["fingerprint_hash"]).strip())
                    p_uid = _sanitize_id(d_row.get("primary_user_id"))
                    if p_uid and not is_admin_exempt(p_uid):
                        associated_users.add(p_uid)
                    u_list = d_row.get("users")
                    if isinstance(u_list, list):
                        for u_item in u_list:
                            s_uid = _sanitize_id(u_item)
                            if s_uid and not is_admin_exempt(s_uid):
                                associated_users.add(s_uid)

                # إزالة المستخدم الحالي لمعرفة هل يوجد حسابات أخرى غيره على نفس الجهاز/المتصفح
                other_users = {u for u in associated_users if u != clean_id}

                # 4. إذا تم اكتشاف أكثر من حساب على نفس الجهاز أو البصمة -> حظر جماعي فوري لكل الحسابات والأجهزة!
                if len(other_users) > 0:
                    all_offending_users = sorted(list(other_users | {clean_id}))
                    accounts_str = ", ".join(all_offending_users)
                    ban_reason = f"حظر تلقائي لتعدد الحسابات على نفس الجهاز/المتصفح (الحسابات المشتركة: {accounts_str})"

                    # 4.1 تحديث وحظر جميع الحسابات المشتركة في جدول users
                    cur.execute("""
                        UPDATE users
                        SET is_banned = TRUE,
                            banned = TRUE,
                            status = 'banned',
                            ban_reason = %s,
                            device_id = COALESCE(device_id, %s),
                            fingerprint_hash = COALESCE(fingerprint_hash, %s),
                            banned_at = CURRENT_TIMESTAMP,
                            banned_by = 'النظام الأمني التلقائي',
                            updated_at = CURRENT_TIMESTAMP
                        WHERE tg_id = ANY(%s) OR user_id = ANY(%s) OR telegram_id = ANY(%s)
                    """, (ban_reason, effective_dev_id, clean_fp, all_offending_users, all_offending_users, all_offending_users))

                    # 4.2 تحديث أو إدراج الأجهزة في جدول devices كأجهزة محظورة مع قائمة الحسابات
                    for dev_item in associated_devices:
                        if not dev_item:
                            continue
                        cur.execute("""
                            INSERT INTO devices (device_id, primary_user_id, users, fingerprint_hash, last_seen, is_banned, ban_reason, banned_at, banned_by)
                            VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP, TRUE, %s, CURRENT_TIMESTAMP, 'النظام الأمني التلقائي')
                            ON CONFLICT (device_id) DO UPDATE
                            SET users = %s,
                                fingerprint_hash = COALESCE(devices.fingerprint_hash, EXCLUDED.fingerprint_hash),
                                last_seen = CURRENT_TIMESTAMP,
                                is_banned = TRUE,
                                ban_reason = EXCLUDED.ban_reason,
                                banned_at = CURRENT_TIMESTAMP,
                                banned_by = 'النظام الأمني التلقائي'
                        """, (
                            dev_item,
                            all_offending_users[0],
                            Json(all_offending_users),
                            clean_fp,
                            ban_reason,
                            Json(all_offending_users)
                        ))

                        # 4.3 إدراج الجهاز في جدول banned_devices
                        cur.execute("""
                            INSERT INTO banned_devices (device_id, fingerprint_hash, banned_user_id, reason, banned_by, banned_at)
                            VALUES (%s, %s, %s, %s, 'النظام الأمني التلقائي', CURRENT_TIMESTAMP)
                            ON CONFLICT (device_id) DO UPDATE
                            SET fingerprint_hash = COALESCE(banned_devices.fingerprint_hash, EXCLUDED.fingerprint_hash),
                                banned_user_id = EXCLUDED.banned_user_id,
                                reason = EXCLUDED.reason,
                                banned_by = EXCLUDED.banned_by,
                                banned_at = CURRENT_TIMESTAMP
                        """, (dev_item, clean_fp, clean_id, ban_reason))

                    # 4.4 إدراج البصمات أيضاً في جدول banned_devices لمنع فتح متصفح جديد
                    for fp_item in associated_fps:
                        if not fp_item:
                            continue
                        cur.execute("""
                            INSERT INTO banned_devices (device_id, fingerprint_hash, banned_user_id, reason, banned_by, banned_at)
                            VALUES (%s, %s, %s, %s, 'النظام الأمني التلقائي', CURRENT_TIMESTAMP)
                            ON CONFLICT (device_id) DO UPDATE
                            SET fingerprint_hash = EXCLUDED.fingerprint_hash,
                                reason = EXCLUDED.reason,
                                banned_at = CURRENT_TIMESTAMP
                        """, (fp_item, fp_item, clean_id, ban_reason))

                    # 4.5 توثيق الحظر التلقائي في سجل الأدمن
                    cur.execute("""
                        INSERT INTO admin_logs (action, user_id, admin_id, admin_name, status, details, created_at)
                        VALUES ('auto_ban_multi_account', %s, 'SYSTEM', 'النظام الأمني التلقائي', 'completed', %s, CURRENT_TIMESTAMP)
                    """, (clean_id, ban_reason))

                    return {
                        "allowed": False,
                        "banned": True,
                        "reason": ban_reason
                    }

                # 5. الوضع السليم (حساب واحد فقط على هذا الجهاز والبصمة) -> ربط الجهاز بالمستخدم وتحديث الظهور
                cur.execute("""
                    UPDATE users
                    SET device_id = %s,
                        fingerprint_hash = COALESCE(%s, fingerprint_hash),
                        last_active_at = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE tg_id = %s OR user_id = %s OR telegram_id = %s
                """, (effective_dev_id, clean_fp, clean_id, clean_id, clean_id))

                cur.execute("""
                    INSERT INTO devices (device_id, primary_user_id, users, fingerprint_hash, created_at, last_seen, is_banned)
                    VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, FALSE)
                    ON CONFLICT (device_id) DO UPDATE
                    SET primary_user_id = COALESCE(devices.primary_user_id, EXCLUDED.primary_user_id),
                        users = %s,
                        fingerprint_hash = COALESCE(EXCLUDED.fingerprint_hash, devices.fingerprint_hash),
                        last_seen = CURRENT_TIMESTAMP
                """, (effective_dev_id, clean_id, Json([clean_id]), clean_fp, Json([clean_id])))

        return {"allowed": True, "banned": False}
    except Exception as e:
        print(f"⚠️ خطأ في فحص بصمة الجهاز check_and_bind_device: {e}")
        return {"allowed": True, "banned": False}


def update_user(telegram_id, updates_dict):
    """تحديث بيانات المستخدم في Supabase بشكل آمن ومفلتر ضد SQL Injection"""
    clean_id = _sanitize_id(telegram_id)
    if not clean_id or not updates_dict or not isinstance(updates_dict, dict):
        return False
    try:
        set_clauses = []
        values = []
        for k, v in updates_dict.items():
            col_name = str(k).strip()
            if col_name == 'tg_id':
                continue
            if col_name not in ALLOWED_USER_COLUMNS or not _SAFE_COL_REGEX.match(col_name):
                print(f"⛔ [Security] تم رفض تحديث عمود غير مصرح به: {col_name}")
                continue
            set_clauses.append(f"{col_name} = %s")
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
                    WHERE (tg_id = %s OR user_id = %s OR telegram_id = %s)
                      AND COALESCE(is_banned, FALSE) = FALSE
                      AND COALESCE(banned, FALSE) = FALSE
                """, (clean_id, clean_id, clean_id))
        return True
    except Exception:
        return False


def atomic_update_balance(telegram_id, amount_change, is_usd=False, is_znx=False, is_ad=False):
    """تحديث ذري ولحظي للأرصدة في Supabase مع منع زيادة أرصدة الحسابات المحظورة"""
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
                    WHERE (tg_id = %s OR user_id = %s OR telegram_id = %s)
                      AND COALESCE(is_banned, FALSE) = FALSE
                      AND COALESCE(banned, FALSE) = FALSE
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
                      AND COALESCE(banned, FALSE) = FALSE
                    ORDER BY COALESCE(balance, 0.0) DESC
                    LIMIT %s
                """, (int(limit),))
                rows = [dict(r) for r in cur.fetchall()]
                my_rank = "غير مصنف"
                if clean_id:
                    cur.execute("""
                        SELECT COUNT(*) + 1 AS rank FROM users
                        WHERE COALESCE(is_banned, FALSE) = FALSE
                          AND COALESCE(banned, FALSE) = FALSE
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
    if is_admin_exempt(clean_id):
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
                cur.execute("""
                    SELECT tg_id AS id, tg_id AS telegram_id, name, COALESCE(role, 'moderator') AS role,
                           permissions, added_by AS "addedBy", created_at
                    FROM moderators
                    ORDER BY created_at DESC
                """)
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
                    INSERT INTO moderators (tg_id, name, role, permissions, added_by)
                    VALUES (%s, %s, 'moderator', %s, %s)
                    ON CONFLICT (tg_id) DO UPDATE
                    SET name = EXCLUDED.name,
                        permissions = EXCLUDED.permissions,
                        added_by = EXCLUDED.added_by;
                """, (clean_id, str(mod_name).strip(), Json(perms), str(added_by or "المدير العام")))
        log_admin_action(added_by, f"إضافة/تحديث المشرف {mod_name} ({clean_id})", user_id=clean_id, action="add_moderator")
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
        log_admin_action(deleted_by, f"حذف المشرف ({clean_id})", user_id=clean_id, action="delete_moderator")
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
                    r["timestamp"] = r.get("created_at") or ""
                    r["admin"] = r.get("admin_name") or r.get("admin_id") or "النظام"
                    if r.get("details") and r.get("action") in ("admin_action", "auto_ban_multi_account", "ban_user", "unban_user"):
                        r["action"] = r["details"]
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
                        COUNT(*) FILTER (WHERE COALESCE(is_banned, FALSE) = TRUE OR COALESCE(banned, FALSE) = TRUE OR status = 'banned') AS banned_users,
                        COUNT(*) FILTER (WHERE last_active_at >= DATE_TRUNC('day', NOW())) AS active_today,
                        COALESCE(SUM(balance), 0.0) AS total_circulating_zn,
                        COALESCE(SUM(ad_balance), 0.0) AS total_ad_balance_zn,
                        COALESCE(SUM(znx_balance), 0.0) AS total_circulating_znx,
                        COALESCE(SUM(usd_balance), 0.0) AS total_circulating_usd
                    FROM users;
                """)
                stats = dict(cur.fetchone() or {})
                cur.execute("""
                    SELECT
                        tg_id,
                        tg_id AS telegram_id,
                        tg_id AS user_id,
                        COALESCE(first_name, name, 'لاعب') AS name,
                        COALESCE(username, '—') AS username,
                        COALESCE(balance, 0.0) AS balance,
                        COALESCE(znx_balance, 0.0) AS znx_balance,
                        COALESCE(interactions, 1) AS interactions,
                        COALESCE(interactions, 1) AS activity_count,
                        COALESCE(is_banned, FALSE) OR COALESCE(banned, FALSE) AS is_banned
                    FROM users
                    WHERE COALESCE(is_banned, FALSE) = FALSE AND COALESCE(banned, FALSE) = FALSE
                    ORDER BY COALESCE(interactions, 0) DESC, COALESCE(balance, 0.0) DESC
                    LIMIT 10;
                """)
                top_users = [dict(r) for r in cur.fetchall()]
                return {
                    "total_users": int(stats.get("total_users") or 0),
                    "active_today": int(stats.get("active_today") or 0),
                    "banned_users": int(stats.get("banned_users") or 0),
                    "total_circulating_zn": round(float(stats.get("total_circulating_zn") or 0.0), 2),
                    "total_ad_balance_zn": round(float(stats.get("total_ad_balance_zn") or 0.0), 2),
                    "total_circulating_znx": round(float(stats.get("total_circulating_znx") or 0.0), 2),
                    "total_circulating_usd": round(float(stats.get("total_circulating_usd") or 0.0), 2),
                    "top_users": top_users,
                    "top_active_users": top_users
                }
    except Exception as e:
        print(f"⚠️ خطأ get_system_global_analytics: {e}")
        return {"total_users": 0, "active_today": 0, "banned_users": 0, "total_circulating_zn": 0.0, "top_users": [], "top_active_users": []}


def get_admin_dashboard_stats():
    return get_system_global_analytics()


# تشغيل التهيئة الأولية عند الاستيراد
try:
    init_db_pool()
except Exception as e:
    print(f"⚠️ تنبيه الإقلاع: {e}")
