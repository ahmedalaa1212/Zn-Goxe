# -*- coding: utf-8 -*-
"""
database.py - النسخة النموذجية المجردة والخفيفة جداً
هدفها: تجربة الاتصال السريع بـ Supabase وإنشاء الجداول فقط بدون أي موديولات إضافية
"""
import os
import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager

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
            connect_timeout=3
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

                    -- جدول الإعدادات العامة (لحفظ إعدادات المزرعة، اليوميات، إلخ)
                    CREATE TABLE IF NOT EXISTS settings (
                        key VARCHAR(128) PRIMARY KEY,
                        value JSONB DEFAULT '{}'::jsonb,
                        updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                    );

                    -- تحديث جدول users ليكون جاهزاً لكافة بيانات التعدين والمزرعة
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS hourly_rate DOUBLE PRECISION DEFAULT 0.10;
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS mined_points DOUBLE PRECISION DEFAULT 0.0;
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS total_mined DOUBLE PRECISION DEFAULT 0.0;
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS storage_level INT DEFAULT 0;
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
                """)
            print("⚡ [Supabase Setup] تم إنشاء الجداول الأساسية وتحديث مخطط البيانات بنجاح وفوراً!")
        except Exception as e:
            print(f"⚠️ خطأ أثناء إنشاء/تحديث الجداول: {e}")
        finally:
            db_pool.putconn(conn)

    return db_pool


@contextmanager
def get_db_connection():
    """مستلم اتصالات خفيف ومباشر"""
    pool_obj = init_db_pool()
    conn = pool_obj.getconn()
    try:
        conn.autocommit = True
        yield conn
    finally:
        if conn:
            pool_obj.putconn(conn)


def get_db():
    return init_db_pool()


# ==================== Core Minimal Functions (لمنع كسر Flask) ====================

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
                    if d.get('created_at'): d['created_at'] = str(d['created_at'])
                    if d.get('last_active_at'): d['last_active_at'] = str(d['last_active_at'])
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
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO users (tg_id, user_id, telegram_id, first_name)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (tg_id) DO NOTHING;
                    """, (clean_id, clean_id, clean_id, str(first_name or 'لاعب')))
            return get_user(clean_id) or {}
        return existing
    except Exception as e:
        print(f"❌ خطأ init_user: {e}")
        return {}


def is_user_banned(telegram_id):
    return False


def check_and_bind_device(telegram_id, device_id, fingerprint_hash=None):
    return {"allowed": True}


def update_user(telegram_id, updates_dict):
    return True


def update_user_last_active(user_id):
    return True


def atomic_update_balance(telegram_id, amount_change, is_usd=False):
    return True, 0.0


def get_leaderboard_data(limit=50, user_id=None):
    return {"success": True, "leaderboard": [], "my_rank": "غير مصنف"}


def get_user_data(telegram_id):
    return get_user(telegram_id)


# تشغيل التهيئة الأولية عند الاستيراد
try:
    init_db_pool()
except Exception as e:
    print(f"⚠️ تنبيه الإقلاع: {e}")
