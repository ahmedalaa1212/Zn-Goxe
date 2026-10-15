# -*- coding: utf-8 -*-
import os
import sys
import time
import logging
from datetime import datetime, timezone

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "../../"))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

logger = logging.getLogger('history_db')

try:
    from database import get_db_connection, _sanitize_id
except ImportError as e:
    logger.error(f"⚠️ خطأ في استيراد database.py داخل history_db: {e}")
    def _sanitize_id(val):
        if val is None:
            return None
        s = str(val).strip()
        return s[:-2] if s.endswith('.0') else s

_TABLES_INITIALIZED = False

def init_history_tables():
    """
    إنشاء وتحديث جداول السجلات (الإيداع والسحب) تلقائياً في Supabase
    لضمان عدم حدوث أي خطأ في حال عدم وجود جدول أو عمود.
    """
    global _TABLES_INITIALIZED
    if _TABLES_INITIALIZED:
        return True

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # 1. جدول عمليات الإيداع المعالجة (processed_txs)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS processed_txs (
                        id SERIAL PRIMARY KEY,
                        user_id TEXT,
                        tx_hash TEXT UNIQUE,
                        usdt_amount NUMERIC(18, 4) DEFAULT 0.0,
                        amount NUMERIC(18, 4) DEFAULT 0.0,
                        currency TEXT DEFAULT 'USDT',
                        memo TEXT,
                        status TEXT DEFAULT 'completed',
                        details TEXT,
                        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                        processed_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                    );
                """)

                # 2. جدول فواتير الإيداع (deposit_invoices)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS deposit_invoices (
                        id SERIAL PRIMARY KEY,
                        invoice_id TEXT,
                        user_id TEXT,
                        usdt_amount NUMERIC(18, 4) DEFAULT 0.0,
                        amount NUMERIC(18, 4) DEFAULT 0.0,
                        currency TEXT DEFAULT 'USDT',
                        memo TEXT,
                        tx_hash TEXT,
                        status TEXT DEFAULT 'pending',
                        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                    );
                """)

                # 3. جدول طلبات السحب (withdraw_requests)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS withdraw_requests (
                        id SERIAL PRIMARY KEY,
                        user_id TEXT NOT NULL,
                        amount NUMERIC(18, 4) NOT NULL DEFAULT 0.0,
                        fee NUMERIC(18, 4) DEFAULT 0.0,
                        net_amount NUMERIC(18, 4) DEFAULT 0.0,
                        currency TEXT DEFAULT 'USDT',
                        wallet_address TEXT,
                        network TEXT DEFAULT 'TON',
                        status TEXT DEFAULT 'pending',
                        tx_hash TEXT,
                        failure_reason TEXT,
                        admin_note TEXT,
                        details TEXT,
                        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                        processed_at TIMESTAMPTZ
                    );
                """)

                # 4. جدول السجل العام الموحد للمعاملات (transactions)
                cur.execute("""
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
                    );
                """)

                # التأكد من وجود الأعمدة الضرورية في الجداول الموجودة مسبقاً في Supabase
                alter_statements = [
                    "ALTER TABLE processed_txs ADD COLUMN IF NOT EXISTS user_id TEXT;",
                    "ALTER TABLE processed_txs ADD COLUMN IF NOT EXISTS tx_hash TEXT;",
                    "ALTER TABLE processed_txs ADD COLUMN IF NOT EXISTS usdt_amount NUMERIC(18, 4) DEFAULT 0.0;",
                    "ALTER TABLE processed_txs ADD COLUMN IF NOT EXISTS currency TEXT DEFAULT 'USDT';",
                    "ALTER TABLE processed_txs ADD COLUMN IF NOT EXISTS memo TEXT;",
                    "ALTER TABLE processed_txs ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'completed';",
                    "ALTER TABLE processed_txs ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP;",
                    "ALTER TABLE deposit_invoices ADD COLUMN IF NOT EXISTS user_id TEXT;",
                    "ALTER TABLE deposit_invoices ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'pending';",
                    "ALTER TABLE deposit_invoices ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP;",
                    "ALTER TABLE withdraw_requests ADD COLUMN IF NOT EXISTS user_id TEXT;",
                    "ALTER TABLE withdraw_requests ADD COLUMN IF NOT EXISTS wallet_address TEXT;",
                    "ALTER TABLE withdraw_requests ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'pending';",
                    "ALTER TABLE withdraw_requests ADD COLUMN IF NOT EXISTS failure_reason TEXT;",
                    "ALTER TABLE withdraw_requests ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP;"
                ]
                for stmt in alter_statements:
                    try:
                        cur.execute(stmt)
                    except Exception:
                        pass

            conn.commit()
        _TABLES_INITIALIZED = True
        return True
    except Exception as e:
        logger.error(f"⚠️ [history_db] خطأ أثناء تهيئة جداول Supabase: {e}")
        return False


def parse_timestamp(val) -> float:
    """تحويل أي صيغة تاريخ من Supabase إلى Timestamp دقيق بالثواني"""
    if val is None:
        return time.time()
    if isinstance(val, datetime):
        if val.tzinfo is None:
            val = val.replace(tzinfo=timezone.utc)
        return float(val.timestamp())
    if hasattr(val, 'timestamp'):
        try:
            return float(val.timestamp())
        except Exception:
            pass
    if isinstance(val, (int, float)):
        val_f = float(val)
        return val_f / 1000.0 if val_f > 1e11 else val_f
    if isinstance(val, str):
        val_str = val.strip()
        try:
            val_f = float(val_str)
            return val_f / 1000.0 if val_f > 1e11 else val_f
        except ValueError:
            pass
        try:
            dt = datetime.fromisoformat(val_str.replace('Z', '+00:00'))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return float(dt.timestamp())
        except Exception:
            pass
    return time.time()


def format_exact_datetime(ts: float) -> str:
    """إرجاع التاريخ والوقت بالسنة والشهر واليوم والساعة والدقيقة والثانية"""
    try:
        dt = datetime.fromtimestamp(ts)
        period = "م" if dt.hour >= 12 else "ص"
        hour_12 = dt.hour % 12
        if hour_12 == 0:
            hour_12 = 12
        return f"{dt.strftime('%Y-%m-%d')} | {hour_12:02d}:{dt.minute:02d}:{dt.second:02d} {period}"
    except Exception:
        return "غير محدد"


def normalize_status(raw_status, default_status='pending'):
    """توحيد حالة المعاملة وترجمتها بدقة (قيد المراجعة / تم التنفيذ / مرفوض)"""
    st = str(raw_status or default_status).lower().strip()
    if st in ['completed', 'success', 'succeeded', 'paid', 'approved', 'confirmed', 'done']:
        return 'completed', 'تم التنفيذ'
    elif st in ['failed', 'rejected', 'canceled', 'cancelled', 'expired', 'error', 'declined']:
        return 'failed', 'مرفوض / فاشل'
    else:
        return 'pending', 'قيد المراجعة'


def _fetch_table_rows_for_user(cur, table_name: str, clean_id: str, limit: int = 100):
    """
    جلب صفوف المستخدم من أي جدول في Supabase بأمان تام مهما كان اسم عمود المعرف
    (user_id أو tg_id أو telegram_id) ومهما كان نوع العمود (BIGINT أو TEXT).
    """
    cur.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_schema = 'public' AND table_name = %s
    """, (table_name,))
    cols = [r[0] for r in cur.fetchall()]
    if not cols:
        return []

    id_columns = [c for c in ['user_id', 'tg_id', 'telegram_id'] if c in cols]
    if not id_columns:
        return []

    where_clauses = [f"CAST({col} AS TEXT) = %s" for col in id_columns]
    params = [clean_id] * len(id_columns)

    order_col = 'created_at' if 'created_at' in cols else ('processed_at' if 'processed_at' in cols else ('id' if 'id' in cols else cols[0]))

    query = f"""
        SELECT * FROM {table_name}
        WHERE {" OR ".join(where_clauses)}
        ORDER BY {order_col} DESC
        LIMIT {int(limit)}
    """
    cur.execute(query, tuple(params))
    col_names = [desc[0] for desc in cur.description]
    return [dict(zip(col_names, row)) for row in cur.fetchall()]


