# -*- coding: utf-8 -*-
import os
import re
import sys
import time
import json
from datetime import datetime, timezone
from psycopg2.extras import RealDictCursor

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "../../"))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

try:
    from database import get_db_connection, _sanitize_id
except ImportError as e:
    print(f"⚠️ خطأ في استيراد database.py داخل withdraw_db: {e}")
    get_db_connection = None

    def _sanitize_id(val):
        if val is None:
            return None
        s = str(val).strip()
        if s.endswith('.0'):
            s = s[:-2]
        return s if s and s.lower() not in ('none', 'null', 'undefined', 'nan') else None

# قراءة عنوان عقد العملة الذكي من متغيرات بيئة Railway
ZNX_CONTRACT_ADDRESS = os.getenv("ZNX_CONTRACT_ADDRESS", "EQCp7mIbe-eR-j6b7opnHBtCbl74gnyYAP2XZlSpHkERkwdJ")

# --- نظام Caching لتسريع الاستجابة ---
_TIER_CACHE = {
    "data": None,
    "timestamp": 0
}
CACHE_TTL_SECONDS = 5

TON_WALLET_REGEX = re.compile(r"^(EQ|UQ|0:)[a-zA-Z0-9_-]{46,66}$")

# الإعدادات القياسية للشرائح السبع لعملة ZNX لضمان التطابق التام مع مستويات التحويل والسحب
DEFAULT_ZNX_TIERS = [
    {"tier": 1, "name": "الشريحة الأولى", "min_pts": 0.0, "max_pts": 500000.0, "min_withdraw_znx": 1000.0, "fixed_fee_usd": 0.02},
    {"tier": 2, "name": "الشريحة الثانية", "min_pts": 500000.0, "max_pts": 1500000.0, "min_withdraw_znx": 500.0, "fixed_fee_usd": 0.02},
    {"tier": 3, "name": "الشريحة الثالثة", "min_pts": 1500000.0, "max_pts": 3500000.0, "min_withdraw_znx": 250.0, "fixed_fee_usd": 0.02},
    {"tier": 4, "name": "الشريحة الرابعة", "min_pts": 3500000.0, "max_pts": 7500000.0, "min_withdraw_znx": 100.0, "fixed_fee_usd": 0.02},
    {"tier": 5, "name": "الشريحة الخامسة", "min_pts": 7500000.0, "max_pts": 15000000.0, "min_withdraw_znx": 50.0, "fixed_fee_usd": 0.02},
    {"tier": 6, "name": "الشريحة السادسة", "min_pts": 15000000.0, "max_pts": 25000000.0, "min_withdraw_znx": 10.0, "fixed_fee_usd": 0.02},
    {"tier": 7, "name": "الشريحة السابعة", "min_pts": 25000000.0, "max_pts": "inf", "min_withdraw_znx": 2.5, "fixed_fee_usd": 0.02}
]

TIER_DEFAULTS_BY_NUM = {item["tier"]: item for item in DEFAULT_ZNX_TIERS}


def is_valid_ton_address(address: str) -> bool:
    if not address or not isinstance(address, str):
        return False
    return bool(TON_WALLET_REGEX.match(address.strip()))


def safe_get_db():
    """فحص جاهزية الاتصال بقاعدة بيانات Supabase PostgreSQL"""
    return get_db_connection is not None


get_db = safe_get_db


