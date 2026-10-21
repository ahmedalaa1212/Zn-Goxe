# -*- coding: utf-8 -*-
import os
import sys
import math

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "../"))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

try:
    from database import get_db_connection, _sanitize_id
except ImportError as e:
    print(f"⚠️ خطأ فادح: لم يتم العثور على database.py: {e}")
    get_db_connection = None

    def _sanitize_id(val):
        if val is None:
            return None
        s = str(val).strip()
        if s.endswith(".0"):
            s = s[:-2]
        return s if s and s.lower() not in ("none", "null", "undefined", "nan") else None


def init_wallet_tables():
    """إنشاء وتجهيز جداول المحفظة والسحب تلقائياً في Supabase PostgreSQL لمنع أي أخطاء مستقبلية"""
    if not get_db_connection:
        return

    conn = None
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # 1. التأكد من وجود الأعمدة المالية في جدول users
                cur.execute("""
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS balance DOUBLE PRECISION DEFAULT 0.0;
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS usd_balance DOUBLE PRECISION DEFAULT 0.0;
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS znx_balance DOUBLE PRECISION DEFAULT 0.0;
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS wallet_address TEXT DEFAULT '';
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS wallets JSONB DEFAULT '{}'::jsonb;
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS is_banned BOOLEAN DEFAULT FALSE;
                """)

                # 2. جدول طلبات السحب الرئيسي processed_txs
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS processed_txs (
                        id TEXT PRIMARY KEY,
                        tx_id TEXT UNIQUE NOT NULL,
                        user_id TEXT NOT NULL,
                        coins DOUBLE PRECISION NOT NULL CHECK (coins > 0),
                        amount DOUBLE PRECISION NOT NULL,
                        fee_usd DOUBLE PRECISION DEFAULT 0.02,
                        net_coins DOUBLE PRECISION NOT NULL,
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
                """)

                # 3. جدول المعاملات العام transactions
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS transactions (
                        id TEXT PRIMARY KEY,
                        tx_id TEXT UNIQUE,
                        user_id TEXT NOT NULL,
                        coins DOUBLE PRECISION DEFAULT 0.0,
                        amount DOUBLE PRECISION DEFAULT 0.0,
                        fee_usd DOUBLE PRECISION DEFAULT 0.0,
                        net_coins DOUBLE PRECISION DEFAULT 0.0,
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
                    CREATE INDEX IF NOT EXISTS idx_transactions_user_id ON transactions(user_id);
                """)

                # 4. جدول شرائح السحب والإحصائيات العالمية znx_global_stats
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS znx_global_stats (
                        id TEXT PRIMARY KEY DEFAULT 'summary',
                        total_converted_znx DOUBLE PRECISION DEFAULT 0.0,
                        tiers_config JSONB DEFAULT '[]'::jsonb,
                        updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                    );
                """)
            conn.commit()
    except Exception as e:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        print(f"⚠️ Notice in init_wallet_tables: {e}")


def get_user_wallet_balances(user_id) -> dict:
    """جلب الأرصدة المباشرة من Supabase مع دعم البحث في كافة أعمدة المعرف وإعادة المحاولة"""
    clean_id = _sanitize_id(user_id)
    default_balances = {
        "zn_balance": 0.0,
        "usdt_balance": 0.0,
        "znx_balance": 0.0,
        "db_ok": False
    }

    if not clean_id or not get_db_connection:
        return default_balances

    for attempt in range(2):
        conn = None
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT
                            GREATEST(0.0, COALESCE(balance, 0.0)),
                            GREATEST(0.0, COALESCE(usd_balance, 0.0)),
                            GREATEST(0.0, COALESCE(znx_balance, 0.0))
                        FROM users
                        WHERE CAST(tg_id AS TEXT) = %s
                           OR CAST(user_id AS TEXT) = %s
                           OR CAST(telegram_id AS TEXT) = %s
                        LIMIT 1
                    """, (clean_id, clean_id, clean_id))

                    row = cur.fetchone()
                    if row:
                        return {
                            "zn_balance": float(row[0] if row[0] is not None else 0.0),
                            "usdt_balance": float(row[1] if row[1] is not None else 0.0),
                            "znx_balance": float(row[2] if row[2] is not None else 0.0),
                            "db_ok": True
                        }
                    else:
                        return {
                            "zn_balance": 0.0,
                            "usdt_balance": 0.0,
                            "znx_balance": 0.0,
                            "db_ok": True
                        }
        except Exception as e:
            print(f"⚠️ Database Fetch Error (Attempt {attempt + 1}): {e}")

    return default_balances


