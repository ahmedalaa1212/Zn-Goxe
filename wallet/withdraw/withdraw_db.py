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


def is_valid_ton_address(address: str) -> bool:
    if not address or not isinstance(address, str):
        return False
    return bool(TON_WALLET_REGEX.match(address.strip()))


def safe_get_db():
    """فحص جاهزية الاتصال بقاعدة بيانات Supabase PostgreSQL"""
    return get_db_connection is not None


get_db = safe_get_db


def init_withdraw_tables():
    """إنشاء وتجهيز كافة جداول وأعمدة نظام السحب في Supabase تلقائياً عند التشغيل"""
    if not get_db_connection:
        return False

    default_tiers_json = json.dumps([
        {"tier": 1, "name": "الشريحة الأولى", "min_pts": 0, "max_pts": 500000, "min_withdraw_znx": 1000.0, "fixed_fee_usd": 0.02},
        {"tier": 2, "name": "الشريحة الثانية", "min_pts": 500000, "max_pts": "inf", "min_withdraw_znx": 500.0, "fixed_fee_usd": 0.02}
    ], ensure_ascii=False)

    conn = None
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # 1. التأكد من كافة الأعمدة المطلوبة في جدول users
                cur.execute("""
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS znx_balance NUMERIC DEFAULT 0.0;
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS usd_balance NUMERIC DEFAULT 0.0;
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS balance NUMERIC DEFAULT 0.0;
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS wallet_address TEXT DEFAULT '';
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS wallets JSONB DEFAULT '{}'::jsonb;
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS is_banned BOOLEAN DEFAULT FALSE;
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS hourly_rate NUMERIC DEFAULT 0.0;
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS upgrades_count INTEGER DEFAULT 0;
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS storage_level INTEGER DEFAULT 1;
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS max_cap NUMERIC DEFAULT 0.0;
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS referral_count INTEGER DEFAULT 0;
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS ref_count INTEGER DEFAULT 0;
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP;
                """)

                # 2. جدول شرائح السحب العالمية znx_global_stats
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS znx_global_stats (
                        id TEXT PRIMARY KEY DEFAULT 'summary',
                        total_converted_znx NUMERIC DEFAULT 0.0,
                        tiers_config JSONB DEFAULT '[]'::jsonb,
                        updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                cur.execute("""
                    INSERT INTO znx_global_stats (id, total_converted_znx, tiers_config)
                    VALUES ('summary', 0.0, %s::jsonb)
                    ON CONFLICT (id) DO NOTHING;
                """, (default_tiers_json,))

                # 3. جدول معاملات السحب الرئيسي processed_txs
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS processed_txs (
                        id TEXT PRIMARY KEY,
                        tx_id TEXT UNIQUE NOT NULL,
                        user_id TEXT NOT NULL,
                        coins NUMERIC NOT NULL CHECK (coins > 0),
                        amount NUMERIC NOT NULL,
                        fee_usd NUMERIC DEFAULT 0.02,
                        net_coins NUMERIC NOT NULL,
                        currency TEXT DEFAULT 'ZNX',
                        tier_name TEXT DEFAULT '',
                        wallet_address TEXT NOT NULL,
                        type TEXT DEFAULT 'withdraw',
                        status TEXT DEFAULT 'pending',
                        processed_by TEXT,
                        processing_started_at TIMESTAMPTZ,
                        processed_at TIMESTAMPTZ,
                        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                    );
                    CREATE INDEX IF NOT EXISTS idx_processed_txs_user_status ON processed_txs(user_id, status);
                    CREATE INDEX IF NOT EXISTS idx_processed_txs_tx_id ON processed_txs(tx_id);
                """)

                # 4. جدول السجل العام للمعاملات transactions (متوافق مع history_db)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS transactions (
                        id TEXT PRIMARY KEY,
                        tx_id TEXT,
                        user_id TEXT NOT NULL,
                        coins NUMERIC DEFAULT 0.0,
                        amount NUMERIC DEFAULT 0.0,
                        fee_usd NUMERIC DEFAULT 0.0,
                        net_coins NUMERIC DEFAULT 0.0,
                        currency TEXT DEFAULT 'ZNX',
                        tier_name TEXT DEFAULT '',
                        wallet_address TEXT DEFAULT '',
                        type TEXT DEFAULT 'withdraw',
                        status TEXT DEFAULT 'pending',
                        processed_by TEXT,
                        processed_at TIMESTAMPTZ,
                        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                    );
                    ALTER TABLE transactions ADD COLUMN IF NOT EXISTS tx_id TEXT;
                    ALTER TABLE transactions ADD COLUMN IF NOT EXISTS coins NUMERIC DEFAULT 0.0;
                    ALTER TABLE transactions ADD COLUMN IF NOT EXISTS amount NUMERIC DEFAULT 0.0;
                    ALTER TABLE transactions ADD COLUMN IF NOT EXISTS fee_usd NUMERIC DEFAULT 0.0;
                    ALTER TABLE transactions ADD COLUMN IF NOT EXISTS net_coins NUMERIC DEFAULT 0.0;
                    ALTER TABLE transactions ADD COLUMN IF NOT EXISTS currency TEXT DEFAULT 'ZNX';
                    ALTER TABLE transactions ADD COLUMN IF NOT EXISTS tier_name TEXT DEFAULT '';
                    ALTER TABLE transactions ADD COLUMN IF NOT EXISTS wallet_address TEXT DEFAULT '';
                    ALTER TABLE transactions ADD COLUMN IF NOT EXISTS type TEXT DEFAULT 'withdraw';
                    ALTER TABLE transactions ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'pending';
                    ALTER TABLE transactions ADD COLUMN IF NOT EXISTS processed_by TEXT;
                    ALTER TABLE transactions ADD COLUMN IF NOT EXISTS processed_at TIMESTAMPTZ;
                    ALTER TABLE transactions ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP;
                    CREATE INDEX IF NOT EXISTS idx_transactions_user_id ON transactions(user_id);
                    CREATE INDEX IF NOT EXISTS idx_transactions_tx_id ON transactions(tx_id);
                """)

                # 5. جدول سجلات قرارات المشرفين admin_logs
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS admin_logs (
                        id BIGSERIAL PRIMARY KEY,
                        action TEXT NOT NULL,
                        tx_id TEXT,
                        user_id TEXT,
                        admin_id TEXT,
                        status TEXT,
                        amount NUMERIC DEFAULT 0.0,
                        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                    );
                    ALTER TABLE admin_logs ADD COLUMN IF NOT EXISTS tx_id TEXT;
                    ALTER TABLE admin_logs ADD COLUMN IF NOT EXISTS user_id TEXT;
                    ALTER TABLE admin_logs ADD COLUMN IF NOT EXISTS admin_id TEXT;
                    ALTER TABLE admin_logs ADD COLUMN IF NOT EXISTS status TEXT;
                    ALTER TABLE admin_logs ADD COLUMN IF NOT EXISTS amount NUMERIC DEFAULT 0.0;
                """)
            conn.commit()
        return True
    except Exception as e:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        print(f"⚠️ ملاحظة أثناء تهيئة جداول السحب تلقائياً: {e}")
        return False


class PostgresUserRef:
    """كلاس توافقي يحاكي user_ref في الكود القديم ليعمل مع Supabase PostgreSQL بسلاسة"""
    def __init__(self, user_id: str, data: dict):
        self.id = str(user_id)
        self.pk_col = "user_id"
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
            if isinstance(v, dict):
                set_clauses.append(f"{k} = %s::jsonb")
                values.append(json.dumps(v, ensure_ascii=False))
            else:
                set_clauses.append(f"{k} = %s")
                values.append(v)

        if not set_clauses:
            return False

        values.extend([self.id, self.id, self.id])
        sql = f"""
            UPDATE users
            SET {", ".join(set_clauses)}
            WHERE CAST(tg_id AS TEXT) = %s
               OR CAST(user_id AS TEXT) = %s
               OR CAST(telegram_id AS TEXT) = %s
        """
        conn = None
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, tuple(values))
                conn.commit()
            return True
        except Exception as e:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
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
    """جلب رصيد ZNX للمستخدم بشكل دقيق واعتماد حقل znx_balance فقط"""
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
    """جلب رصيد الدولار للمستخدم"""
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


def get_current_withdraw_tier():
    """جلب بيانات الشريحة الحالية لسحب العملات من Supabase مع Caching فائق السرعة"""
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
                tiers = _parse_json_val(stats.get("tiers_config"), [])

                res_tier = default_tier
                for item in tiers:
                    if not isinstance(item, dict):
                        continue
                    min_v = float(item.get("min_pts", 0.0) or 0.0)
                    raw_max = item.get("max_pts")
                    max_v = float("inf") if str(raw_max).lower() in ("inf", "infinity", "none", "null") else float(raw_max)
                    if min_v <= total_global_znx < max_v:
                        res_tier = {
                            "tier": int(item.get("tier", 1)),
                            "name": str(item.get("name", "الشريحة الحالية")),
                            "min_withdraw_znx": float(item.get("min_withdraw_znx", 1000.0)),
                            "fixed_fee_usd": float(item.get("fixed_fee_usd", 0.02))
                        }
                        break
                else:
                    if tiers and isinstance(tiers[-1], dict):
                        last = tiers[-1]
                        res_tier = {
                            "tier": int(last.get("tier", 7)),
                            "name": str(last.get("name", "الشريحة السابعة")),
                            "min_withdraw_znx": float(last.get("min_withdraw_znx", 2.5)),
                            "fixed_fee_usd": float(last.get("fixed_fee_usd", 0.02))
                        }

                _TIER_CACHE["data"] = res_tier
                _TIER_CACHE["timestamp"] = now
                return res_tier
    except Exception as e:
        print(f"⚠️ خطأ جلب شريحة السحب: {e}")

    return default_tier


def get_user_doc(user_id):
    """البحث عن سجل المستخدم في Supabase برقم الـ ID أو tg_id بسرعة وحماية"""
    clean_id = _sanitize_id(user_id)
    if not clean_id or not get_db_connection:
        return None, None

    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM users
                    WHERE CAST(tg_id AS TEXT) = %s
                       OR CAST(user_id AS TEXT) = %s
                       OR CAST(telegram_id AS TEXT) = %s
                    LIMIT 1
                """, (clean_id, clean_id, clean_id))
                row = cur.fetchone()
                if row:
                    data = dict(row)
                    return PostgresUserRef(clean_id, data), data
    except Exception as e:
        print(f"⚠️ خطأ جلب بيانات المستخدم في get_user_doc: {e}")

    return None, None