def init_withdraw_tables():
    """إنشاء وتجهيز وترقية كافة جداول وأعمدة نظام السحب والسجلات في Supabase تلقائياً"""
    if not get_db_connection:
        return False

    default_tiers_json = json.dumps(DEFAULT_ZNX_TIERS, ensure_ascii=False)

    # 1. تهيئة وترقية جدول users
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS user_id VARCHAR(128);
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS telegram_id VARCHAR(128);
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS username VARCHAR(100) DEFAULT '';
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS znx_balance DOUBLE PRECISION DEFAULT 0.0;
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS usd_balance DOUBLE PRECISION DEFAULT 0.0;
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS balance DOUBLE PRECISION DEFAULT 0.0;
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS wallet_address TEXT DEFAULT '';
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS wallets JSONB DEFAULT '{}'::jsonb;
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS is_banned BOOLEAN DEFAULT FALSE;
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS banned BOOLEAN DEFAULT FALSE;
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS hourly_rate DOUBLE PRECISION DEFAULT 0.0;
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS upgrades_count INTEGER DEFAULT 0;
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS storage_level INTEGER DEFAULT 1;
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS max_cap DOUBLE PRECISION DEFAULT 0.0;
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS referral_count INTEGER DEFAULT 0;
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS referrals_count INTEGER DEFAULT 0;
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS ref_count INTEGER DEFAULT 0;
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP;
                """)
    except Exception as e:
        print(f"⚠️ خطأ تهيئة users في withdraw_db: {e}")

    # 2. تهيئة جدول شرائح السحب ومستويات ZNX (znx_global_stats)
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS znx_global_stats (
                        id TEXT PRIMARY KEY DEFAULT 'summary',
                        total_converted_znx DOUBLE PRECISION DEFAULT 0.0,
                        max_global_znx DOUBLE PRECISION DEFAULT 32500000.0,
                        active_tier INTEGER DEFAULT 1,
                        tiers_config JSONB DEFAULT '[]'::jsonb,
                        updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                cur.execute("ALTER TABLE znx_global_stats ADD COLUMN IF NOT EXISTS total_converted_znx DOUBLE PRECISION DEFAULT 0.0;")
                cur.execute("ALTER TABLE znx_global_stats ADD COLUMN IF NOT EXISTS max_global_znx DOUBLE PRECISION DEFAULT 32500000.0;")
                cur.execute("ALTER TABLE znx_global_stats ADD COLUMN IF NOT EXISTS active_tier INTEGER DEFAULT 1;")
                cur.execute("ALTER TABLE znx_global_stats ADD COLUMN IF NOT EXISTS tiers_config JSONB DEFAULT '[]'::jsonb;")
                cur.execute("ALTER TABLE znx_global_stats ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP;")
                cur.execute("""
                    INSERT INTO znx_global_stats (id, total_converted_znx, tiers_config)
                    VALUES ('summary', 0.0, %s::jsonb)
                    ON CONFLICT (id) DO NOTHING;
                """, (default_tiers_json,))
    except Exception as e:
        print(f"⚠️ خطأ تهيئة znx_global_stats: {e}")

    # 3. تهيئة وترقية جدول processed_txs (متوافق مع المتجر والسحب والسجل معاً)
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS processed_txs (
                        tx_hash VARCHAR(256) PRIMARY KEY DEFAULT md5(random()::text || clock_timestamp()::text),
                        id TEXT DEFAULT md5(random()::text || clock_timestamp()::text),
                        tx_id TEXT,
                        user_id TEXT,
                        tg_id TEXT,
                        coins NUMERIC DEFAULT 0.0,
                        amount NUMERIC DEFAULT 0.0,
                        fee_usd NUMERIC DEFAULT 0.02,
                        net_coins NUMERIC DEFAULT 0.0,
                        currency TEXT DEFAULT 'ZNX',
                        tier_name TEXT DEFAULT '',
                        wallet_address TEXT DEFAULT '',
                        type TEXT DEFAULT 'withdraw',
                        status TEXT DEFAULT 'pending',
                        processed_by TEXT,
                        details TEXT DEFAULT '',
                        failure_reason TEXT,
                        processing_started_at TIMESTAMPTZ,
                        processed_at TIMESTAMPTZ,
                        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                cols = [
                    "id TEXT DEFAULT md5(random()::text || clock_timestamp()::text)",
                    "tx_hash VARCHAR(256) DEFAULT md5(random()::text || clock_timestamp()::text)",
                    "tx_id TEXT",
                    "user_id TEXT",
                    "tg_id TEXT",
                    "coins NUMERIC DEFAULT 0.0",
                    "amount NUMERIC DEFAULT 0.0",
                    "fee_usd NUMERIC DEFAULT 0.02",
                    "net_coins NUMERIC DEFAULT 0.0",
                    "currency TEXT DEFAULT 'ZNX'",
                    "tier_name TEXT DEFAULT ''",
                    "wallet_address TEXT DEFAULT ''",
                    "type TEXT DEFAULT 'withdraw'",
                    "status TEXT DEFAULT 'pending'",
                    "processed_by TEXT",
                    "details TEXT DEFAULT ''",
                    "failure_reason TEXT",
                    "processing_started_at TIMESTAMPTZ",
                    "processed_at TIMESTAMPTZ",
                    "created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP",
                    "updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP"
                ]
                for col in cols:
                    try:
                        cur.execute(f"ALTER TABLE processed_txs ADD COLUMN IF NOT EXISTS {col};")
                    except Exception:
                        pass

                try:
                    cur.execute("ALTER TABLE processed_txs ALTER COLUMN tx_hash SET DEFAULT md5(random()::text || clock_timestamp()::text);")
                    cur.execute("ALTER TABLE processed_txs ALTER COLUMN id SET DEFAULT md5(random()::text || clock_timestamp()::text);")
                    cur.execute("ALTER TABLE processed_txs ALTER COLUMN details TYPE TEXT USING details::TEXT;")
                except Exception:
                    pass

                cur.execute("CREATE INDEX IF NOT EXISTS idx_processed_txs_user_status ON processed_txs(user_id, status);")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_processed_txs_tx_id ON processed_txs(tx_id);")
    except Exception as e:
        print(f"⚠️ خطأ تهيئة processed_txs: {e}")

    # 4. تهيئة وترقية جدول withdraw_requests
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
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
                """)
                cols = [
                    "tx_id TEXT",
                    "tg_id VARCHAR(255)",
                    "coins NUMERIC(18, 4) DEFAULT 0.0",
                    "amount NUMERIC(18, 4) DEFAULT 0.0",
                    "fee NUMERIC(18, 4) DEFAULT 0.0",
                    "fee_usd NUMERIC(18, 4) DEFAULT 0.02",
                    "net_coins NUMERIC(18, 4) DEFAULT 0.0",
                    "net_amount NUMERIC(18, 4) DEFAULT 0.0",
                    "currency VARCHAR(32) DEFAULT 'ZNX'",
                    "tier_name TEXT DEFAULT ''",
                    "wallet_address TEXT",
                    "network VARCHAR(32) DEFAULT 'TON'",
                    "status VARCHAR(50) DEFAULT 'pending'",
                    "tx_hash TEXT",
                    "processed_by TEXT",
                    "details TEXT",
                    "failure_reason TEXT",
                    "admin_note TEXT",
                    "updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP",
                    "processed_at TIMESTAMPTZ"
                ]
                for col in cols:
                    try:
                        cur.execute(f"ALTER TABLE withdraw_requests ADD COLUMN IF NOT EXISTS {col};")
                    except Exception:
                        pass
                cur.execute("CREATE INDEX IF NOT EXISTS idx_withdraw_requests_user ON withdraw_requests(user_id);")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_withdraw_requests_tx_id ON withdraw_requests(tx_id);")
    except Exception as e:
        print(f"⚠️ خطأ تهيئة withdraw_requests: {e}")

    # 5. تهيئة وترقية جدول transactions (لضمان عمل تبويب السجلات History 100%)
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
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
                """)
                cols = [
                    "tx_id TEXT",
                    "tx_hash TEXT",
                    "user_id TEXT",
                    "tg_id TEXT",
                    "coins NUMERIC DEFAULT 0.0",
                    "amount NUMERIC DEFAULT 0.0",
                    "fee NUMERIC DEFAULT 0.0",
                    "fee_usd NUMERIC DEFAULT 0.0",
                    "net_coins NUMERIC DEFAULT 0.0",
                    "net_amount NUMERIC DEFAULT 0.0",
                    "currency TEXT DEFAULT 'ZNX'",
                    "tier_name TEXT DEFAULT ''",
                    "wallet_address TEXT DEFAULT ''",
                    "network TEXT DEFAULT 'TON'",
                    "type TEXT DEFAULT 'withdraw'",
                    "status TEXT DEFAULT 'pending'",
                    "processed_by TEXT",
                    "details TEXT DEFAULT ''",
                    "failure_reason TEXT",
                    "processed_at TIMESTAMPTZ",
                    "updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP"
                ]
                for col in cols:
                    try:
                        cur.execute(f"ALTER TABLE transactions ADD COLUMN IF NOT EXISTS {col};")
                    except Exception:
                        pass
                cur.execute("CREATE INDEX IF NOT EXISTS idx_transactions_user_id ON transactions(user_id);")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_transactions_tg_id ON transactions(tg_id);")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_transactions_tx_id ON transactions(tx_id);")
    except Exception as e:
        print(f"⚠️ خطأ تهيئة transactions: {e}")

    # 6. تهيئة وترقية جدول admin_logs
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
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
                """)
                cur.execute("ALTER TABLE admin_logs ADD COLUMN IF NOT EXISTS tx_id TEXT;")
                cur.execute("ALTER TABLE admin_logs ADD COLUMN IF NOT EXISTS user_id TEXT;")
                cur.execute("ALTER TABLE admin_logs ADD COLUMN IF NOT EXISTS admin_id TEXT;")
                cur.execute("ALTER TABLE admin_logs ADD COLUMN IF NOT EXISTS status TEXT;")
                cur.execute("ALTER TABLE admin_logs ADD COLUMN IF NOT EXISTS amount NUMERIC DEFAULT 0.0;")
                cur.execute("ALTER TABLE admin_logs ADD COLUMN IF NOT EXISTS details TEXT;")
    except Exception as e:
        print(f"⚠️ خطأ تهيئة admin_logs: {e}")

    return True