def get_user_transaction_history(user_id):
    """
    جلب كافة سجلات الإيداع والسحب الخاصة بالمستخدم من Supabase
    مع الترتيب الزمني الدقيق بالدقيقة والثانية.
    """
    init_history_tables()

    transactions = []
    seen_keys = set()

    clean_id = _sanitize_id(user_id)
    if not clean_id:
        return transactions

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:

                # 1. جلب الإيداعات المؤكدة من جدول processed_txs
                try:
                    rows = _fetch_table_rows_for_user(cur, 'processed_txs', clean_id)
                    for d in rows:
                        raw_hash = d.get('tx_hash') or d.get('memo') or d.get('id')
                        tx_id = str(raw_hash or f"DEP-{d.get('id')}")
                        dedup_key = f"dep_{tx_id}"
                        if dedup_key in seen_keys:
                            continue
                        seen_keys.add(dedup_key)
                        if d.get('memo'):
                            seen_keys.add(f"memo_{d.get('memo')}")

                        status_code, status_ar = normalize_status(d.get('status'), default_status='completed')
                        ts = parse_timestamp(d.get('processed_at') or d.get('created_at') or d.get('timestamp'))
                        amount = float(d.get('usdt_amount') or d.get('amount') or 0.0)
                        currency = str(d.get('currency') or 'USDT').upper()
                        memo = d.get('memo')

                        details_text = d.get('details') or (f"إيداع عبر شبكة TON (Memo: {memo})" if memo else "إيداع تلقائي عبر شبكة TON")

                        transactions.append({
                            'id': tx_id,
                            'type': 'deposit',
                            'type_ar': 'إيداع',
                            'amount': amount,
                            'currency': currency,
                            'status': status_code,
                            'status_ar': status_ar,
                            'failure_reason': d.get('failure_reason') or d.get('error') or None,
                            'timestamp': ts,
                            'formatted_date': format_exact_datetime(ts),
                            'wallet_address': d.get('sender_address') or d.get('wallet_address') or None,
                            'details': details_text
                        })
                except Exception as e:
                    logger.error(f"⚠️ [history_db] خطأ في استعلام processed_txs: {e}")

                # 2. جلب فواتير وطلبات الإيداع من جدول deposit_invoices
                try:
                    rows = _fetch_table_rows_for_user(cur, 'deposit_invoices', clean_id)
                    for d in rows:
                        memo = d.get('memo')
                        tx_hash = d.get('tx_hash')
                        inv_id = d.get('invoice_id') or d.get('id')

                        # منع التكرار إذا كانت الفاتورة مسجلة بالفعل في processed_txs
                        if (tx_hash and f"dep_{tx_hash}" in seen_keys) or (memo and f"memo_{memo}" in seen_keys):
                            continue

                        tx_id = str(tx_hash or inv_id or memo or f"INV-{d.get('id')}")
                        dedup_key = f"inv_{tx_id}"
                        if dedup_key in seen_keys:
                            continue
                        seen_keys.add(dedup_key)

                        status_code, status_ar = normalize_status(d.get('status'), default_status='pending')
                        ts = parse_timestamp(d.get('updated_at') or d.get('created_at'))
                        amount = float(d.get('usdt_amount') or d.get('amount') or 0.0)
                        currency = str(d.get('currency') or 'USDT').upper()

                        details_text = d.get('details') or (f"طلب إيداع - كود الفاتورة: {memo}" if memo else "طلب إيداع عبر شبكة TON")

                        transactions.append({
                            'id': tx_id,
                            'type': 'deposit',
                            'type_ar': 'إيداع',
                            'amount': amount,
                            'currency': currency,
                            'status': status_code,
                            'status_ar': status_ar,
                            'failure_reason': d.get('failure_reason') or None,
                            'timestamp': ts,
                            'formatted_date': format_exact_datetime(ts),
                            'wallet_address': d.get('wallet_address') or None,
                            'details': details_text
                        })
                except Exception as e:
                    logger.error(f"⚠️ [history_db] خطأ في استعلام deposit_invoices: {e}")

                # 3. جلب طلبات السحب من جدول withdraw_requests
                try:
                    rows = _fetch_table_rows_for_user(cur, 'withdraw_requests', clean_id)
                    for d in rows:
                        raw_id = d.get('tx_hash') or d.get('request_id') or f"WD-{d.get('id')}"
                        tx_id = str(raw_id)
                        dedup_key = f"wd_{tx_id}"
                        if dedup_key in seen_keys:
                            continue
                        seen_keys.add(dedup_key)

                        status_code, status_ar = normalize_status(d.get('status'), default_status='pending')
                        ts = parse_timestamp(d.get('processed_at') or d.get('updated_at') or d.get('created_at'))
                        amount = float(d.get('amount') or d.get('usdt_amount') or 0.0)
                        currency = str(d.get('currency') or 'USDT').upper()
                        wallet_addr = d.get('wallet_address') or d.get('address') or 'محفظة TON'

                        details_text = d.get('details') or f"سحب إلى المحفظة: {wallet_addr}"

                        transactions.append({
                            'id': tx_id,
                            'type': 'withdraw',
                            'type_ar': 'سحب',
                            'amount': amount,
                            'currency': currency,
                            'status': status_code,
                            'status_ar': status_ar,
                            'failure_reason': d.get('failure_reason') or d.get('reject_reason') or d.get('admin_note') or None,
                            'timestamp': ts,
                            'formatted_date': format_exact_datetime(ts),
                            'wallet_address': wallet_addr,
                            'details': details_text
                        })
                except Exception as e:
                    logger.error(f"⚠️ [history_db] خطأ في استعلام withdraw_requests: {e}")

                # 4. جلب أي سجلات إضافية من جدول المعاملات العام transactions
                try:
                    rows = _fetch_table_rows_for_user(cur, 'transactions', clean_id)
                    for d in rows:
                        raw_id = d.get('tx_id') or d.get('tx_hash') or f"TX-{d.get('id')}"
                        tx_id = str(raw_id)
                        if f"dep_{tx_id}" in seen_keys or f"wd_{tx_id}" in seen_keys or f"tx_{tx_id}" in seen_keys:
                            continue
                        seen_keys.add(f"tx_{tx_id}")

                        raw_type = str(d.get('type') or 'deposit').lower().strip()
                        tx_type = 'withdraw' if 'withdraw' in raw_type else 'deposit'
                        default_st = 'completed' if tx_type == 'deposit' else 'pending'
                        status_code, status_ar = normalize_status(d.get('status'), default_status=default_st)
                        ts = parse_timestamp(d.get('updated_at') or d.get('created_at'))
                        amount = float(d.get('amount') or d.get('usdt_amount') or 0.0)
                        currency = str(d.get('currency') or 'USDT').upper()
                        wallet_addr = d.get('wallet_address')

                        if d.get('details'):
                            details_text = d.get('details')
                        elif tx_type == 'withdraw':
                            details_text = f"سحب إلى المحفظة: {wallet_addr or 'محفظة TON'}"
                        else:
                            details_text = f"إيداع {currency} عبر شبكة TON"

                        transactions.append({
                            'id': tx_id,
                            'type': tx_type,
                            'type_ar': 'سحب' if tx_type == 'withdraw' else 'إيداع',
                            'amount': amount,
                            'currency': currency,
                            'status': status_code,
                            'status_ar': status_ar,
                            'failure_reason': d.get('failure_reason') or None,
                            'timestamp': ts,
                            'formatted_date': format_exact_datetime(ts),
                            'wallet_address': wallet_addr,
                            'details': details_text
                        })
                except Exception as e:
                    logger.error(f"⚠️ [history_db] خطأ في استعلام transactions: {e}")

    except Exception as e:
        logger.error(f"❌ [history_db] خطأ في الاتصال بقاعدة بيانات Supabase: {e}")

    # ترتيب جميع السجلات من الأحدث إلى الأقدم بدقة الثانية
    transactions.sort(key=lambda x: x.get('timestamp', 0), reverse=True)
    return transactions


def record_transaction(user_id, tx_type: str, amount: float, currency: str = 'USDT',
                       status: str = 'pending', tx_id: str = None, wallet_address: str = None,
                       memo: str = None, details: str = None, failure_reason: str = None) -> bool:
    """
    دالة مساعدة لتسجيل أي عملية إيداع أو سحب مباشرة في Supabase
    يمكن استدعاؤها من قسم الإيداع أو السحب في أي وقت.
    """
    init_history_tables()
    clean_id = _sanitize_id(user_id)
    if not clean_id:
        return False

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO transactions 
                    (tx_id, user_id, type, amount, currency, status, wallet_address, memo, details, failure_reason, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """, (
                    tx_id, clean_id, tx_type, float(amount), currency,
                    status, wallet_address, memo, details, failure_reason
                ))
            conn.commit()
        return True
    except Exception as e:
        logger.error(f"⚠️ [history_db] فشل في تسجيل المعاملة في Supabase: {e}")
        return False
