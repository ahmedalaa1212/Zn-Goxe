# -*- coding: utf-8 -*-
import os
import sys
import uuid
import time
import json
import base64
import hashlib
import urllib.request
from datetime import datetime
from psycopg2.extras import RealDictCursor, Json

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "../../"))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

try:
    from database import (
        get_db_connection,
        get_db_transaction,
        _sanitize_id,
        atomic_update_balance,
        get_user_balances,
    )
except ImportError as e:
    print(f"⚠️ خطأ في الاستيراد من database.py: {e}")

    def _sanitize_id(val):
        if val is None:
            return None
        s = str(val).strip()
        return s[:-2] if s.endswith('.0') else s

    get_db_transaction = None

SEED_PACKAGES = [
    {'id': 1, 'usdt_amount': 0.5, 'name_ar': 'باقة $0.5 USDT', 'is_active': True, 'sort_order': 1},
    {'id': 2, 'usdt_amount': 1.5, 'name_ar': 'باقة $1.5 USDT', 'is_active': True, 'sort_order': 2},
    {'id': 3, 'usdt_amount': 5.0, 'name_ar': 'باقة $5 USDT', 'is_active': True, 'sort_order': 3},
    {'id': 4, 'usdt_amount': 10.0, 'name_ar': 'باقة $10 USDT', 'is_active': True, 'sort_order': 4},
    {'id': 5, 'usdt_amount': 15.0, 'name_ar': 'باقة $15 USDT', 'is_active': True, 'sort_order': 5}
]

_tables_initialized = False


def get_official_ton_wallet():
    """جلب عنوان محفظة TON للاستلام من متغيرات البيئة"""
    env_wallet = (
        os.getenv('TON_WALLET_ADDRESS')
        or os.getenv('OFFICIAL_TON_WALLET')
        or os.getenv('TON_WALLET')
        or os.getenv('PROJECT_WALLET')
        or ''
    )
    return str(env_wallet).strip()


def _exec_safe(conn, cur, sql, params=None):
    """تنفيذ أمر SQL بأمان تام مع دعم autocommit أو rollback"""
    try:
        if params is not None:
            cur.execute(sql, params)
        else:
            cur.execute(sql)
        if not getattr(conn, 'autocommit', False):
            conn.commit()
        return True
    except Exception:
        try:
            if not getattr(conn, 'autocommit', False):
                conn.rollback()
        except Exception:
            pass
        return False