def get_user_full_details(user_id):
    """جلب كامل التفاصيل المطلوبة لإشعار السحب اليدوي للأدمن من Supabase"""
    try:
        clean_id = _sanitize_id(user_id)
        _, data = get_user_doc(clean_id)
        if not data:
            return None

        real_znx_balance = extract_user_balance(data)
        usd_balance = extract_usd_balance(data)
        zn_balance = float(data.get("balance", 0.0) or 0.0)

        wallets = _parse_json_val(data.get("wallets"), {})
        wallet_addr = data.get("wallet_address") or wallets.get("ZNX", "") or ""

        # 1. استخراج تاريخ التسجيل بوضوح
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

        # 2. سرعة التعدين والترقيات والمخازن
        hourly_rate = float(data.get("hourly_rate", 0.0) or 0.0)
        upgrades_count = int(data.get("upgrades_count", 0) or 0)
        storage_level = int(data.get("storage_level", 1) or 1)
        max_cap = float(data.get("max_cap", 0.0) or 0.0)

        # 3. حساب عدد الإحالات (الأصدقاء)
        ref_count = int(data.get("referral_count", 0) or data.get("ref_count", 0) or 0)
        if ref_count == 0 and get_db_connection:
            try:
                with get_db_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("""
                            SELECT COUNT(*) FROM users
                            WHERE CAST(referred_by AS TEXT) = %s OR CAST(ref_by AS TEXT) = %s
                        """, (clean_id, clean_id))
                        cnt_row = cur.fetchone()
                        if cnt_row and cnt_row[0]:
                            ref_count = int(cnt_row[0])
            except Exception:
                pass

        return {
            "user_id": str(clean_id),
            "first_name": data.get("first_name") or "غير محدد",
            "username": data.get("username") or "لا يوجد",
            "znx_balance": real_znx_balance,
            "zn_balance": zn_balance,
            "usd_balance": usd_balance,
            "joined_at": joined_str,
            "hourly_rate": hourly_rate,
            "upgrades_count": upgrades_count,
            "storage_level": storage_level,
            "max_cap": max_cap,
            "ref_count": ref_count,
            "is_banned": bool(data.get("is_banned", False)),
            "wallets": wallets,
            "wallet_address": wallet_addr
        }
    except Exception as e:
        print(f"⚠️ خطأ جلب تفاصيل المستخدم كاملة: {e}")
        return None


