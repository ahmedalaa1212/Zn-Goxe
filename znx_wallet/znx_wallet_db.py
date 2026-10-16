# -*- coding: utf-8 -*-
"""
💎 ZNX Wallet Database Module (Supabase Edition)
إدارة عمليات قاعدة البيانات (Supabase PostgreSQL & REST API) الخاصة بمحفظة ZNX
يدعم الإنشاء التلقائي للجداول والفهارس، الكاش الذكي، والمعاملات الذرية (ACID Transactions)
"""

import os
import math
import time
import json
import threading

# محاولة استيراد محركات الاتصال بـ Supabase (PostgreSQL المباشر أو مكتبة Supabase REST)
try:
    import psycopg2
    from psycopg2 import pool
    from psycopg2.extras import RealDictCursor
    HAS_PSYCOPG2 = True
except ImportError:
    HAS_PSYCOPG2 = False

try:
    from supabase import create_client, Client
    HAS_SUPABASE_LIB = True
except ImportError:
    HAS_SUPABASE_LIB = False


# ==================== الثوابت وإعدادات الشرائح ====================

MAX_GLOBAL_ZNX = 32_500_000.0

TIERS_CONFIG = [
    {"tier": 1, "name": "الشريحة الأولى", "min_pts": 0.0, "max_pts": 1_500_000.0, "rate": 10, "quota": 1_500_000, "min_withdraw_znx": 1000.0, "fixed_fee_usd": 0.02},
    {"tier": 2, "name": "الشريحة الثانية", "min_pts": 1_500_000.0, "max_pts": 2_000_000.0, "rate": 30, "quota": 2_000_000, "min_withdraw_znx": 350.0, "fixed_fee_usd": 0.02},
    {"tier": 3, "name": "الشريحة الثالثة", "min_pts": 2_000_000.0, "max_pts": 2_500_000.0, "rate": 80, "quota": 2_500_000, "min_withdraw_znx": 125.0, "fixed_fee_usd": 0.02},
    {"tier": 4, "name": "الشريحة الرابعة", "min_pts": 2_500_000.0, "max_pts": 4_000_000.0, "rate": 200, "quota": 4_000_000, "min_withdraw_znx": 50.0, "fixed_fee_usd": 0.02},
    {"tier": 5, "name": "الشريحة الخامسة", "min_pts": 4_000_000.0, "max_pts": 5_500_000.0, "rate": 600, "quota": 5_500_000, "min_withdraw_znx": 20.0, "fixed_fee_usd": 0.02},
    {"tier": 6, "name": "الشريحة السادسة", "min_pts": 5_500_000.0, "max_pts": 8_000_000.0, "rate": 1600, "quota": 8_000_000, "min_withdraw_znx": 6.0, "fixed_fee_usd": 0.02},
    {"tier": 7, "name": "الشريحة السابعة", "min_pts": 8_000_000.0, "max_pts": "Infinity", "rate": 4000, "quota": 9_000_000, "min_withdraw_znx": 2.5, "fixed_fee_usd": 0.02}
]

# متغيرات الاتصال والكاش الداخلي لتخفيف الضغط عند دخول ملايين المستخدمين
_PG_POOL = None
_SUPABASE_CLIENT = None
_DB_INITIALIZED = False
_INIT_LOCK = threading.Lock()

_GLOBAL_STATS_CACHE = {"data": None, "timestamp": 0.0}
_LEADERBOARD_CACHE = {"top_list": [], "timestamp": 0.0}


# ==================== إدارة الاتصال والإنشاء التلقائي للجداول ====================

def _get_database_url():
    """جلب رابط قاعدة بيانات PostgreSQL الخاص بـ Supabase من متغيرات البيئة"""
    for env_key in ("DATABASE_URL", "SUPABASE_DB_URL", "POSTGRES_URL", "POSTGRES_PRISMA_URL"):
        val = os.environ.get(env_key)
        if val and val.strip():
            url = val.strip()
            if url.startswith("postgres://"):
                url = "postgresql://" + url[len("postgres://"):]
            return url
    return None


def _get_pg_pool():
    """إنشاء مجمع اتصالات (Connection Pool) لـ PostgreSQL"""
    global _PG_POOL
    if _PG_POOL is not None:
        return _PG_POOL

    db_url = _get_database_url()
    if not db_url or not HAS_PSYCOPG2:
        return None

    try:
        _PG_POOL = pool.ThreadedConnectionPool(
            minconn=1,
            maxconn=20,
            dsn=db_url,
            sslmode="require" if "supabase" in db_url and "sslmode" not in db_url else "prefer"
        )
        return _PG_POOL
    except Exception as e:
        print(f"⚠️ Failed to create PostgreSQL pool: {e}")
        return None