def init_deposit_tables():
    """تهيئة جداول الإيداع في Supabase بأمان وسرعة"""
    global _tables_initialized
    if _tables_initialized:
        return
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # 1. جدول الباقات (deposit_packages)
                _exec_safe(conn, cur, '''
                    CREATE TABLE IF NOT EXISTS deposit_packages (
                        id SERIAL PRIMARY KEY,
                        usdt_amount NUMERIC NOT NULL,
                        name_ar VARCHAR(255),
                        is_active BOOLEAN DEFAULT TRUE,
                        sort_order INTEGER DEFAULT 0
                    )
                ''')

                # 2. جدول فواتير الإيداع (deposit_invoices)
                _exec_safe(conn, cur, '''
                    CREATE TABLE IF NOT EXISTS deposit_invoices (
                        id SERIAL PRIMARY KEY,
                        invoice_id TEXT,
                        user_id VARCHAR(255) NOT NULL,
                        usdt_amount NUMERIC(18, 4) NOT NULL DEFAULT 0.0,
                        amount NUMERIC(18, 4) DEFAULT 0.0,
                        ton_amount NUMERIC(18, 4) NOT NULL DEFAULT 0.0,
                        currency VARCHAR(32) DEFAULT 'USDT',
                        memo VARCHAR(255) UNIQUE NOT NULL,
                        tx_hash TEXT,
                        wallet_address TEXT,
                        status VARCHAR(50) DEFAULT 'pending',
                        details TEXT,
                        failure_reason TEXT,
                        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

                # 3. جدول المعاملات المكتملة (processed_txs)
                _exec_safe(conn, cur, '''
                    CREATE TABLE IF NOT EXISTS processed_txs (
                        tx_hash VARCHAR(256) PRIMARY KEY,
                        user_id VARCHAR(255),
                        usdt_amount NUMERIC(18, 4) DEFAULT 0.0,
                        amount NUMERIC(18, 4) DEFAULT 0.0,
                        ton_amount NUMERIC(18, 4) DEFAULT 0.0,
                        currency VARCHAR(32) DEFAULT 'USDT',
                        memo TEXT,
                        boc TEXT,
                        wallet_address TEXT,
                        type VARCHAR(64) DEFAULT 'deposit',
                        status VARCHAR(50) DEFAULT 'completed',
                        details TEXT,
                        failure_reason TEXT,
                        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                        processed_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

                # 4. جدول السجل الموحد (transactions)
                _exec_safe(conn, cur, '''
                    CREATE TABLE IF NOT EXISTS transactions (
                        id SERIAL PRIMARY KEY,
                        tx_id TEXT,
                        user_id TEXT NOT NULL,
                        type TEXT NOT NULL,
                        amount NUMERIC(18, 4) NOT NULL DEFAULT 0.0,
                        currency TEXT DEFAULT 'USDT',
                        status TEXT DEFAULT 'pending',
                        wallet_address TEXT,
                        memo TEXT,
                        details TEXT,
                        failure_reason TEXT,
                        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                    )
                ''')

                alter_queries = [
                    "ALTER TABLE deposit_packages ADD COLUMN IF NOT EXISTS name_ar VARCHAR(255);",
                    "ALTER TABLE deposit_packages ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;",
                    "ALTER TABLE deposit_packages ADD COLUMN IF NOT EXISTS sort_order INTEGER DEFAULT 0;",
                    "ALTER TABLE deposit_invoices ADD COLUMN IF NOT EXISTS invoice_id TEXT;",
                    "ALTER TABLE deposit_invoices ADD COLUMN IF NOT EXISTS amount NUMERIC(18, 4) DEFAULT 0.0;",
                    "ALTER TABLE deposit_invoices ADD COLUMN IF NOT EXISTS ton_amount NUMERIC(18, 4) DEFAULT 0.0;",
                    "ALTER TABLE deposit_invoices ADD COLUMN IF NOT EXISTS currency VARCHAR(32) DEFAULT 'USDT';",
                    "ALTER TABLE deposit_invoices ADD COLUMN IF NOT EXISTS tx_hash TEXT;",
                    "ALTER TABLE deposit_invoices ADD COLUMN IF NOT EXISTS wallet_address TEXT;",
                    "ALTER TABLE deposit_invoices ADD COLUMN IF NOT EXISTS status VARCHAR(50) DEFAULT 'pending';",
                    "ALTER TABLE deposit_invoices ADD COLUMN IF NOT EXISTS details TEXT;",
                    "ALTER TABLE deposit_invoices ADD COLUMN IF NOT EXISTS failure_reason TEXT;",
                    "ALTER TABLE deposit_invoices ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP;",
                    "ALTER TABLE deposit_invoices ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP;",
                    "ALTER TABLE processed_txs ADD COLUMN IF NOT EXISTS user_id VARCHAR(255);",
                    "ALTER TABLE processed_txs ADD COLUMN IF NOT EXISTS usdt_amount NUMERIC(18, 4) DEFAULT 0.0;",
                    "ALTER TABLE processed_txs ADD COLUMN IF NOT EXISTS amount NUMERIC(18, 4) DEFAULT 0.0;",
                    "ALTER TABLE processed_txs ADD COLUMN IF NOT EXISTS ton_amount NUMERIC(18, 4) DEFAULT 0.0;",
                    "ALTER TABLE processed_txs ADD COLUMN IF NOT EXISTS currency VARCHAR(32) DEFAULT 'USDT';",
                    "ALTER TABLE processed_txs ADD COLUMN IF NOT EXISTS memo TEXT;",
                    "ALTER TABLE processed_txs ADD COLUMN IF NOT EXISTS boc TEXT;",
                    "ALTER TABLE processed_txs ADD COLUMN IF NOT EXISTS wallet_address TEXT;",
                    "ALTER TABLE processed_txs ADD COLUMN IF NOT EXISTS type VARCHAR(64) DEFAULT 'deposit';",
                    "ALTER TABLE processed_txs ADD COLUMN IF NOT EXISTS status VARCHAR(50) DEFAULT 'completed';",
                    "ALTER TABLE processed_txs ADD COLUMN IF NOT EXISTS details TEXT;",
                    "ALTER TABLE processed_txs ADD COLUMN IF NOT EXISTS failure_reason TEXT;",
                    "ALTER TABLE processed_txs ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP;",
                    "ALTER TABLE processed_txs ADD COLUMN IF NOT EXISTS processed_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP;",
                    "ALTER TABLE processed_txs ALTER COLUMN details TYPE TEXT USING details::TEXT;",
                    "ALTER TABLE deposit_invoices ALTER COLUMN details TYPE TEXT USING details::TEXT;",
                    "ALTER TABLE transactions ALTER COLUMN details TYPE TEXT USING details::TEXT;"
                ]
                for q in alter_queries:
                    _exec_safe(conn, cur, q)

                if _exec_safe(conn, cur, "SELECT COUNT(*) FROM deposit_packages"):
                    row = cur.fetchone()
                    count = row[0] if row else 0
                    if count == 0:
                        for pkg in SEED_PACKAGES:
                            _exec_safe(conn, cur, """
                                INSERT INTO deposit_packages (usdt_amount, name_ar, is_active, sort_order)
                                VALUES (%s, %s, %s, %s)
                            """, (pkg['usdt_amount'], f"باقة ${pkg['usdt_amount']:g} USDT", pkg['is_active'], pkg['sort_order']))

            _tables_initialized = True
    except Exception as e:
        print(f"⚠️ خطأ في تهيئة جداول الإيداع في Supabase: {e}")


# ==================== دوال حفظ واسترجاع المحفظة المربوطة في Supabase ====================

def get_user_bound_wallet(user_id):
    """جلب المحفظة المربوطة للمستخدم من جدول users في Supabase لضمان بقائها مربوطة دائماً"""
    clean_id = _sanitize_id(user_id)
    if not clean_id or clean_id == "0":
        return {"wallet_address": "", "wallet_name": ""}
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT wallet_address, wallets
                    FROM users
                    WHERE tg_id = %s OR user_id = %s OR telegram_id = %s
                    LIMIT 1
                """, (clean_id, clean_id, clean_id))
                row = cur.fetchone()
                if not row:
                    return {"wallet_address": "", "wallet_name": ""}

                wallets_obj = row.get("wallets")
                if isinstance(wallets_obj, str):
                    try:
                        wallets_obj = json.loads(wallets_obj)
                    except Exception:
                        wallets_obj = {}
                if not isinstance(wallets_obj, dict):
                    wallets_obj = {}

                deposit_addr = (
                    str(wallets_obj.get("deposit_wallet") or row.get("wallet_address") or "").strip()
                )
                deposit_name = str(wallets_obj.get("deposit_wallet_name") or "محفظة TON").strip()
                return {
                    "wallet_address": deposit_addr,
                    "wallet_name": deposit_name if deposit_addr else "",
                }
    except Exception as e:
        print(f"⚠️ خطأ جلب المحفظة المربوطة من Supabase: {e}")
        return {"wallet_address": "", "wallet_name": ""}


def save_user_bound_wallet(user_id, wallet_address: str, wallet_name: str = "محفظة TON") -> bool:
    """حفظ عنوان واسم المحفظة المربوطة في Supabase لتظل مربوطة دائماً حتى يغيرها المستخدم"""
    clean_id = _sanitize_id(user_id)
    clean_addr = str(wallet_address or "").strip()
    clean_name = str(wallet_name or "محفظة TON").strip()[:64]
    if not clean_id or clean_id == "0" or not clean_addr:
        return False

    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT wallets, wallet_address
                    FROM users
                    WHERE tg_id = %s OR user_id = %s OR telegram_id = %s
                    LIMIT 1
                """, (clean_id, clean_id, clean_id))
                row = cur.fetchone()
                wallets_obj = {}
                if row and row.get("wallets"):
                    raw_w = row.get("wallets")
                    if isinstance(raw_w, dict):
                        wallets_obj = dict(raw_w)
                    elif isinstance(raw_w, str):
                        try:
                            wallets_obj = json.loads(raw_w)
                        except Exception:
                            wallets_obj = {}

                wallets_obj["deposit_wallet"] = clean_addr
                wallets_obj["deposit_wallet_name"] = clean_name
                wallets_obj["updated_at"] = int(time.time())

                cur.execute("""
                    UPDATE users
                    SET wallet_address = COALESCE(NULLIF(wallet_address, ''), %s),
                        wallets = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE tg_id = %s OR user_id = %s OR telegram_id = %s
                """, (clean_addr, Json(wallets_obj), clean_id, clean_id, clean_id))
        return True
    except Exception as e:
        print(f"⚠️ خطأ حفظ المحفظة المربوطة في Supabase: {e}")
        return False


def clear_user_bound_wallet(user_id) -> bool:
    """إلغاء ربط محفظة الإيداع في Supabase فقط عندما يضغط المستخدم يدوياً على إلغاء الربط"""
    clean_id = _sanitize_id(user_id)
    if not clean_id or clean_id == "0":
        return False

    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT wallets
                    FROM users
                    WHERE tg_id = %s OR user_id = %s OR telegram_id = %s
                    LIMIT 1
                """, (clean_id, clean_id, clean_id))
                row = cur.fetchone()
                wallets_obj = {}
                if row and row.get("wallets"):
                    raw_w = row.get("wallets")
                    if isinstance(raw_w, dict):
                        wallets_obj = dict(raw_w)
                    elif isinstance(raw_w, str):
                        try:
                            wallets_obj = json.loads(raw_w)
                        except Exception:
                            wallets_obj = {}

                wallets_obj.pop("deposit_wallet", None)
                wallets_obj.pop("deposit_wallet_name", None)

                cur.execute("""
                    UPDATE users
                    SET wallets = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE tg_id = %s OR user_id = %s OR telegram_id = %s
                """, (Json(wallets_obj), clean_id, clean_id, clean_id))
        return True
    except Exception as e:
        print(f"⚠️ خطأ إلغاء ربط المحفظة في Supabase: {e}")
        return False


# ==================== دوال الباقات والفواتير ====================

def get_active_deposit_packages():
    """جلب الباقات النشطة مباشرة من جدول deposit_packages في Supabase"""
    init_deposit_tables()
    packages = []
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, usdt_amount, COALESCE(is_active, TRUE), COALESCE(sort_order, id), name_ar
                    FROM deposit_packages
                    WHERE COALESCE(is_active, TRUE) = TRUE
                    ORDER BY COALESCE(sort_order, id) ASC, id ASC
                """)
                rows = cur.fetchall()
                for row in rows:
                    pkg_id = row[0]
                    usdt_val = float(row[1] or 0.0)
                    custom_name = row[4] if len(row) > 4 and row[4] else f"باقة ${usdt_val:g} USDT"
                    packages.append({
                        'id': pkg_id,
                        'usdt_amount': usdt_val,
                        'name_ar': custom_name,
                        'is_active': bool(row[2]),
                        'sort_order': int(row[3] or 0)
                    })
        if packages:
            return packages
    except Exception as e:
        print(f"❌ خطأ جلب الباقات من Supabase: {e}")

    return SEED_PACKAGES