class PostgresUserRef:
    def __init__(self, user_id: str, data: dict):
        self.id = str(user_id)
        self.pk_col = "tg_id"
        self.pk_val = str(user_id)
        self._data = data

    def update(self, payload: dict):
        if not get_db_connection or not payload:
            return False
        set_clauses = []
        values = []
        for k, v in payload.items():
            if not re.match(r"^[a-zA-Z0-9_]+$", str(k)):
                continue
            if isinstance(v, (dict, list)):
                set_clauses.append(f"{k} = %s::jsonb")
                values.append(json.dumps(v, ensure_ascii=False))
            else:
                set_clauses.append(f"{k} = %s")
                values.append(v)

        if not set_clauses:
            return False

        set_clauses.append("updated_at = CURRENT_TIMESTAMP")
        values.extend([self.id, self.id, self.id])
        sql = f"""
            UPDATE users
            SET {", ".join(set_clauses)}
            WHERE tg_id::TEXT = %s
               OR user_id::TEXT = %s
               OR telegram_id::TEXT = %s
        """
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, tuple(values))
            return True
        except Exception as e:
            print(f"⚠️ خطأ تحديث المستخدم في PostgresUserRef: {e}")
            return False

    def set(self, payload: dict, merge: bool = True):
        return self.update(payload)