def _get_supabase_client():
    """إنشاء عميل Supabase REST API في حال عدم استخدام اتصال PostgreSQL المباشر"""
    global _SUPABASE_CLIENT
    if _SUPABASE_CLIENT is not None:
        return _SUPABASE_CLIENT

    if not HAS_SUPABASE_LIB:
        return None

    sb_url = os.environ.get("SUPABASE_URL") or os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
    sb_key = (
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        or os.environ.get("SUPABASE_KEY")
        or os.environ.get("SUPABASE_ANON_KEY")
        or os.environ.get("NEXT_PUBLIC_SUPABASE_ANON_KEY")
    )

    if sb_url and sb_key:
        try:
            _SUPABASE_CLIENT = create_client(sb_url.strip(), sb_key.strip())
            return _SUPABASE_CLIENT
        except Exception as e:
            print(f"⚠️ Error initializing Supabase REST client: {e}")
    return None


def init_supabase_tables():
    """
    إنشاء كافة الجداول والأعمدة والفهارس والبيانات الافتراضية تلقائياً في Supabase
    يتم استدعاؤها تلقائياً عند بدء التشغيل
    """
    global _DB_INITIALIZED
    if _DB_INITIALIZED:
        return True

    with _INIT_LOCK:
        if _DB_INITIALIZED:
            return True

        pg_pool = _get_pg_pool()
        if pg_pool:
            conn = None
            try:
                conn = pg_pool.getconn()
                with conn.cursor() as cur:
                    # 1. جدول الإحصائيات العامة والشرائح znx_global_stats
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS public.znx_global_stats (
                            id TEXT PRIMARY KEY,
                            total_converted_znx DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                            max_global_znx DOUBLE PRECISION NOT NULL DEFAULT 32500000.0,
                            is_active BOOLEAN NOT NULL DEFAULT TRUE,
                            tiers_config JSONB NOT NULL DEFAULT '[]'::jsonb,
                            updated_at TIMESTAMPTZ DEFAULT NOW()
                        );
                    """)

                    # 2. جدول المستخدمين users (إنشاؤه إذا لم يكن موجوداً أو تحديث أعمدته تلقائياً)
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS public.users (
                            user_id TEXT PRIMARY KEY,
                            first_name TEXT DEFAULT 'لاعب جديد',
                            name TEXT DEFAULT 'لاعب جديد',
                            balance DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                            usd_balance DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                            znx_balance DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                            total_znx_earned DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                            created_at TIMESTAMPTZ DEFAULT NOW(),
                            updated_at TIMESTAMPTZ DEFAULT NOW()
                        );
                    """)

                    # ضمان وجود كافة الأعمدة حتى لو كان جدول users منشأ مسبقاً من نظام آخر
                    cur.execute("ALTER TABLE public.users ADD COLUMN IF NOT EXISTS first_name TEXT DEFAULT 'لاعب جديد';")
                    cur.execute("ALTER TABLE public.users ADD COLUMN IF NOT EXISTS name TEXT DEFAULT 'لاعب جديد';")
                    cur.execute("ALTER TABLE public.users ADD COLUMN IF NOT EXISTS balance DOUBLE PRECISION NOT NULL DEFAULT 0.0;")
                    cur.execute("ALTER TABLE public.users ADD COLUMN IF NOT EXISTS usd_balance DOUBLE PRECISION NOT NULL DEFAULT 0.0;")
                    cur.execute("ALTER TABLE public.users ADD COLUMN IF NOT EXISTS znx_balance DOUBLE PRECISION NOT NULL DEFAULT 0.0;")
                    cur.execute("ALTER TABLE public.users ADD COLUMN IF NOT EXISTS total_znx_earned DOUBLE PRECISION NOT NULL DEFAULT 0.0;")
                    cur.execute("ALTER TABLE public.users ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();")

                    # 3. جدول سجل عمليات التحويل znx_conversions_log
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS public.znx_conversions_log (
                            id BIGSERIAL PRIMARY KEY,
                            user_id TEXT NOT NULL,
                            points_converted DOUBLE PRECISION NOT NULL,
                            znx_gained DOUBLE PRECISION NOT NULL,
                            tier_number INTEGER NOT NULL,
                            conversion_rate DOUBLE PRECISION NOT NULL,
                            created_at TIMESTAMPTZ DEFAULT NOW()
                        );
                    """)

                    # 4. إنشاء فهارس السرعة الفائقة للمتصدرين والترتيب
                    cur.execute("""
                        CREATE INDEX IF NOT EXISTS idx_users_total_znx_earned
                        ON public.users (total_znx_earned DESC);
                    """)
                    cur.execute("""
                        CREATE INDEX IF NOT EXISTS idx_conversions_user_id
                        ON public.znx_conversions_log (user_id, created_at DESC);
                    """)

                    # 5. إدراج سجل الملخص الافتراضي في znx_global_stats إن لم يكن موجوداً
                    init_tiers = [_clean_tier_dict(t, t) for t in TIERS_CONFIG]
                    cur.execute("""
                        INSERT INTO public.znx_global_stats (id, total_converted_znx, max_global_znx, is_active, tiers_config)
                        VALUES ('summary', 0.0, %s, TRUE, %s::jsonb)
                        ON CONFLICT (id) DO NOTHING;
                    """, (MAX_GLOBAL_ZNX, json.dumps(init_tiers, ensure_ascii=False)))

                conn.commit()
                _DB_INITIALIZED = True
                print("✅ Supabase PostgreSQL tables & indexes initialized automatically!")
                return True
            except Exception as e:
                if conn:
                    conn.rollback()
                print(f"⚠️ PostgreSQL auto-init warning: {e}")
            finally:
                if conn:
                    pg_pool.putconn(conn)

        # في حال استخدام Supabase REST Client فقط، نضمن تهيئة صف summary
        sb = _get_supabase_client()
        if sb:
            try:
                res = sb.table("znx_global_stats").select("id").eq("id", "summary").execute()
                if not res.data:
                    init_tiers = [_clean_tier_dict(t, t) for t in TIERS_CONFIG]
                    sb.table("znx_global_stats").upsert({
                        "id": "summary",
                        "total_converted_znx": 0.0,
                        "max_global_znx": MAX_GLOBAL_ZNX,
                        "is_active": True,
                        "tiers_config": init_tiers
                    }).execute()
                _DB_INITIALIZED = True
                print("✅ Supabase REST Client initialized successfully!")
                return True
            except Exception as e:
                print(f"⚠️ Supabase REST init warning (Make sure tables exist): {e}")

        return False


def _get_db():
    """دالة توافقية لضمان تهيئة قاعدة البيانات قبل أي عملية"""
    if not _DB_INITIALIZED:
        init_supabase_tables()
    return _get_pg_pool() or _get_supabase_client()


# ==================== الأدوات المساعدة ومنطق الشرائح ====================

def _sanitize_id(user_id):
    if user_id is None:
        return None
    s_id = str(user_id).strip()
    if not s_id or s_id.lower() in ("none", "null", "undefined", "false", "true"):
        return None
    return s_id


def _clean_tier_dict(t, def_tier):
    """تنظيف وتنسيق بيانات الشريحة لتكون صالحة للتشفير في JSON دون أخطاء Infinity"""
    if not isinstance(t, dict):
        return def_tier

    raw_max = t.get('max_pts')
    if str(raw_max).lower() in ("inf", "infinity", "none") or raw_max == float('inf'):
        json_max = "Infinity"
    else:
        try:
            json_max = float(raw_max)
        except Exception:
            json_max = "Infinity"

    tier_num = int(t.get('tier', def_tier.get('tier', 1)))

    return {
        'tier': tier_num,
        'name': str(t.get('name', def_tier.get('name', f'الشريحة {tier_num}'))),
        'min_pts': float(t.get('min_pts', def_tier.get('min_pts', 0.0))),
        'max_pts': json_max,
        'rate': float(t.get('rate', def_tier.get('rate', 10))),
        'quota': float(t.get('quota', def_tier.get('quota', 1_000_000))),
        'min_withdraw_znx': float(t.get('min_withdraw_znx', def_tier.get('min_withdraw_znx', 1.0))),
        'fixed_fee_usd': float(t.get('fixed_fee_usd', def_tier.get('fixed_fee_usd', 0.02)))
    }


def _parse_tiers_from_raw(raw_tiers):
    """معالجة مرنة لبيانات الشرائح سواء كانت قائمة أو نص JSON أو قاموس"""
    if isinstance(raw_tiers, str):
        try:
            raw_tiers = json.loads(raw_tiers)
        except Exception:
            raw_tiers = None

    parsed_tiers_list = []
    if isinstance(raw_tiers, list) and len(raw_tiers) > 0:
        parsed_tiers_list = raw_tiers
    elif isinstance(raw_tiers, dict) and len(raw_tiers) > 0:
        sorted_keys = sorted(raw_tiers.keys(), key=lambda x: int(x) if str(x).isdigit() else str(x))
        parsed_tiers_list = [raw_tiers[k] for k in sorted_keys if isinstance(raw_tiers[k], dict)]

    if parsed_tiers_list:
        clean_tiers = []
        for idx, t in enumerate(parsed_tiers_list):
            def_t = TIERS_CONFIG[idx] if idx < len(TIERS_CONFIG) else TIERS_CONFIG[-1]
            clean_tiers.append(_clean_tier_dict(t, def_t))
        return clean_tiers

    return [_clean_tier_dict(t, t) for t in TIERS_CONFIG]


def get_current_tier(global_znx=0.0, user_points=0.0, custom_tiers=None):
    """تحديد الشريحة الحالية بناءً على إجمالي عملات ZNX المحولة عالمياً"""
    tiers = custom_tiers or TIERS_CONFIG

    try:
        g_znx = float(global_znx) if global_znx is not None and not math.isnan(float(global_znx)) else 0.0
    except (ValueError, TypeError):
        g_znx = 0.0

    for item in tiers:
        try:
            min_v = float(item.get("min_pts", 0.0))
            raw_max = item.get("max_pts")
            if str(raw_max).lower() in ("inf", "infinity", "none"):
                max_v = float('inf')
            else:
                max_v = float(raw_max)

            if min_v <= g_znx < max_v:
                return item
        except Exception:
            continue

    return tiers[-1] if tiers else TIERS_CONFIG[-1]


def get_user_tier(user_points: float, custom_tiers=None, global_znx=0.0):
    return get_current_tier(global_znx=global_znx, user_points=user_points, custom_tiers=custom_tiers)


# ==================== العمليات الأساسية لقاعدة البيانات ====================

def get_global_stats(use_cache=True):
    """جلب إحصائيات المجمّع الكلي والشرائح مع كاش ذكي لمدة ثانيتين لمنع الضغط"""
    now = time.time()
    if use_cache and _GLOBAL_STATS_CACHE["data"] and (now - _GLOBAL_STATS_CACHE["timestamp"] < 2.0):
        return _GLOBAL_STATS_CACHE["data"]

    _get_db()
    default_stats = {
        'total_converted_znx': 0.0,
        'max_global_znx': MAX_GLOBAL_ZNX,
        'is_active': True,
        'tiers_config': [_clean_tier_dict(t, t) for t in TIERS_CONFIG]
    }

    # 1. المحاولة عبر اتصال PostgreSQL المباشر
    pg_pool = _get_pg_pool()
    if pg_pool:
        conn = None
        try:
            conn = pg_pool.getconn()
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM public.znx_global_stats WHERE id = 'summary' LIMIT 1;")
                row = cur.fetchone()

                if row:
                    total_converted = float(row.get('total_converted_znx') or 0.0)
                    max_global = float(row.get('max_global_znx') or MAX_GLOBAL_ZNX)
                    clean_tiers = _parse_tiers_from_raw(row.get('tiers_config'))

                    result = {
                        'total_converted_znx': total_converted,
                        'max_global_znx': max_global,
                        'is_active': total_converted < max_global,
                        'tiers_config': clean_tiers
                    }
                    _GLOBAL_STATS_CACHE["data"] = result
                    _GLOBAL_STATS_CACHE["timestamp"] = now
                    return result
                else:
                    init_tiers = [_clean_tier_dict(t, t) for t in TIERS_CONFIG]
                    cur.execute("""
                        INSERT INTO public.znx_global_stats (id, total_converted_znx, max_global_znx, is_active, tiers_config)
                        VALUES ('summary', 0.0, %s, TRUE, %s::jsonb)
                        ON CONFLICT (id) DO NOTHING;
                    """, (MAX_GLOBAL_ZNX, json.dumps(init_tiers, ensure_ascii=False)))
                    conn.commit()
                    _GLOBAL_STATS_CACHE["data"] = default_stats
                    _GLOBAL_STATS_CACHE["timestamp"] = now
                    return default_stats
        except Exception as e:
            if conn:
                conn.rollback()
            print(f"⚠️ PostgreSQL get_global_stats error: {e}")
        finally:
            if conn:
                pg_pool.putconn(conn)

    # 2. المحاولة عبر Supabase REST API
    sb = _get_supabase_client()
    if sb:
        try:
            res = sb.table("znx_global_stats").select("*").eq("id", "summary").limit(1).execute()
            if res.data and len(res.data) > 0:
                row = res.data[0]
                total_converted = float(row.get('total_converted_znx') or 0.0)
                max_global = float(row.get('max_global_znx') or MAX_GLOBAL_ZNX)
                clean_tiers = _parse_tiers_from_raw(row.get('tiers_config'))

                result = {
                    'total_converted_znx': total_converted,
                    'max_global_znx': max_global,
                    'is_active': total_converted < max_global,
                    'tiers_config': clean_tiers
                }
                _GLOBAL_STATS_CACHE["data"] = result
                _GLOBAL_STATS_CACHE["timestamp"] = now
                return result
            else:
                sb.table("znx_global_stats").upsert({
                    "id": "summary",
                    **default_stats
                }).execute()
                return default_stats
        except Exception as e:
            print(f"⚠️ Supabase REST get_global_stats error: {e}")

    return _GLOBAL_STATS_CACHE["data"] or default_stats


def get_user_data(user_id: str):
    """جلب بيانات المستخدم من Supabase أو إنشاؤه تلقائياً إن لم يكن موجوداً"""
    clean_uid = _sanitize_id(user_id)
    default_tier = _clean_tier_dict(TIERS_CONFIG[0], TIERS_CONFIG[0])
    default_user = {
        'user_id': clean_uid or '',
        'balance': 0.0,
        'usd_balance': 0.0,
        'znx_balance': 0.0,
        'total_znx_earned': 0.0,
        'first_name': 'لاعب جديد',
        'current_tier': default_tier
    }

    if not clean_uid:
        return default_user

    _get_db()
    global_stats = get_global_stats(use_cache=True)
    total_global_znx = float(global_stats.get('total_converted_znx', 0.0))
    all_tiers = global_stats.get('tiers_config') or TIERS_CONFIG

    # 1. عبر اتصال PostgreSQL المباشر
    pg_pool = _get_pg_pool()
    if pg_pool:
        conn = None
        try:
            conn = pg_pool.getconn()
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT user_id, first_name, name, balance, usd_balance, znx_balance, total_znx_earned
                    FROM public.users
                    WHERE user_id = %s
                    LIMIT 1;
                """, (clean_uid,))
                row = cur.fetchone()

                if row:
                    balance = float(row.get('balance') or 0.0)
                    usd_balance = float(row.get('usd_balance') or 0.0)
                    znx_balance = float(row.get('znx_balance') or 0.0)
                    total_znx_earned = float(row.get('total_znx_earned') or 0.0)
                    first_name = str(row.get('first_name') or row.get('name') or 'لاعب')
                    current_tier = get_current_tier(global_znx=total_global_znx, user_points=balance, custom_tiers=all_tiers)

                    return {
                        'user_id': clean_uid,
                        'balance': balance,
                        'usd_balance': usd_balance,
                        'znx_balance': znx_balance,
                        'total_znx_earned': total_znx_earned,
                        'first_name': first_name,
                        'current_tier': current_tier
                    }
                else:
                    current_tier = get_current_tier(global_znx=total_global_znx, user_points=0.0, custom_tiers=all_tiers)
                    cur.execute("""
                        INSERT INTO public.users (user_id, first_name, name, balance, usd_balance, znx_balance, total_znx_earned)
                        VALUES (%s, 'لاعب جديد', 'لاعب جديد', 0.0, 0.0, 0.0, 0.0)
                        ON CONFLICT (user_id) DO NOTHING;
                    """, (clean_uid,))
                    conn.commit()
                    return {
                        **default_user,
                        'current_tier': current_tier
                    }
        except Exception as e:
            if conn:
                conn.rollback()
            print(f"❌ PostgreSQL get_user_data error ({clean_uid}): {e}")
        finally:
            if conn:
                pg_pool.putconn(conn)

    # 2. عبر Supabase REST API
    sb = _get_supabase_client()
    if sb:
        try:
            res = sb.table("users").select("*").eq("user_id", clean_uid).limit(1).execute()
            if res.data and len(res.data) > 0:
                row = res.data[0]
                balance = float(row.get('balance') or 0.0)
                usd_balance = float(row.get('usd_balance') or 0.0)
                znx_balance = float(row.get('znx_balance') or 0.0)
                total_znx_earned = float(row.get('total_znx_earned') or 0.0)
                first_name = str(row.get('first_name') or row.get('name') or 'لاعب')
                current_tier = get_current_tier(global_znx=total_global_znx, user_points=balance, custom_tiers=all_tiers)

                return {
                    'user_id': clean_uid,
                    'balance': balance,
                    'usd_balance': usd_balance,
                    'znx_balance': znx_balance,
                    'total_znx_earned': total_znx_earned,
                    'first_name': first_name,
                    'current_tier': current_tier
                }
            else:
                current_tier = get_current_tier(global_znx=total_global_znx, user_points=0.0, custom_tiers=all_tiers)
                new_record = {
                    'user_id': clean_uid,
                    'first_name': 'لاعب جديد',
                    'name': 'لاعب جديد',
                    'balance': 0.0,
                    'usd_balance': 0.0,
                    'znx_balance': 0.0,
                    'total_znx_earned': 0.0
                }
                sb.table("users").upsert(new_record).execute()
                return {**default_user, 'current_tier': current_tier}
        except Exception as e:
            print(f"❌ Supabase REST get_user_data error ({clean_uid}): {e}")

    return default_user


