# -*- coding: utf-8 -*-
import os
import sys
import uuid
import time
import json
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

# كاش داخلي لهيكل الجداول والأعمدة لمنع الاستعلام المتكرر من information_schema
_TABLES_INITIALIZED = False
_TABLE_COLUMNS_CACHE = {}
_USER_HISTORY_CACHE = {}
_CACHE_TTL_SECONDS = 3.0


def _safe_exec(cur, sql, params=None):
    """تنفيذ أمر SQL داخل SAVEPOINT مستقل لمنع إيقاف المعاملة عند وجود تعارض"""
    sp_name = f"sp_{uuid.uuid4().hex[:8]}"
    try:
        cur.execute(f"SAVEPOINT {sp_name}")
        if params is not None:
            cur.execute(sql, params)
        else:
            cur.execute(sql)
        cur.execute(f"RELEASE SAVEPOINT {sp_name}")
        return True
    except Exception:
        try:
            cur.execute(f"ROLLBACK TO SAVEPOINT {sp_name}")
        except Exception:
            pass
        return False


def _load_schema_cache(cur):
    """جلب كافة أعمدة جداول السجلات الأربعة في استعلام واحد فقط وحفظها في الذاكرة"""
    global _TABLE_COLUMNS_CACHE
    cur.execute("""
        SELECT table_name, column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name IN ('processed_txs', 'deposit_invoices', 'withdraw_requests', 'transactions')
    """)
    schema = {}
    col_types = {}
    for t_name, c_name, d_type in cur.fetchall():
        schema.setdefault(t_name, set()).add(c_name)
        col_types[(t_name, c_name)] = d_type
    _TABLE_COLUMNS_CACHE = schema
    return schema, col_types