def update_user_balance(user_id, amount: float, currency: str = "zn", operation: str = "add") -> bool:
    """
    تحديث الأرصدة في Supabase ذرياً وبأمان تام.
    في حالة الخصم (subtract): يمنع الخصم إذا كان الرصيد الحالي أقل من المبلغ المطلوب (منع الرصيد السالب والغش).
    """
    clean_id = _sanitize_id(user_id)
    if not clean_id or not get_db_connection:
        return False

    try:
        raw_amount = float(amount)
        if math.isnan(raw_amount) or math.isinf(raw_amount) or raw_amount < 0:
            return False
        amount_val = abs(raw_amount)
    except (ValueError, TypeError):
        return False

    if amount_val == 0:
        return True

    curr = str(currency).lower().strip()
    if curr in ("zn", "balance"):
        field_to_update = "balance"
    elif curr in ("znx", "znx_balance", "total_znx_earned"):
        field_to_update = "znx_balance"
    elif curr in ("usd", "usdt", "usd_balance", "usdt_balance"):
        field_to_update = "usd_balance"
    else:
        return False

    op = str(operation).lower().strip()
    if op not in ("add", "subtract", "sub"):
        return False

    for attempt in range(2):
        conn = None
        try:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    if op in ("subtract", "sub"):
                        # خصم ذري مشروط بتوفر الرصيد الكافي لمنع ثغرات Double Spending
                        cur.execute(f"""
                            UPDATE users
                            SET {field_to_update} = ROUND(CAST(COALESCE({field_to_update}, 0.0) - %s AS NUMERIC), 6),
                                last_active_at = CURRENT_TIMESTAMP
                            WHERE (CAST(tg_id AS TEXT) = %s OR CAST(user_id AS TEXT) = %s OR CAST(telegram_id AS TEXT) = %s)
                              AND COALESCE({field_to_update}, 0.0) >= %s
                            RETURNING {field_to_update}
                        """, (amount_val, clean_id, clean_id, clean_id, amount_val))
                    else:
                        # إضافة ذرية آمنة
                        cur.execute(f"""
                            UPDATE users
                            SET {field_to_update} = ROUND(CAST(GREATEST(0.0, COALESCE({field_to_update}, 0.0)) + %s AS NUMERIC), 6),
                                last_active_at = CURRENT_TIMESTAMP
                            WHERE (CAST(tg_id AS TEXT) = %s OR CAST(user_id AS TEXT) = %s OR CAST(telegram_id AS TEXT) = %s)
                            RETURNING {field_to_update}
                        """, (amount_val, clean_id, clean_id, clean_id))

                    updated_row = cur.fetchone()
                    conn.commit()
                    return updated_row is not None
        except Exception as e:
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
            print(f"⚠️ Database Update Error (Attempt {attempt + 1}): {e}")

    return False


# تهيئة الجداول الأساسية تلقائياً عند استيراد الملف
init_wallet_tables()

# الاستيراد الآمن للقوائم الفرعية وتهيئة الجداول تلقائياً
try:
    from .deposit.deposit_db import *
except Exception:
    try:
        from deposit.deposit_db import *
    except Exception as e:
        print(f"⚠️ Notice importing deposit_db: {e}")

try:
    from .history.history_db import *
    init_history_tables()
except Exception:
    try:
        from history.history_db import *
        init_history_tables()
    except Exception as e:
        print(f"⚠️ Notice importing history_db: {e}")

try:
    from .withdraw.withdraw_db import *
except Exception:
    try:
        from withdraw.withdraw_db import *
    except Exception as e:
        print(f"⚠️ Notice importing withdraw_db: {e}")