def get_package_by_id(pkg_id):
    if pkg_id is None:
        return None
    packages = get_active_deposit_packages()
    for pkg in packages:
        if str(pkg.get('id')) == str(pkg_id):
            return pkg
    return None


def get_deposit_invoice_by_memo(memo: str, user_id: str = None):
    """جلب الفاتورة من قاعدة البيانات للتحقق من ملكيتها وقيمتها الفعلية"""
    if not memo:
        return None
    init_deposit_tables()
    clean_memo = str(memo).strip()
    clean_uid = _sanitize_id(user_id) if user_id else None
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                if clean_uid:
                    cur.execute("""
                        SELECT * FROM deposit_invoices
                        WHERE memo = %s AND user_id = %s
                        LIMIT 1
                    """, (clean_memo, clean_uid))
                else:
                    cur.execute("""
                        SELECT * FROM deposit_invoices
                        WHERE memo = %s
                        LIMIT 1
                    """, (clean_memo,))
                row = cur.fetchone()
                return dict(row) if row else None
    except Exception as e:
        print(f"⚠️ خطأ جلب الفاتورة get_deposit_invoice_by_memo: {e}")
        return None


def create_deposit_invoice(user_id, usdt_amount: float, ton_amount: float, sender_wallet: str = None) -> dict:
    """إنشاء فاتورة إيداع مبدئية في Supabase بحالة قيد المراجعة (pending)"""
    init_deposit_tables()
    user_id_clean = _sanitize_id(user_id)
    if not user_id_clean or user_id_clean == "0":
        raise ValueError("معرف المستخدم غير صالح لإنشاء فاتورة الإيداع")

    if sender_wallet:
        save_user_bound_wallet(user_id_clean, sender_wallet)

    memo = f"DEP-{user_id_clean}-{uuid.uuid4().hex[:8].upper()}"
    details_text = f"إيداع باقة ${usdt_amount:g} USDT (~{ton_amount:.4f} TON) عبر شبكة TON"
    details_payload = json.dumps({"text": details_text, "memo": memo, "usdt": usdt_amount}, ensure_ascii=False)

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                ok = _exec_safe(conn, cur, """
                    INSERT INTO deposit_invoices 
                    (user_id, usdt_amount, amount, ton_amount, currency, memo, wallet_address, status, details, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, 'USDT', %s, %s, 'pending', %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    RETURNING id
                """, (user_id_clean, usdt_amount, usdt_amount, ton_amount, memo, sender_wallet, details_payload))

                if ok:
                    row = cur.fetchone()
                    invoice_id = row[0] if row else 0
                else:
                    _exec_safe(conn, cur, """
                        INSERT INTO deposit_invoices (user_id, usdt_amount, ton_amount, memo, status)
                        VALUES (%s, %s, %s, %s, 'pending')
                        RETURNING id
                    """, (user_id_clean, usdt_amount, ton_amount, memo))
                    row = cur.fetchone()
                    invoice_id = row[0] if row else 0

        return {
            'invoice_id': invoice_id,
            'user_id': user_id_clean,
            'usdt_amount': usdt_amount,
            'ton_amount': ton_amount,
            'memo': memo
        }
    except Exception as e:
        print(f"⚠️ خطأ إنشاء الفاتورة في Supabase: {e}")
        raise Exception("تعذر تسجيل فاتورة الإيداع في قاعدة البيانات")