def format_crypto_display(amount):
    if amount is None:
        return "0.0000"
    try:
        val = float(amount)
        if val <= 0:
            return "0.0000"
        return f"{val:,.4f}"
    except Exception:
        return str(amount)


def extract_user_balance(data):
    if not isinstance(data, dict):
        return 0.0
    if "znx_balance" in data and data["znx_balance"] is not None:
        try:
            val = float(data["znx_balance"])
            if val >= 0:
                return val
        except (ValueError, TypeError):
            pass
    return 0.0


def extract_usd_balance(data):
    if not isinstance(data, dict):
        return 0.0
    try:
        val = float(data.get("usd_balance", 0.0) or 0.0)
        return val if val >= 0 else 0.0
    except (ValueError, TypeError):
        return 0.0


def _parse_json_val(raw_val, default_val):
    if raw_val is None:
        return default_val
    if isinstance(raw_val, type(default_val)):
        return raw_val
    if isinstance(raw_val, str):
        try:
            parsed = json.loads(raw_val)
            if isinstance(parsed, type(default_val)):
                return parsed
        except Exception:
            pass
    return default_val


def _resolve_tier_limits(item: dict, tier_num: int):
    """استخراج حدود الشريحة والحد الأدنى للسحب بمرونة كاملة لتتطابق مع جدول znx_global_stats"""
    fallback = TIER_DEFAULTS_BY_NUM.get(tier_num, TIER_DEFAULTS_BY_NUM[1])

    # قراءة الحد الأدنى للشريحة (إن وجد بأي مسمى)
    min_raw = (
        item.get("min_pts")
        if item.get("min_pts") is not None
        else item.get("min_znx", item.get("min_converted", item.get("start_znx", fallback["min_pts"])))
    )
    try:
        min_v = float(min_raw or 0.0)
    except (ValueError, TypeError):
        min_v = float(fallback["min_pts"])

    # قراءة الحد الأقصى للشريحة (إن وجد بأي مسمى في znx_wallet)
    max_raw = None
    for k in ("max_pts", "max_znx", "max_converted", "end_znx", "limit", "max_limit", "target_znx", "cap"):
        if item.get(k) is not None:
            max_raw = item.get(k)
            break

    if max_raw is None:
        max_raw = fallback["max_pts"]

    if str(max_raw).strip().lower() in ("inf", "infinity", "none", "null", ""):
        max_v = float("inf")
    else:
        try:
            max_v = float(max_raw)
        except (ValueError, TypeError):
            max_v = float("inf") if fallback["max_pts"] == "inf" else float(fallback["max_pts"])

    # قراءة الحد الأدنى للسحب والرسوم الخاصة بهذه الشريحة
    min_withdraw_raw = item.get("min_withdraw_znx", item.get("min_withdraw", fallback["min_withdraw_znx"]))
    try:
        min_withdraw_znx = float(min_withdraw_raw)
        if min_withdraw_znx <= 0:
            min_withdraw_znx = float(fallback["min_withdraw_znx"])
    except (ValueError, TypeError):
        min_withdraw_znx = float(fallback["min_withdraw_znx"])

    fee_raw = item.get("fixed_fee_usd", item.get("fee_usd", fallback["fixed_fee_usd"]))
    try:
        fixed_fee_usd = float(fee_raw)
        if fixed_fee_usd < 0:
            fixed_fee_usd = float(fallback["fixed_fee_usd"])
    except (ValueError, TypeError):
        fixed_fee_usd = float(fallback["fixed_fee_usd"])

    return {
        "tier": tier_num,
        "name": str(item.get("name") or fallback["name"]),
        "min_pts": min_v,
        "max_pts": max_v,
        "min_withdraw_znx": min_withdraw_znx,
        "fixed_fee_usd": fixed_fee_usd
    }