def get_leaderboard_rankings(limit=10, user_id=None):
    """
    جلب قائمة المتصدرين وترتيب المستخدم الحالي بسرعة فائقة عبر SQL Indexed Queries
    دون سحب كل المستخدمين إلى الذاكرة كما كان يحدث في Firebase
    """
    _get_db()
    clean_target_id = _sanitize_id(user_id)
    now = time.time()
    rankings = []
    user_rank = "غير مصنف"
    user_in_top = False
    my_user_info = None

    # 1. عبر PostgreSQL المباشر
    pg_pool = _get_pg_pool()
    if pg_pool:
        conn = None
        try:
            conn = pg_pool.getconn()
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # استخدام الكاش لقائمة الـ Top 10 لمدة 5 ثوانٍ لتخفيف الحمل عند الملايين
                if _LEADERBOARD_CACHE["top_list"] and (now - _LEADERBOARD_CACHE["timestamp"] < 5.0) and len(_LEADERBOARD_CACHE["top_list"]) >= limit:
                    top_rows = _LEADERBOARD_CACHE["top_list"][:limit]
                else:
                    cur.execute("""
                        SELECT user_id, first_name, name, total_znx_earned, znx_balance, balance
                        FROM public.users
                        ORDER BY total_znx_earned DESC, znx_balance DESC
                        LIMIT %s;
                    """, (max(limit, 10),))
                    top_rows = cur.fetchall() or []
                    _LEADERBOARD_CACHE["top_list"] = top_rows
                    _LEADERBOARD_CACHE["timestamp"] = now

                rank = 1
                for r in top_rows[:limit]:
                    uid = str(r.get('user_id') or '')
                    name = str(r.get('first_name') or r.get('name') or 'لاعب')
                    earned = float(r.get('total_znx_earned') or 0.0)
                    znx_bal = float(r.get('znx_balance') or 0.0)
                    bal = float(r.get('balance') or 0.0)

                    item = {
                        'user_id': uid,
                        'name': name,
                        'first_name': name,
                        'total_znx_earned': earned,
                        'znx_balance': znx_bal,
                        'balance': bal,
                        'rank': rank
                    }
                    rankings.append(item)
                    if clean_target_id and uid == clean_target_id:
                        user_rank = rank
                        user_in_top = True
                        my_user_info = item
                    rank += 1

                # حساب ترتيب المستخدم بدقة عبر الفهرس إذا لم يكن ضمن الـ 10 الأوائل
                if clean_target_id and not user_in_top:
                    cur.execute("""
                        SELECT user_id, first_name, name, total_znx_earned
                        FROM public.users
                        WHERE user_id = %s
                        LIMIT 1;
                    """, (clean_target_id,))
                    t_row = cur.fetchone()
                    if t_row:
                        t_earned = float(t_row.get('total_znx_earned') or 0.0)
                        t_name = str(t_row.get('first_name') or t_row.get('name') or 'لاعب')
                        cur.execute("""
                            SELECT COUNT(*) AS higher_count
                            FROM public.users
                            WHERE total_znx_earned > %s;
                        """, (t_earned,))
                        cnt_row = cur.fetchone()
                        higher_count = int(cnt_row['higher_count']) if cnt_row else 0
                        user_rank = higher_count + 1
                        my_user_info = {
                            'user_id': clean_target_id,
                            'name': t_name,
                            'first_name': t_name,
                            'total_znx_earned': t_earned,
                            'rank': user_rank
                        }

                return {
                    'success': True,
                    'leaderboard': rankings,
                    'my_rank': user_rank,
                    'my_info': my_user_info
                }
        except Exception as e:
            print(f"❌ PostgreSQL leaderboard query error: {e}")
        finally:
            if conn:
                pg_pool.putconn(conn)

    # 2. عبر Supabase REST API
    sb = _get_supabase_client()
    if sb:
        try:
            res = (
                sb.table("users")
                .select("user_id, first_name, name, total_znx_earned, znx_balance, balance")
                .order("total_znx_earned", desc=True)
                .limit(limit)
                .execute()
            )
            top_rows = res.data or []
            rank = 1
            for r in top_rows:
                uid = str(r.get('user_id') or '')
                name = str(r.get('first_name') or r.get('name') or 'لاعب')
                earned = float(r.get('total_znx_earned') or 0.0)
                znx_bal = float(r.get('znx_balance') or 0.0)
                bal = float(r.get('balance') or 0.0)

                item = {
                    'user_id': uid,
                    'name': name,
                    'first_name': name,
                    'total_znx_earned': earned,
                    'znx_balance': znx_bal,
                    'balance': bal,
                    'rank': rank
                }
                rankings.append(item)
                if clean_target_id and uid == clean_target_id:
                    user_rank = rank
                    user_in_top = True
                    my_user_info = item
                rank += 1

            if clean_target_id and not user_in_top:
                u_res = sb.table("users").select("user_id, first_name, name, total_znx_earned").eq("user_id", clean_target_id).limit(1).execute()
                if u_res.data:
                    t_row = u_res.data[0]
                    t_earned = float(t_row.get('total_znx_earned') or 0.0)
                    t_name = str(t_row.get('first_name') or t_row.get('name') or 'لاعب')
                    c_res = sb.table("users").select("user_id", count="exact").gt("total_znx_earned", t_earned).execute()
                    higher_count = c_res.count if c_res.count is not None else 0
                    user_rank = higher_count + 1
                    my_user_info = {
                        'user_id': clean_target_id,
                        'name': t_name,
                        'first_name': t_name,
                        'total_znx_earned': t_earned,
                        'rank': user_rank
                    }
        except Exception as e:
            print(f"❌ Supabase REST leaderboard query error: {e}")

    return {
        'success': True,
        'leaderboard': rankings,
        'my_rank': user_rank,
        'my_info': my_user_info
    }