def update_deposit_invoice_status(memo: str, status: str = 'cancelled', failure_reason: str = None, delete_if_cancelled: bool = True, user_id: str = None) -> bool:
    """تحديث حالة الفاتورة عند الإلغاء أو الفشل مع التحقق من ملكية المستخدم للفاتورة"""
    if not memo:
        return False
    init_deposit_tables()
    clean_memo = str(memo).strip()
    clean_uid = _sanitize_id(user_id) if user_id else None
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                if status in ['cancelled', 'canceled'] and delete_if_cancelled:
                    if clean_uid:
                        _exec_safe(conn, cur, "DELETE FROM deposit_invoices WHERE memo = %s AND user_id = %s AND status = 'pending'", (clean_memo, clean_uid))
                    else:
                        _exec_safe(conn, cur, "DELETE FROM deposit_invoices WHERE memo = %s AND status = 'pending'", (clean_memo,))
                else:
                    if clean_uid:
                        _exec_safe(conn, cur, """
                            UPDATE deposit_invoices 
                            SET status = %s,
                                failure_reason = COALESCE(%s, failure_reason),
                                updated_at = CURRENT_TIMESTAMP
                            WHERE memo = %s AND user_id = %s AND status != 'completed'
                        """, (status, failure_reason, clean_memo, clean_uid))
                    else:
                        _exec_safe(conn, cur, """
                            UPDATE deposit_invoices 
                            SET status = %s,
                                failure_reason = COALESCE(%s, failure_reason),
                                updated_at = CURRENT_TIMESTAMP
                            WHERE memo = %s AND status != 'completed'
                        """, (status, failure_reason, clean_memo))
        return True
    except Exception as e:
        print(f"⚠️ خطأ تحديث حالة الفاتورة: {e}")
        return False


