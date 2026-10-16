# -*- coding: utf-8 -*-
import os
import sys
import uuid
import time
import json
import hashlib

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "../../"))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

try:
    from database import get_db_connection, _sanitize_id, atomic_update_balance, get_user_balances
except ImportError as e:
    print(f"⚠️ خطأ في الاستيراد من database.py: {e}")
    def _sanitize_id(val):
        if val is None:
            return None
        s = str(val).strip()
        return s[:-2] if s.endswith('.0') else s

SEED_PACKAGES = [
    {'id': 1, 'usdt_amount': 0.5, 'name_ar': 'باقة $0.5 USDT', 'is_active': True, 'sort_order': 1},
    {'id': 2, 'usdt_amount': 1.5, 'name_ar': 'باقة $1.5 USDT', 'is_active': True, 'sort_order': 2},
    {'id': 3, 'usdt_amount': 5.0, 'name_ar': 'باقة $5 USDT', 'is_active': True, 'sort_order': 3},
    {'id': 4, 'usdt_amount': 10.0, 'name_ar': 'باقة $10 USDT', 'is_active': True, 'sort_order': 4},
    {'id': 5, 'usdt_amount': 15.0, 'name_ar': 'باقة $15 USDT', 'is_active': True, 'sort_order': 5}
]

_tables_initialized = False


def get_official_ton_wallet():
    """جلب عنوان محفظة TON للاستلام من متغيرات البيئة فقط"""
    env_wallet = (
        os.getenv('TON_WALLET_ADDRESS')
        or os.getenv('OFFICIAL_TON_WALLET')
        or os.getenv('TON_WALLET')
        or os.getenv('PROJECT_WALLET')
        or ''
    )
    return str(env_wallet).strip()