def get_leaderboard_data(limit=10, user_id=None):
    return get_leaderboard_rankings(limit=limit, user_id=user_id)


def _calculate_tiered_conversion(points_to_convert: float, total_global_znx: float, max_global_znx: float, active_tiers: list):
    """
    حساب التحويل المتسلسل عبر الشرائح بدقة متناهية:
    إذا كانت النقاط المحولة تنقل المجمّع العالمي من شريحة إلى الشريحة التي تليها،
    يتم تقسيم التحويل تلقائياً حسب سعر كل شريحة أو السقف المتبقي.
    """
    remaining_points = float(points_to_convert)
    sim_global_znx = float(total_global_znx)
    total_znx_gained = 0.0
    total_points_used = 0.0
    last_used_tier = get_current_tier(global_znx=sim_global_znx, custom_tiers=active_tiers)

    safety_loops = 0
    while remaining_points > 1e-7 and sim_global_znx < max_global_znx and safety_loops < 20:
        safety_loops += 1
        cur_tier = get_current_tier(global_znx=sim_global_znx, custom_tiers=active_tiers)
        last_used_tier = cur_tier
        rate = float(cur_tier.get('rate') or 10.0)
        if rate <= 0:
            rate = 10.0

        raw_max = cur_tier.get('max_pts')
        if str(raw_max).lower() in ("inf", "infinity", "none"):
            tier_upper_znx = max_global_znx
        else:
            try:
                tier_upper_znx = min(float(raw_max), max_global_znx)
            except Exception:
                tier_upper_znx = max_global_znx

        znx_room_in_tier = max(0.0, tier_upper_znx - sim_global_znx)
        if znx_room_in_tier <= 1e-9:
            # الانتقال للشريحة التالية إذا امتلأت الحالية
            sim_global_znx = tier_upper_znx + 1e-6
            continue

        znx_desired = remaining_points / rate
        znx_step = min(znx_desired, znx_room_in_tier, max_global_znx - sim_global_znx)
        if znx_step <= 0:
            break

        points_step = znx_step * rate
        total_znx_gained += znx_step
        total_points_used += points_step
        sim_global_znx += znx_step
        remaining_points -= points_step

        if abs(znx_step - znx_desired) < 1e-8:
            break

    return total_points_used, total_znx_gained, last_used_tier