def init_history_tables():
    """
    تهيئة ذكية وسريعة لجداول السجلات وفهارس البحث (Indexes) مرة واحدة فقط
    دون إرسال أوامر ALTER TABLE متكررة إذا كانت الجداول جاهزة.
    """
    global _TABLES_INITIALIZED
    if _TABLES_INITIALIZED and _TABLE_COLUMNS_CACHE:
        return True

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                _safe_exec(cur, "SET LOCAL lock_timeout = '3000';")
                _safe_exec(cur, "SET LOCAL statement_timeout = '8000';")

                schema, col_types = _load_schema_cache(cur)
                needs_reload = False

                # إنشاء أي جدول غير موجود فقط
                if 'processed_txs' not in schema:
                    _safe_exec(cur, """
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
                    needs_reload = True

                if 'deposit_invoices' not in schema:
                    _safe_exec(cur, """
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
                            details TEXT,
                            failure_reason TEXT,
                            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                        );
                    """)
                    needs_reload = True

                if 'withdraw_requests' not in schema:
                    _safe_exec(cur, """
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
                    needs_reload = True

                if 'transactions' not in schema:
                    _safe_exec(cur, """
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
                    needs_reload = True

                # تحويل عمود details فقط إذا كان نوعه لا يزال json أو jsonb
                for tbl in ['processed_txs', 'deposit_invoices', 'withdraw_requests', 'transactions']:
                    dtype = col_types.get((tbl, 'details'), '')
                    if 'json' in str(dtype).lower():
                        _safe_exec(cur, f"ALTER TABLE {tbl} ALTER COLUMN details TYPE TEXT USING details::TEXT;")
                        needs_reload = True

                # إنشاء فهارس سريعة (Indexes) على user_id لتسريع الاستعلامات
                index_queries = [
                    "CREATE INDEX IF NOT EXISTS idx_processed_txs_user_id ON processed_txs (user_id);",
                    "CREATE INDEX IF NOT EXISTS idx_deposit_invoices_user_id ON deposit_invoices (user_id);",
                    "CREATE INDEX IF NOT EXISTS idx_withdraw_requests_user_id ON withdraw_requests (user_id);",
                    "CREATE INDEX IF NOT EXISTS idx_transactions_user_id ON transactions (user_id);"
                ]
                for idx_sql in index_queries:
                    _safe_exec(cur, idx_sql)

                if needs_reload:
                    _load_schema_cache(cur)

            conn.commit()
        _TABLES_INITIALIZED = True
        return True
    except Exception as e:
        logger.error(f"⚠️ [history_db] خطأ أثناء تهيئة جداول Supabase: {e}")
        return False


def _clean_details_value(val, fallback: str) -> str:
    """استخراج نص واضح من عمود details سواء كان مخزناً كنص أو JSON"""
    if not val:
        return fallback
    if isinstance(val, dict):
        return str(val.get('text') or val.get('details') or val.get('memo') or fallback)
    if isinstance(val, str):
        s = val.strip()
        if not s or s == '{}' or s == 'null':
            return fallback
        if s.startswith('{') and s.endswith('}'):
            try:
                parsed = json.loads(s)
                if isinstance(parsed, dict):
                    return str(parsed.get('text') or parsed.get('details') or parsed.get('memo') or fallback)
            except Exception:
                pass
        return s
    return fallback


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


def _fetch_table_rows_fast(cur, table_name: str, clean_id: str, limit: int = 80):
    """
    جلب صفوف المستخدم بسرعة فائقة بالاعتماد على الكاش الداخلي للأعمدة
    واستبعاد الأعمدة الضخمة غير اللازمة مثل boc.
    """
    cols = _TABLE_COLUMNS_CACHE.get(table_name)
    if not cols:
        return []

    id_columns = [c for c in ['user_id', 'tg_id', 'telegram_id'] if c in cols]
    if not id_columns:
        return []

    # استبعاد عمود boc الثقيل لتسريع نقل البيانات من Supabase
    select_cols = [c for c in cols if c != 'boc']
    select_clause = ", ".join(select_cols) if select_cols else "*"

    where_clauses = [f"{col}::text = %s" for col in id_columns]
    params = [clean_id] * len(id_columns)

    if 'created_at' in cols:
        order_col = 'created_at'
    elif 'processed_at' in cols:
        order_col = 'processed_at'
    elif 'id' in cols:
        order_col = 'id'
    else:
        order_col = select_cols[0]

    query = f"""
        SELECT {select_clause}
        FROM {table_name}
        WHERE {" OR ".join(where_clauses)}
        ORDER BY {order_col} DESC NULLS LAST
        LIMIT {int(limit)}
    """

    sp_name = f"sp_q_{table_name}"
    try:
        cur.execute(f"SAVEPOINT {sp_name}")
        cur.execute(query, tuple(params))
        col_names = [desc[0] for desc in cur.description]
        rows = [dict(zip(col_names, row)) for row in cur.fetchall()]
        cur.execute(f"RELEASE SAVEPOINT {sp_name}")
        return rows
    except Exception as e:
        try:
            cur.execute(f"ROLLBACK TO SAVEPOINT {sp_name}")
        except Exception:
            pass
        logger.error(f"⚠️ [history_db] خطأ قراءة جدول {table_name}: {e}")
        return []


def invalidate_user_history_cache(user_id=None):
    """مسح الكاش اللحظي عند إضافة معاملة جديدة"""
    global _USER_HISTORY_CACHE
    if user_id is None:
        _USER_HISTORY_CACHE.clear()
    else:
        clean_id = _sanitize_id(user_id)
        _USER_HISTORY_CACHE.pop(clean_id, None)


def get_user_transaction_history(user_id, force_refresh: bool = False):
    """جلب كافة سجلات الإيداع والسحب الخاصة بالمستخدم من Supabase بسرعة فائقة"""
    clean_id = _sanitize_id(user_id)
    if not clean_id:
        return []

    now = time.time()
    if not force_refresh and clean_id in _USER_HISTORY_CACHE:
        cached_time, cached_data = _USER_HISTORY_CACHE[clean_id]
        if now - cached_time < _CACHE_TTL_SECONDS:
            return cached_data

    init_history_tables()

    transactions = []
    seen_keys = set()

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # تحديد مهلة قصوى للاستعلام حتى لا يعلق الاتصال أبداً
                _safe_exec(cur, "SET LOCAL statement_timeout = '6000';")

                if not _TABLE_COLUMNS_CACHE:
                    _load_schema_cache(cur)

                # 1. جلب الإيداعات المؤكدة من جدول processed_txs
                rows = _fetch_table_rows_fast(cur, 'processed_txs', clean_id)
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

                    fallback_details = f"إيداع عبر شبكة TON (الفاتورة: {memo})" if memo else "إيداع تلقائي عبر شبكة TON"
                    details_text = _clean_details_value(d.get('details'), fallback_details)

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

                # 2. جلب فواتير وطلبات الإيداع من جدول deposit_invoices
                rows = _fetch_table_rows_fast(cur, 'deposit_invoices', clean_id)
                for d in rows:
                    memo = d.get('memo')
                    tx_hash = d.get('tx_hash')
                    inv_id = d.get('invoice_id') or d.get('id')

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

                    fallback_details = f"طلب إيداع - كود الفاتورة: {memo}" if memo else "طلب إيداع عبر شبكة TON"
                    details_text = _clean_details_value(d.get('details'), fallback_details)

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

                # 3. جلب طلبات السحب من جدول withdraw_requests
                rows = _fetch_table_rows_fast(cur, 'withdraw_requests', clean_id)
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

                    fallback_details = f"سحب إلى المحفظة: {wallet_addr}"
                    details_text = _clean_details_value(d.get('details'), fallback_details)

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

                # 4. جلب أي سجلات إضافية من جدول المعاملات العام transactions
                rows = _fetch_table_rows_fast(cur, 'transactions', clean_id)
                for d in rows:
                    raw_id = d.get('tx_id') or d.get('tx_hash') or f"TX-{d.get('id')}"
                    tx_id = str(raw_id)
                    memo = d.get('memo')
                    if (
                        f"dep_{tx_id}" in seen_keys
                        or f"wd_{tx_id}" in seen_keys
                        or f"tx_{tx_id}" in seen_keys
                        or (memo and f"memo_{memo}" in seen_keys)
                    ):
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

                    fallback_details = f"سحب إلى المحفظة: {wallet_addr or 'محفظة TON'}" if tx_type == 'withdraw' else f"إيداع {currency} عبر شبكة TON"
                    details_text = _clean_details_value(d.get('details'), fallback_details)

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
        logger.error(f"❌ [history_db] خطأ في الاتصال بقاعدة بيانات Supabase: {e}")

    transactions.sort(key=lambda x: x.get('timestamp', 0), reverse=True)
    _USER_HISTORY_CACHE[clean_id] = (time.time(), transactions)
    return transactions


def record_transaction(user_id, tx_type: str, amount: float, currency: str = 'USDT',
                       status: str = 'pending', tx_id: str = None, wallet_address: str = None,
                       memo: str = None, details: str = None, failure_reason: str = None) -> bool:
    """تسجيل أي عملية إيداع أو سحب مباشرة في Supabase ومسح الكاش اللحظي"""
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
        invalidate_user_history_cache(clean_id)
        return True
    except Exception as e:
        logger.error(f"⚠️ [history_db] فشل في تسجيل المعاملة في Supabase: {e}")
        return False