def get_current_withdraw_tier():
    """جلب شريحة السحب الحالية ومطابقتها تماماً مع مستوى ZNX في znx_global_stats"""
    now = time.time()
    if _TIER_CACHE["data"] and (now - _TIER_CACHE["timestamp"] < CACHE_TTL_SECONDS):
        return _TIER_CACHE["data"]

    default_tier = {
        "tier": 1,
        "name": "الشريحة الأولى",
        "min_withdraw_znx": 1000.0,
        "fixed_fee_usd": 0.02
    }
    if not get_db_connection:
        return default_tier

    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM znx_global_stats WHERE id = 'summary' LIMIT 1")
                stats = cur.fetchone()

                if not stats:
                    _TIER_CACHE["data"] = default_tier
                    _TIER_CACHE["timestamp"] = now
                    return default_tier

                total_global_znx = float(stats.get("total_converted_znx", 0.0) or 0.0)
                active_tier_col = stats.get("active_tier") or stats.get("current_tier")
                raw_tiers = _parse_json_val(stats.get("tiers_config"), [])

                if not raw_tiers or not isinstance(raw_tiers, list):
                    raw_tiers = DEFAULT_ZNX_TIERS

                resolved_list = []
                for idx, item in enumerate(raw_tiers):
                    if not isinstance(item, dict):
                        continue
                    t_num = int(item.get("tier") or (idx + 1))
                    resolved_list.append(_resolve_tier_limits(item, t_num))

                if not resolved_list:
                    resolved_list = [_resolve_tier_limits(t, t["tier"]) for t in DEFAULT_ZNX_TIERS]

                res_tier = None

                # 1. تحديد الشريحة بناءً على إجمالي العملات المحولة (total_converted_znx)
                for r_item in resolved_list:
                    if r_item["min_pts"] <= total_global_znx < r_item["max_pts"]:
                        res_tier = {
                            "tier": r_item["tier"],
                            "name": r_item["name"],
                            "min_withdraw_znx": r_item["min_withdraw_znx"],
                            "fixed_fee_usd": r_item["fixed_fee_usd"]
                        }
                        break

                # 2. إذا كان هناك عمود active_tier صريح في الجدول وكان أعلى، نأخذ به لضمان التطابق
                if active_tier_col is not None:
                    try:
                        act_num = int(active_tier_col)
                        for r_item in resolved_list:
                            if r_item["tier"] == act_num:
                                # إذا لم تكن total_converted_znx قد حددت شريحة أعلى، اعتمد active_tier
                                if not res_tier or act_num >= res_tier["tier"]:
                                    res_tier = {
                                        "tier": r_item["tier"],
                                        "name": r_item["name"],
                                        "min_withdraw_znx": r_item["min_withdraw_znx"],
                                        "fixed_fee_usd": r_item["fixed_fee_usd"]
                                    }
                                break
                    except (ValueError, TypeError):
                        pass

                # 3. إذا تخطى الإجمالي جميع الحدود القصوى، نعتمد الشريحة الأخيرة (السابعة)
                if not res_tier:
                    last = resolved_list[-1]
                    res_tier = {
                        "tier": last["tier"],
                        "name": last["name"],
                        "min_withdraw_znx": last["min_withdraw_znx"],
                        "fixed_fee_usd": last["fixed_fee_usd"]
                    }

                _TIER_CACHE["data"] = res_tier
                _TIER_CACHE["timestamp"] = now
                return res_tier
    except Exception as e:
        print(f"⚠️ خطأ جلب شريحة السحب: {e}")
    return default_tier