def _exec_safe(conn, cur, sql, params=None):
    """تنفيذ أمر SQL بأمان تام بدون SAVEPOINT مع دعم autocommit أو rollback"""
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

                # إضافة الأعمدة الناقصة إن وجدت
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

                # إدخال الباقات الافتراضية فقط إذا كان الجدول فارغاً
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
                    usdt_val = float(row[1])
                    custom_name = row[4] if len(row) > 4 and row[4] else f"باقة ${usdt_val:g} USDT"
                    packages.append({
                        'id': pkg_id,
                        'usdt_amount': usdt_val,
                        'name_ar': custom_name,
                        'is_active': bool(row[2]),
                        'sort_order': int(row[3])
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


def create_deposit_invoice(user_id, usdt_amount: float, ton_amount: float, sender_wallet: str = None) -> dict:
    """إنشاء فاتورة إيداع مبدئية في Supabase بحالة قيد المراجعة (pending)"""
    init_deposit_tables()
    user_id_clean = _sanitize_id(user_id) or "0"
    memo = f"DEP-{user_id_clean}-{uuid.uuid4().hex[:6].upper()}"
    details_text = f"إيداع باقة ${usdt_amount:g} USDT (~{ton_amount:.4f} TON) عبر شبكة TON"
    # صيغة JSON صالحة تعمل سواء كان العمود JSONB أو TEXT
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
        return {
            'memo': memo,
            'invoice_id': 0,
            'user_id': user_id_clean,
            'usdt_amount': usdt_amount,
            'ton_amount': ton_amount
        }


def update_deposit_invoice_status(memo: str, status: str = 'cancelled', failure_reason: str = None, delete_if_cancelled: bool = True) -> bool:
    """تحديث حالة الفاتورة عند الإلغاء أو الفشل"""
    if not memo:
        return False
    init_deposit_tables()
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                if status in ['cancelled', 'canceled'] and delete_if_cancelled:
                    _exec_safe(conn, cur, "DELETE FROM deposit_invoices WHERE memo = %s AND status = 'pending'", (memo,))
                else:
                    _exec_safe(conn, cur, """
                        UPDATE deposit_invoices 
                        SET status = %s,
                            failure_reason = COALESCE(%s, failure_reason),
                            updated_at = CURRENT_TIMESTAMP
                        WHERE memo = %s AND status != 'completed'
                    """, (status, failure_reason, memo))
        return True
    except Exception as e:
        print(f"⚠️ خطأ تحديث حالة الفاتورة: {e}")
        return False


def verify_and_process_ton_boc(user_id, usdt_amount: float, memo: str, boc: str, ton_amount: float = 0.0, sender_wallet: str = None) -> float:
    """معالجة معاملة الإيداع وتوثيقها في جداول السجلات وتحديث الرصيد ذرياً في Supabase"""
    init_deposit_tables()
    user_id_clean = _sanitize_id(user_id)
    if not user_id_clean or usdt_amount <= 0:
        raise ValueError("بيانات المستخدم أو قيمة الباقة غير صحيحة")

    tx_identifier = boc or memo or str(uuid.uuid4())
    tx_hash = hashlib.sha256(tx_identifier.encode('utf-8')).hexdigest()

    details_text = f"إيداع ناجح بقيمة ${usdt_amount:g} USDT"
    if ton_amount and float(ton_amount) > 0:
        details_text += f" ({float(ton_amount):.4f} TON)"
    if memo:
        details_text += f" | الفاتورة: {memo}"

    # صيغة JSON متوافقة 100% مع كل من أعمدة JSON/JSONB وأعمدة TEXT
    details_payload = json.dumps({"text": details_text, "memo": memo, "usdt": usdt_amount}, ensure_ascii=False)

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # 1. التأكد من عدم تكرار المعاملة
                cur.execute("SELECT tx_hash FROM processed_txs WHERE tx_hash = %s", (tx_hash,))
                if cur.fetchone():
                    raise ValueError("هذه المعاملة تم استخدامها وشحنها سابقاً!")

                if memo:
                    cur.execute("SELECT tx_hash FROM processed_txs WHERE memo = %s AND status = 'completed'", (memo,))
                    if cur.fetchone():
                        raise ValueError("تم تأكيد وشحن هذه الفاتورة مسبقاً!")

                # 2. تسجيل الإيداع المكتمل في جدول processed_txs
                inserted = _exec_safe(conn, cur, """
                    INSERT INTO processed_txs 
                    (tx_hash, user_id, usdt_amount, amount, ton_amount, currency, memo, boc, wallet_address, type, status, details, created_at, processed_at)
                    VALUES (%s, %s, %s, %s, %s, 'USDT', %s, %s, %s, 'deposit', 'completed', %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """, (tx_hash, user_id_clean, usdt_amount, usdt_amount, float(ton_amount or 0.0), memo, boc, sender_wallet, details_payload))

                if not inserted:
                    inserted = _exec_safe(conn, cur, """
                        INSERT INTO processed_txs 
                        (tx_hash, user_id, usdt_amount, memo, boc, type, status, details)
                        VALUES (%s, %s, %s, %s, %s, 'deposit', 'completed', %s)
                    """, (tx_hash, user_id_clean, usdt_amount, memo, boc, details_payload))

                if not inserted:
                    _exec_safe(conn, cur, """
                        INSERT INTO processed_txs 
                        (tx_hash, user_id, usdt_amount, memo, boc, type, status)
                        VALUES (%s, %s, %s, %s, %s, 'deposit', 'completed')
                    """, (tx_hash, user_id_clean, usdt_amount, memo, boc))

                # 3. تحديث الفاتورة في deposit_invoices لتصبح مكتملة (completed)
                if memo:
                    updated_inv = _exec_safe(conn, cur, """
                        UPDATE deposit_invoices 
                        SET status = 'completed',
                            tx_hash = %s,
                            wallet_address = COALESCE(%s, wallet_address),
                            details = %s,
                            failure_reason = NULL,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE memo = %s
                    """, (tx_hash, sender_wallet, details_payload, memo))
                    if not updated_inv:
                        _exec_safe(conn, cur, "UPDATE deposit_invoices SET status = 'completed', failure_reason = NULL WHERE memo = %s", (memo,))

                # 4. تسجيل العملية في جدول السجلات الموحد (transactions)
                _exec_safe(conn, cur, """
                    INSERT INTO transactions
                    (tx_id, user_id, type, amount, currency, status, wallet_address, memo, details, created_at, updated_at)
                    VALUES (%s, %s, 'deposit', %s, 'USDT', 'completed', %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """, (tx_hash, user_id_clean, usdt_amount, sender_wallet, memo, details_payload))

        # 5. تحديث رصيد المستخدم ذرياً وإرجاع الرصيد الجديد
        new_balance_val = None
        try:
            from wallet.wallet_db import update_user_balance, get_user_wallet_balances
            success = update_user_balance(user_id_clean, usdt_amount, currency='usd_balance', operation='add')
            if success:
                balances = get_user_wallet_balances(user_id_clean)
                new_balance_val = float(balances.get('usdt_balance', 0.0))
        except Exception as e:
            print(f"⚠️ Notice in wallet_db balance update: {e}")

        if new_balance_val is None:
            try:
                ok, new_bal = atomic_update_balance(user_id_clean, usdt_amount, is_usd=True)
                if ok:
                    new_balance_val = float(new_bal)
            except Exception as e:
                print(f"⚠️ Notice in atomic_update_balance: {e}")

        if new_balance_val is None:
            with get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE users 
                        SET usd_balance = COALESCE(usd_balance, 0.0) + %s
                        WHERE CAST(tg_id AS TEXT) = %s OR CAST(user_id AS TEXT) = %s
                        RETURNING usd_balance
                    """, (float(usdt_amount), user_id_clean, user_id_clean))
                    row = cur.fetchone()
                    if not getattr(conn, 'autocommit', False):
                        conn.commit()
                    if row:
                        new_balance_val = float(row[0])

        if new_balance_val is None:
            raise Exception("تعذر العثور على حساب المستخدم لتحديث الرصيد.")

        return float(new_balance_val)

    except ValueError as ve:
        raise ve
    except Exception as e:
        if memo:
            update_deposit_invoice_status(memo, status='failed', failure_reason=str(e), delete_if_cancelled=False)
        print(f"⚠️ خطأ أثناء معالجة الشحن في Supabase: {e}")
        raise Exception(f"حدث خطأ أثناء معالجة المعاملة: {str(e)}")


def credit_user_balance(user_id, usdt_amount: float) -> float:
    """دالة احتياطية للشحن اليدوي المباشر"""
    if not user_id:
        return 0.0
    return verify_and_process_ton_boc(user_id, usdt_amount, f"MANUAL-{int(time.time())}", f"BOC-MANUAL-{uuid.uuid4().hex}")


init_deposit_tables()