# ==================== التحقق الجنائي من معاملات TON على البلوكشين ====================

def is_valid_ton_boc(boc_str: str) -> bool:
    """فحص أمني صارم للتأكد من أن الـ BOC المرسل هو خلية BOC حقيقية من محفظة TON وليس نصاً مزوراً"""
    if not boc_str or not isinstance(boc_str, str):
        return False
    clean_boc = boc_str.strip()
    if len(clean_boc) < 32 or clean_boc.startswith("BOC-MANUAL") or clean_boc.startswith("TX_"):
        return False
    try:
        padded = clean_boc + "=" * (-len(clean_boc) % 4)
        raw_bytes = base64.b64decode(padded)
        if len(raw_bytes) < 12:
            return False
        magic = raw_bytes[:4].hex().lower()
        return magic in ("b5ee9c72", "68ff65f3", "acc3a728")
    except Exception:
        return False


def _is_tx_hash_already_used(tx_hash: str) -> bool:
    if not tx_hash:
        return False
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM processed_txs WHERE tx_hash = %s LIMIT 1", (str(tx_hash).strip(),))
                return cur.fetchone() is not None
    except Exception:
        return False


def verify_ton_deposit_onchain(min_nano_ton: int, expected_memo: str, boc: str = None, created_after_ts: int = None) -> tuple[bool, str | None]:
    """
    التحقق الفعلي الصارم عبر TonCenter API من وصول مبلغ TON المطلوب إلى محفظة المشروع الرسمية
    وتطابق الـ Memo الفريد للفاتورة لمنع أي إيداع وهمي أو تزوير.
    """
    official_wallet = get_official_ton_wallet()
    if not official_wallet or min_nano_ton <= 0 or not expected_memo:
        return False, None

    if not is_valid_ton_boc(boc):
        return False, None

    headers = {'User-Agent': 'Mozilla/5.0'}
    now_ts = int(time.time())
    min_utime = int(created_after_ts - 90) if created_after_ts else (now_ts - 1800)

    try:
        url = f"https://toncenter.com/api/v2/getTransactions?address={official_wallet}&limit=35"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            if data.get('ok') and 'result' in data:
                for tx in data['result']:
                    in_msg = tx.get('in_msg', {})
                    val = int(in_msg.get('value', 0))
                    tx_utime = int(tx.get('utime', 0))
                    msg_hash = str(tx.get('transaction_id', {}).get('hash', '')).strip()

                    if not msg_hash or val <= 0 or tx_utime < min_utime:
                        continue

                    # التحقق من القيمة المالية المستلمة (مع هامش سماح 4% لكسور التحويل)
                    if val < int(min_nano_ton * 0.96):
                        continue

                    decoded_body = in_msg.get('decoded_body') if isinstance(in_msg.get('decoded_body'), dict) else {}
                    msg_memo = str(in_msg.get('message', '') or decoded_body.get('text', '') or '').strip()

                    # شرط صارم: تطابق الميمو الفريد الخاص بالفاتورة وعدم صرف المعاملة مسبقاً
                    if expected_memo in msg_memo:
                        if not _is_tx_hash_already_used(msg_hash):
                            return True, msg_hash
    except Exception as e:
        print(f"⚠️ [Deposit TonCenter Verification Warning]: {e}")

    return False, None