def execute_conversion(user_id: str, points_to_convert: float):
    """تنفيذ تحويل نقاط ZN إلى عملات ZNX بمعاملة ذرية آمنة (ACID Transaction)"""
    clean_uid = _sanitize_id(user_id)
    if not clean_uid:
        return False, "معرف المستخدم غير صالح."

    try:
        points_to_convert = float(points_to_convert)
    except (ValueError, TypeError):
        return False, "كمية النقاط غير صالحة."

    if math.isnan(points_to_convert) or math.isinf(points_to_convert) or points_to_convert <= 0:
        return False, "كمية النقاط يجب أن تكون رقماً موجباً وصالحاً."

    _get_db()

    # 1. التنفيذ الذري عبر PostgreSQL المباشر (مع قفل الصفوف FOR UPDATE لمنع أي تضارب)
    pg_pool = _get_pg_pool()
    if pg_pool:
        conn = None
        try:
            conn = pg_pool.getconn()
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # قفل صف الإحصائيات العامة
                cur.execute("SELECT * FROM public.znx_global_stats WHERE id = 'summary' FOR UPDATE;")
                global_row = cur.fetchone()
                if not global_row:
                    init_tiers = [_clean_tier_dict(t, t) for t in TIERS_CONFIG]
                    cur.execute("""
                        INSERT INTO public.znx_global_stats (id, total_converted_znx, max_global_znx, is_active, tiers_config)
                        VALUES ('summary', 0.0, %s, TRUE, %s::jsonb)
                        RETURNING *;
                    """, (MAX_GLOBAL_ZNX, json.dumps(init_tiers, ensure_ascii=False)))
                    global_row = cur.fetchone()

                total_global_znx = float(global_row.get('total_converted_znx') or 0.0)
                max_global_znx = float(global_row.get('max_global_znx') or MAX_GLOBAL_ZNX)
                active_tiers = _parse_tiers_from_raw(global_row.get('tiers_config'))

                if total_global_znx >= max_global_znx:
                    conn.rollback()
                    return False, f"عذراً، تم الوصول إلى الحد الأقصى للمجمّع الكلي ({max_global_znx / 1_000_000:.1f}M ZNX)."

                # قفل صف المستخدم
                cur.execute("SELECT * FROM public.users WHERE user_id = %s FOR UPDATE;", (clean_uid,))
                user_row = cur.fetchone()
                if not user_row:
                    conn.rollback()
                    return False, "حساب المستخدم غير موجود في قاعدة البيانات."

                current_zn_balance = float(user_row.get('balance') or 0.0)
                if current_zn_balance < points_to_convert:
                    conn.rollback()
                    return False, f"رصيد نقاط ZN غير كافٍ. رصيدك الحالي: {current_zn_balance:,.2f}"

                actual_points, znx_received, used_tier = _calculate_tiered_conversion(
                    points_to_convert=points_to_convert,
                    total_global_znx=total_global_znx,
                    max_global_znx=max_global_znx,
                    active_tiers=active_tiers
                )

                if znx_received <= 0 or actual_points <= 0:
                    conn.rollback()
                    return False, "تم استنفاد مجمّع العملات المتاح بالكامل."

                new_zn_balance = round(max(0.0, current_zn_balance - actual_points), 4)
                new_znx_balance = round(float(user_row.get('znx_balance') or 0.0) + znx_received, 6)
                new_total_znx_earned = round(float(user_row.get('total_znx_earned') or 0.0) + znx_received, 6)
                new_global_total = round(total_global_znx + znx_received, 6)

                cur.execute("""
                    UPDATE public.users
                    SET balance = %s,
                        znx_balance = %s,
                        total_znx_earned = %s,
                        updated_at = NOW()
                    WHERE user_id = %s;
                """, (new_zn_balance, new_znx_balance, new_total_znx_earned, clean_uid))

                cur.execute("""
                    UPDATE public.znx_global_stats
                    SET total_converted_znx = %s,
                        is_active = %s,
                        updated_at = NOW()
                    WHERE id = 'summary';
                """, (new_global_total, new_global_total < max_global_znx))

                cur.execute("""
                    INSERT INTO public.znx_conversions_log (user_id, points_converted, znx_gained, tier_number, conversion_rate)
                    VALUES (%s, %s, %s, %s, %s);
                """, (
                    clean_uid,
                    round(actual_points, 4),
                    round(znx_received, 6),
                    int(used_tier.get('tier', 1)),
                    float(used_tier.get('rate', 10))
                ))

            conn.commit()

            # تحديث الكاش فوراً
            _GLOBAL_STATS_CACHE["timestamp"] = 0.0
            _LEADERBOARD_CACHE["timestamp"] = 0.0

            return True, {
                'converted_points': round(actual_points, 4),
                'znx_gained': round(znx_received, 6),
                'new_zn_balance': new_zn_balance,
                'new_znx_balance': new_znx_balance,
                'new_total_earned': new_total_znx_earned,
                'global_total': new_global_total
            }
        except Exception as e:
            if conn:
                conn.rollback()
            print(f"❌ PostgreSQL Conversion Transaction Error: {e}")
            return False, f"حدث خطأ أثناء معالجة العملية: {str(e)}"
        finally:
            if conn:
                pg_pool.putconn(conn)

    # 2. التنفيذ عبر Supabase REST API (في حال عدم ضبط DATABASE_URL)
    sb = _get_supabase_client()
    if sb:
        try:
            stats = get_global_stats(use_cache=False)
            total_global_znx = float(stats.get('total_converted_znx') or 0.0)
            max_global_znx = float(stats.get('max_global_znx') or MAX_GLOBAL_ZNX)
            active_tiers = stats.get('tiers_config') or TIERS_CONFIG

            if total_global_znx >= max_global_znx:
                return False, f"عذراً، تم الوصول إلى الحد الأقصى للمجمّع الكلي ({max_global_znx / 1_000_000:.1f}M ZNX)."

            u_res = sb.table("users").select("*").eq("user_id", clean_uid).limit(1).execute()
            if not u_res.data:
                return False, "حساب المستخدم غير موجود في قاعدة البيانات."

            user_row = u_res.data[0]
            current_zn_balance = float(user_row.get('balance') or 0.0)
            if current_zn_balance < points_to_convert:
                return False, f"رصيد نقاط ZN غير كافٍ. رصيدك الحالي: {current_zn_balance:,.2f}"

            actual_points, znx_received, used_tier = _calculate_tiered_conversion(
                points_to_convert=points_to_convert,
                total_global_znx=total_global_znx,
                max_global_znx=max_global_znx,
                active_tiers=active_tiers
            )

            if znx_received <= 0 or actual_points <= 0:
                return False, "تم استنفاد مجمّع العملات المتاح بالكامل."

            new_zn_balance = round(max(0.0, current_zn_balance - actual_points), 4)
            new_znx_balance = round(float(user_row.get('znx_balance') or 0.0) + znx_received, 6)
            new_total_znx_earned = round(float(user_row.get('total_znx_earned') or 0.0) + znx_received, 6)
            new_global_total = round(total_global_znx + znx_received, 6)

            sb.table("users").update({
                "balance": new_zn_balance,
                "znx_balance": new_znx_balance,
                "total_znx_earned": new_total_znx_earned
            }).eq("user_id", clean_uid).execute()

            sb.table("znx_global_stats").update({
                "total_converted_znx": new_global_total,
                "is_active": new_global_total < max_global_znx
            }).eq("id", "summary").execute()

            _GLOBAL_STATS_CACHE["timestamp"] = 0.0
            _LEADERBOARD_CACHE["timestamp"] = 0.0

            return True, {
                'converted_points': round(actual_points, 4),
                'znx_gained': round(znx_received, 6),
                'new_zn_balance': new_zn_balance,
                'new_znx_balance': new_znx_balance,
                'new_total_earned': new_total_znx_earned,
                'global_total': new_global_total
            }
        except Exception as e:
            print(f"❌ Supabase REST Conversion Error: {e}")
            return False, f"حدث خطأ أثناء معالجة العملية: {str(e)}"

    return False, "لم يتم العثور على إعدادات اتصال بقاعدة بيانات Supabase."


# تشغيل التهيئة التلقائية للجداول فور استيراد الملف
init_supabase_tables()