def get_user_doc(user_id):
    clean_id = _sanitize_id(user_id)
    if not clean_id or not get_db_connection:
        return None, None
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM users
                    WHERE tg_id::TEXT = %s OR user_id::TEXT = %s OR telegram_id::TEXT = %s
                    LIMIT 1
                """, (clean_id, clean_id, clean_id))
                row = cur.fetchone()
                if row:
                    data = dict(row)
                    return PostgresUserRef(clean_id, data), data
    except Exception as e:
        print(f"⚠️ خطأ جلب بيانات المستخدم: {e}")
    return None, None


def get_user_full_details(user_id):
    try:
        clean_id = _sanitize_id(user_id)
        if not clean_id or not get_db_connection:
            return None

        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    WITH user_data AS (
                        SELECT * FROM users 
                        WHERE tg_id::TEXT = %s OR user_id::TEXT = %s OR telegram_id::TEXT = %s
                        LIMIT 1
                    ),
                    referral_count_data AS (
                        SELECT COUNT(*) AS count_refs FROM users 
                        WHERE referred_by::TEXT = %s OR ref_by::TEXT = %s
                    )
                    SELECT user_data.*, referral_count_data.count_refs 
                    FROM user_data CROSS JOIN referral_count_data;
                """, (clean_id, clean_id, clean_id, clean_id, clean_id))
                row = cur.fetchone()
                if not row:
                    return None
                data = dict(row)

        real_znx_balance = extract_user_balance(data)
        usd_balance = extract_usd_balance(data)
        zn_balance = float(data.get("balance", 0.0) or 0.0)
        wallets = _parse_json_val(data.get("wallets"), {})
        wallet_addr = data.get("wallet_address") or wallets.get("ZNX", "") or ""

        joined_str = "غير محدد"
        joined_raw = data.get("created_at") or data.get("joined_at") or data.get("registration_date")
        if joined_raw:
            try:
                if hasattr(joined_raw, "strftime"):
                    joined_str = joined_raw.strftime("%Y-%m-%d %H:%M:%S")
                elif isinstance(joined_raw, (int, float)):
                    joined_str = datetime.fromtimestamp(joined_raw, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                elif isinstance(joined_raw, str):
                    joined_str = joined_raw.replace("T", " ").split(".")[0].replace("Z", "")[:19]
            except Exception:
                pass

        return {
            "user_id": str(clean_id),
            "first_name": data.get("first_name") or data.get("name") or "غير محدد",
            "username": data.get("username") or "لا يوجد",
            "znx_balance": real_znx_balance,
            "zn_balance": zn_balance,
            "usd_balance": usd_balance,
            "joined_at": joined_str,
            "hourly_rate": float(data.get("hourly_rate", 0.0) or 0.0),
            "upgrades_count": int(data.get("upgrades_count", 0) or 0),
            "storage_level": int(data.get("storage_level", 1) or 1),
            "max_cap": float(data.get("max_cap", 0.0) or 0.0),
            "ref_count": max(
                int(data.get("count_refs", 0) or 0),
                int(data.get("referrals_count", 0) or data.get("referral_count", 0) or data.get("ref_count", 0) or 0)
            ),
            "is_banned": bool(data.get("is_banned", False) or data.get("banned", False)),
            "wallets": wallets,
            "wallet_address": wallet_addr
        }
    except Exception as e:
        print(f"⚠️ خطأ جلب تفاصيل المستخدم كاملة: {e}")
        return None


def save_user_wallet(user_id, currency, wallet_address):
    """حفظ أو تغيير عنوان المحفظة للمستخدم بحرية تامة في Supabase بدون أي تعارض"""
    clean_id = _sanitize_id(user_id)
    clean_wallet = str(wallet_address or "").strip()
    curr_key = str(currency or "ZNX").strip().upper()

    if not clean_id or not get_db_connection:
        return False, "تعذر الاتصال بقاعدة البيانات."

    if not is_valid_ton_address(clean_wallet):
        return False, "عنوان محفظة TON غير صالح! يجب أن يبدأ بـ EQ أو UQ."

    try:
        user_ref, user_data = get_user_doc(clean_id)

        # إذا لم يكن المستخدم مسجلاً بعد في جدول users، نقوم بإنشائه تلقائياً
        if not user_data:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    wallets_init = json.dumps({curr_key: clean_wallet}, ensure_ascii=False)
                    cur.execute("""
                        INSERT INTO users (tg_id, user_id, telegram_id, wallet_address, wallets, updated_at)
                        VALUES (%s, %s, %s, %s, %s::jsonb, CURRENT_TIMESTAMP)
                        ON CONFLICT (tg_id) DO UPDATE
                        SET wallet_address = EXCLUDED.wallet_address,
                            wallets = EXCLUDED.wallets,
                            updated_at = CURRENT_TIMESTAMP;
                    """, (clean_id, clean_id, clean_id, clean_wallet, wallets_init))
            return True, "تم حفظ المحفظة بنجاح."

        wallets = _parse_json_val(user_data.get("wallets"), {})
        if not isinstance(wallets, dict):
            wallets = {}
        wallets[curr_key] = clean_wallet

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE users
                    SET wallet_address = %s,
                        wallets = %s::jsonb,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE tg_id::TEXT = %s
                       OR user_id::TEXT = %s
                       OR telegram_id::TEXT = %s
                """, (clean_wallet, json.dumps(wallets, ensure_ascii=False), clean_id, clean_id, clean_id))

        return True, "تم حفظ وتحديث عنوان المحفظة بنجاح."
    except Exception as e:
        print(f"⚠️ خطأ حفظ المحفظة في Supabase: {e}")
        return False, "حدث خطأ أثناء الاتصال بالخادم لحفظ المحفظة."


# تهيئة وترقية الجداول تلقائياً عند استيراد الملف
init_withdraw_tables()