def verify_and_process_ton_boc(user_id, usdt_amount: float, memo: str, boc: str, ton_amount: float = 0.0, sender_wallet: str = None) -> float:
    """
    معالجة معاملة الإيداع بأمان فائق:
    1. التحقق من صحة الـ BOC والفاتورة المسجلة في deposit_invoices وملكيتها للمستخدم.
    2. التحقق الفعلي من وصول الأموال على شبكة TON (TonCenter API) بمطابقة الـ Memo والمبلغ.
    3. قفل الفاتورة ذرياً عبر get_db_transaction (FOR UPDATE) لمنع التكرار (Double-Spending).
    """
    init_deposit_tables()
    user_id_clean = _sanitize_id(user_id)
    clean_memo = str(memo or "").strip()
    clean_boc = str(boc or "").strip()

    if not user_id_clean or user_id_clean == "0":
        raise ValueError("معرف المستخدم غير صالح")

    if not clean_memo:
        raise ValueError("رقم الفاتورة (Memo) مفقود")

    if not is_valid_ton_boc(clean_boc):
        raise ValueError("كود تأكيد المعاملة (BOC) غير صالح أو غير حقيقي")

    # 1. جلب الفاتورة من قاعدة البيانات للتأكد من وجودها وملكيتها للمستخدم وأخذ المبالغ الحقيقية منها
    invoice_row = get_deposit_invoice_by_memo(clean_memo, user_id=user_id_clean)
    if not invoice_row:
        raise ValueError("الفاتورة غير موجودة أو لا تخص هذا الحساب")

    if str(invoice_row.get("status")) == "completed":
        raise ValueError("تم تأكيد وشحن هذه الفاتورة مسبقاً!")

    db_usdt_amount = float(invoice_row.get("usdt_amount") or 0.0)
    db_ton_amount = float(invoice_row.get("ton_amount") or 0.0)
    if db_usdt_amount <= 0 or db_ton_amount <= 0:
        raise ValueError("بيانات قيمة الفاتورة المسجلة غير صالحة")

    expected_nano_ton = int(round(db_ton_amount * 1e9))
    created_dt = invoice_row.get("created_at")
    created_ts = int(created_dt.timestamp()) if isinstance(created_dt, datetime) else (int(time.time()) - 600)

    # 2. فحص البلوكشين الفعلي (حتى 4 محاولات بفاصل 3 ثوانٍ لإعطاء الشبكة وقتاً لتأكيد الكتلة)
    verified_onchain = False
    confirmed_chain_hash = None
    for attempt in range(4):
        verified_onchain, confirmed_chain_hash = verify_ton_deposit_onchain(
            min_nano_ton=expected_nano_ton,
            expected_memo=clean_memo,
            boc=clean_boc,
            created_after_ts=created_ts,
        )
        if verified_onchain and confirmed_chain_hash:
            break
        if attempt < 3:
            time.sleep(3)

    if not verified_onchain or not confirmed_chain_hash:
        raise ValueError("لم يتم رصد وصول المعاملة على شبكة TON بعد، يرجى التأكد من إتمام التحويل والمحاولة بعد لحظات.")

    boc_hash = hashlib.sha256(clean_boc.encode('utf-8')).hexdigest()
    tx_hash = str(confirmed_chain_hash).strip()

    details_text = f"إيداع ناجح بقيمة ${db_usdt_amount:g} USDT ({db_ton_amount:.4f} TON) | الفاتورة: {clean_memo}"
    details_payload = json.dumps(
        {"text": details_text, "memo": clean_memo, "usdt": db_usdt_amount, "chain_hash": tx_hash},
        ensure_ascii=False,
    )

    tx_ctx = get_db_transaction() if callable(get_db_transaction) else get_db_connection()

    try:
        with tx_ctx as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # 3. قفل صف الفاتورة ذرياً لمنع Race Condition
                cur.execute("""
                    SELECT id, user_id, status, usdt_amount, ton_amount
                    FROM deposit_invoices
                    WHERE memo = %s AND user_id = %s
                    FOR UPDATE
                """, (clean_memo, user_id_clean))
                locked_inv = cur.fetchone()
                if not locked_inv:
                    raise ValueError("الفاتورة غير موجودة")
                if str(locked_inv.get("status")) == "completed":
                    raise ValueError("تم تأكيد وشحن هذه الفاتورة مسبقاً!")

                # 4. فحص عدم تكرار هاش البلوكشين أو هاش الـ BOC أو الميمو في processed_txs
                cur.execute("""
                    SELECT tx_hash FROM processed_txs
                    WHERE tx_hash IN (%s, %s) OR (memo = %s AND status = 'completed')
                    LIMIT 1
                """, (tx_hash, boc_hash, clean_memo))
                if cur.fetchone():
                    raise ValueError("هذه المعاملة تم استخدامها وشحنها سابقاً!")

                # 5. إدراج المعاملة في processed_txs
                cur.execute("""
                    INSERT INTO processed_txs 
                    (tx_hash, user_id, usdt_amount, amount, ton_amount, currency, memo, boc, wallet_address, type, status, details, created_at, processed_at)
                    VALUES (%s, %s, %s, %s, %s, 'USDT', %s, %s, %s, 'deposit', 'completed', %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """, (
                    tx_hash,
                    user_id_clean,
                    db_usdt_amount,
                    db_usdt_amount,
                    db_ton_amount,
                    clean_memo,
                    boc_hash,
                    sender_wallet,
                    details_payload,
                ))

                # 6. تحديث حالة الفاتورة إلى مكتملة (completed)
                cur.execute("""
                    UPDATE deposit_invoices 
                    SET status = 'completed',
                        tx_hash = %s,
                        wallet_address = COALESCE(%s, wallet_address),
                        details = %s,
                        failure_reason = NULL,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE memo = %s AND user_id = %s
                """, (tx_hash, sender_wallet, details_payload, clean_memo, user_id_clean))

                # 7. تسجيل العملية في جدول السجلات الموحد (transactions)
                cur.execute("""
                    INSERT INTO transactions
                    (tx_id, tx_hash, user_id, tg_id, type, amount, currency, status, wallet_address, memo, details, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, 'deposit', %s, 'USDT', 'completed', %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """, (tx_hash, tx_hash, user_id_clean, user_id_clean, db_usdt_amount, sender_wallet, clean_memo, details_payload))

                # 8. تحديث رصيد المستخدم من الدولار ذرياً داخل نفس المعاملة المغلقة
                cur.execute("""
                    UPDATE users 
                    SET usd_balance = COALESCE(usd_balance, 0.0) + %s,
                        last_active_at = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE (tg_id = %s OR user_id = %s OR telegram_id = %s)
                      AND COALESCE(is_banned, FALSE) = FALSE
                      AND COALESCE(banned, FALSE) = FALSE
                    RETURNING usd_balance
                """, (db_usdt_amount, user_id_clean, user_id_clean, user_id_clean))
                bal_row = cur.fetchone()
                if not bal_row:
                    raise ValueError("تعذر العثور على حساب المستخدم أو الحساب محظور")

                new_balance_val = float(bal_row.get("usd_balance") or 0.0)

        if sender_wallet:
            save_user_bound_wallet(user_id_clean, sender_wallet)

        return new_balance_val

    except ValueError as ve:
        raise ve
    except Exception as e:
        print(f"⚠️ خطأ أثناء معالجة الشحن في Supabase: {e}")
        raise Exception(f"حدث خطأ أثناء معالجة المعاملة: {str(e)}")


def credit_user_balance(user_id, usdt_amount: float) -> float:
    """دالة مخصصة للشحن الإداري المباشر فقط عبر atomic_update_balance"""
    clean_id = _sanitize_id(user_id)
    if not clean_id or float(usdt_amount or 0.0) <= 0:
        return 0.0
    ok, new_bal = atomic_update_balance(clean_id, float(usdt_amount), is_usd=True)
    return float(new_bal) if ok else 0.0


init_deposit_tables()