def save_user_wallet(user_id, currency, wallet_address):
    """حفظ عنوان المحفظة للمستخدم في Supabase بأمان"""
    clean_id = _sanitize_id(user_id)
    clean_wallet = str(wallet_address or "").strip()

    if not clean_id or not get_db_connection:
        return False, "تعذر الاتصال بقاعدة البيانات."

    if not is_valid_ton_address(clean_wallet):
        return False, "عنوان محفظة TON غير صالح."

    try:
        user_ref, user_data = get_user_doc(clean_id)
        if not user_ref or not user_data:
            return False, "المستخدم غير موجود في قاعدة البيانات."

        wallets = _parse_json_val(user_data.get("wallets"), {})
        wallets[str(currency or "ZNX").upper()] = clean_wallet

        ok = user_ref.update({
            "wallets": wallets,
            "wallet_address": clean_wallet
        })
        if ok:
            return True, "تم حفظ المحفظة بنجاح."
        return False, "تعذر تحديث المحفظة في قاعدة البيانات."
    except Exception as e:
        print(f"⚠️ خطأ حفظ المحفظة في Supabase: {e}")
        return False, f"خطأ أثناء الحفظ: {str(e)}"


# تهيئة الجداول تلقائياً عند استيراد الملف
init_withdraw_tables()
