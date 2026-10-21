# -*- coding: utf-8 -*-
import os
import sys
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
    get_db_connection = None

    def _sanitize_id(val):
        if val is None:
            return None
        s = str(val).strip()
        return s[:-2] if s.endswith('.0') else s

_TABLES_INITIALIZED = False
_TABLE_COLUMNS_CACHE = {}


def _exec_safe(conn, cur, sql, params=None):
    """تنفيذ استعلام SQL بأمان تام مع دعم autocommit أو المعاملات العادية بدون SAVEPOINT"""
    try:
        if params is not None:
            cur.execute(sql, params)
        else:
            cur.execute(sql)
        if not getattr(conn, 'autocommit', False):
            conn.commit()
        return True
    except Exception as e:
        try:
            if not getattr(conn, 'autocommit', False):
                conn.rollback()
        except Exception:
            pass
        logger.debug(f"[history_db] SQL Notice: {e}")
        return False


def _load_schema_cache(conn, cur):
    """جلب أسماء الأعمدة للجداول الأربعة في استعلام واحد سريع وحفظها في الذاكرة"""
    global _TABLE_COLUMNS_CACHE
    try:
        cur.execute("""
            SELECT table_name, column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name IN ('processed_txs', 'deposit_invoices', 'withdraw_requests', 'transactions')
        """)
        schema = {}
        for t_name, c_name in cur.fetchall():
            schema.setdefault(t_name, set()).add(c_name)
        if schema:
            _TABLE_COLUMNS_CACHE = schema
        return schema
    except Exception as e:
        try:
            if not getattr(conn, 'autocommit', False):
                conn.rollback()
        except Exception:
            pass
        logger.error(f"⚠️ [history_db] خطأ قراءة هيكل الجداول: {e}")
        return _TABLE_COLUMNS_CACHE


def init_history_tables():
    """تهيئة جداول السجلات ومزامنة الأعمدة مع نظام السحب والإيداع في Supabase تلقائياً"""
    global _TABLES_INITIALIZED
    if _TABLES_INITIALIZED and _TABLE_COLUMNS_CACHE:
        return True

    if not get_db_connection:
        return False

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                schema = _load_schema_cache(conn, cur)

                # 1. جدول processed_txs (يدعم الإيداع والسحب معاً)
                if 'processed_txs' not in schema:
                    _exec_safe(conn, cur, """
                        CREATE TABLE IF NOT EXISTS processed_txs (
                            id TEXT PRIMARY KEY,
                            tx_id TEXT UNIQUE,
                            tx_hash VARCHAR(256),
                            user_id VARCHAR(255),
                            coins NUMERIC(18, 4) DEFAULT 0.0,
                            usdt_amount NUMERIC(18, 4) DEFAULT 0.0,
                            amount NUMERIC(18, 4) DEFAULT 0.0,
                            fee_usd NUMERIC(18, 4) DEFAULT 0.02,
                            net_coins NUMERIC(18, 4) DEFAULT 0.0,
                            currency VARCHAR(32) DEFAULT 'ZNX',
                            tier_name TEXT DEFAULT '',
                            memo TEXT,
                            boc TEXT,
                            wallet_address TEXT,
                            type VARCHAR(64) DEFAULT 'withdraw',
                            status VARCHAR(50) DEFAULT 'pending',
                            processed_by TEXT,
                            details TEXT,
                            failure_reason TEXT,
                            processing_started_at TIMESTAMPTZ,
                            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                            processed_at TIMESTAMPTZ
                        );
                    """)
                else:
                    _exec_safe(conn, cur, """
                        ALTER TABLE processed_txs ADD COLUMN IF NOT EXISTS id TEXT;
                        ALTER TABLE processed_txs ADD COLUMN IF NOT EXISTS tx_id TEXT;
                        ALTER TABLE processed_txs ADD COLUMN IF NOT EXISTS tx_hash VARCHAR(256);
                        ALTER TABLE processed_txs ADD COLUMN IF NOT EXISTS coins NUMERIC(18, 4) DEFAULT 0.0;
                        ALTER TABLE processed_txs ADD COLUMN IF NOT EXISTS usdt_amount NUMERIC(18, 4) DEFAULT 0.0;
                        ALTER TABLE processed_txs ADD COLUMN IF NOT EXISTS amount NUMERIC(18, 4) DEFAULT 0.0;
                        ALTER TABLE processed_txs ADD COLUMN IF NOT EXISTS fee_usd NUMERIC(18, 4) DEFAULT 0.02;
                        ALTER TABLE processed_txs ADD COLUMN IF NOT EXISTS net_coins NUMERIC(18, 4) DEFAULT 0.0;
                        ALTER TABLE processed_txs ADD COLUMN IF NOT EXISTS currency VARCHAR(32) DEFAULT 'ZNX';
                        ALTER TABLE processed_txs ADD COLUMN IF NOT EXISTS tier_name TEXT DEFAULT '';
                        ALTER TABLE processed_txs ADD COLUMN IF NOT EXISTS wallet_address TEXT;
                        ALTER TABLE processed_txs ADD COLUMN IF NOT EXISTS type VARCHAR(64) DEFAULT 'withdraw';
                        ALTER TABLE processed_txs ADD COLUMN IF NOT EXISTS status VARCHAR(50) DEFAULT 'pending';
                        ALTER TABLE processed_txs ADD COLUMN IF NOT EXISTS processed_by TEXT;
                        ALTER TABLE processed_txs ADD COLUMN IF NOT EXISTS details TEXT;
                        ALTER TABLE processed_txs ADD COLUMN IF NOT EXISTS failure_reason TEXT;
                        ALTER TABLE processed_txs ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP;
                        ALTER TABLE processed_txs ADD COLUMN IF NOT EXISTS processed_at TIMESTAMPTZ;
                    """)

                # 2. جدول فواتير الإيداع deposit_invoices
                if 'deposit_invoices' not in schema:
                    _exec_safe(conn, cur, """
                        CREATE TABLE IF NOT EXISTS deposit_invoices (
                            id SERIAL PRIMARY KEY,
                            invoice_id TEXT,
                            user_id VARCHAR(255) NOT NULL,
                            usdt_amount NUMERIC(18, 4) DEFAULT 0.0,
                            amount NUMERIC(18, 4) DEFAULT 0.0,
                            ton_amount NUMERIC(18, 4) DEFAULT 0.0,
                            currency VARCHAR(32) DEFAULT 'USDT',
                            memo VARCHAR(255) UNIQUE NOT NULL,
                            tx_hash TEXT,
                            wallet_address TEXT,
                            status VARCHAR(50) DEFAULT 'pending',
                            details TEXT,
                            failure_reason TEXT,
                            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                        );
                    """)

                # 3. جدول طلبات السحب withdraw_requests
                if 'withdraw_requests' not in schema:
                    _exec_safe(conn, cur, """
                        CREATE TABLE IF NOT EXISTS withdraw_requests (
                            id SERIAL PRIMARY KEY,
                            tx_id TEXT,
                            user_id VARCHAR(255) NOT NULL,
                            coins NUMERIC(18, 4) DEFAULT 0.0,
                            amount NUMERIC(18, 4) NOT NULL DEFAULT 0.0,
                            fee NUMERIC(18, 4) DEFAULT 0.0,
                            fee_usd NUMERIC(18, 4) DEFAULT 0.02,
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
                else:
                    _exec_safe(conn, cur, """
                        ALTER TABLE withdraw_requests ADD COLUMN IF NOT EXISTS tx_id TEXT;
                        ALTER TABLE withdraw_requests ADD COLUMN IF NOT EXISTS coins NUMERIC(18, 4) DEFAULT 0.0;
                        ALTER TABLE withdraw_requests ADD COLUMN IF NOT EXISTS fee_usd NUMERIC(18, 4) DEFAULT 0.02;
                        ALTER TABLE withdraw_requests ADD COLUMN IF NOT EXISTS tier_name TEXT DEFAULT '';
                        ALTER TABLE withdraw_requests ADD COLUMN IF NOT EXISTS processed_by TEXT;
                        ALTER TABLE withdraw_requests ADD COLUMN IF NOT EXISTS details TEXT;
                        ALTER TABLE withdraw_requests ADD COLUMN IF NOT EXISTS failure_reason TEXT;
                        ALTER TABLE withdraw_requests ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP;
                        ALTER TABLE withdraw_requests ADD COLUMN IF NOT EXISTS processed_at TIMESTAMPTZ;
                    """)

                # 4. جدول المعاملات العام transactions
                if 'transactions' not in schema:
                    _exec_safe(conn, cur, """
                        CREATE TABLE IF NOT EXISTS transactions (
                            id SERIAL PRIMARY KEY,
                            tx_id TEXT,
                            user_id VARCHAR(255) NOT NULL,
                            type VARCHAR(50) NOT NULL DEFAULT 'withdraw',
                            coins NUMERIC(18, 4) DEFAULT 0.0,
                            amount NUMERIC(18, 4) NOT NULL DEFAULT 0.0,
                            fee_usd NUMERIC(18, 4) DEFAULT 0.0,
                            net_coins NUMERIC(18, 4) DEFAULT 0.0,
                            currency VARCHAR(32) DEFAULT 'ZNX',
                            tier_name TEXT DEFAULT '',
                            status VARCHAR(50) DEFAULT 'pending',
                            wallet_address TEXT,
                            memo TEXT,
                            details TEXT,
                            failure_reason TEXT,
                            processed_by TEXT,
                            processed_at TIMESTAMPTZ,
                            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                        );
                    """)
                else:
                    _exec_safe(conn, cur, """
                        ALTER TABLE transactions ADD COLUMN IF NOT EXISTS tx_id TEXT;
                        ALTER TABLE transactions ADD COLUMN IF NOT EXISTS coins NUMERIC(18, 4) DEFAULT 0.0;
                        ALTER TABLE transactions ADD COLUMN IF NOT EXISTS amount NUMERIC(18, 4) DEFAULT 0.0;
                        ALTER TABLE transactions ADD COLUMN IF NOT EXISTS fee_usd NUMERIC(18, 4) DEFAULT 0.0;
                        ALTER TABLE transactions ADD COLUMN IF NOT EXISTS net_coins NUMERIC(18, 4) DEFAULT 0.0;
                        ALTER TABLE transactions ADD COLUMN IF NOT EXISTS currency VARCHAR(32) DEFAULT 'ZNX';
                        ALTER TABLE transactions ADD COLUMN IF NOT EXISTS tier_name TEXT DEFAULT '';
                        ALTER TABLE transactions ADD COLUMN IF NOT EXISTS wallet_address TEXT;
                        ALTER TABLE transactions ADD COLUMN IF NOT EXISTS type VARCHAR(50) DEFAULT 'withdraw';
                        ALTER TABLE transactions ADD COLUMN IF NOT EXISTS status VARCHAR(50) DEFAULT 'pending';
                        ALTER TABLE transactions ADD COLUMN IF NOT EXISTS details TEXT;
                        ALTER TABLE transactions ADD COLUMN IF NOT EXISTS failure_reason TEXT;
                        ALTER TABLE transactions ADD COLUMN IF NOT EXISTS processed_by TEXT;
                        ALTER TABLE transactions ADD COLUMN IF NOT EXISTS processed_at TIMESTAMPTZ;
                        ALTER TABLE transactions ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP;
                    """)

                _load_schema_cache(conn, cur)

        _TABLES_INITIALIZED = True
        return True
    except Exception as e:
        logger.error(f"⚠️ [history_db] خطأ أثناء تهيئة الجداول: {e}")
        return False


def _clean_details_value(val, fallback: str) -> str:
    """استخراج النص العربي النظيف من عمود details سواء كان مخزناً كنص أو JSON"""
    if not val:
        return fallback
    if isinstance(val, dict):
        return str(val.get('text') or val.get('details') or val.get('memo') or fallback)
    if isinstance(val, str):
        s = val.strip()
        if not s or s in ['{}', 'null', 'None']:
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


def _fetch_table_rows_for_user(conn, cur, table_name: str, clean_id: str, limit: int = 80):
    """جلب صفوف المستخدم من الجدول مباشرة وبأمان تام"""
    cols = _TABLE_COLUMNS_CACHE.get(table_name)
    if not cols:
        schema = _load_schema_cache(conn, cur)
        cols = schema.get(table_name, set())

    if not cols:
        return []

    id_columns = [c for c in ['user_id', 'tg_id', 'telegram_id'] if c in cols]
    if not id_columns:
        return []

    where_clauses = [f"CAST({col} AS TEXT) = %s" for col in id_columns]
    params = [clean_id] * len(id_columns)

    if 'created_at' in cols:
        order_col = 'created_at'
    elif 'updated_at' in cols:
        order_col = 'updated_at'
    elif 'processed_at' in cols:
        order_col = 'processed_at'
    elif 'id' in cols:
        order_col = 'id'
    else:
        order_col = id_columns[0]

    select_cols = [f'"{c}"' for c in cols if c != 'boc']
    select_clause = ", ".join(select_cols) if select_cols else "*"

    query = f"""
        SELECT {select_clause}
        FROM {table_name}
        WHERE {" OR ".join(where_clauses)}
        ORDER BY "{order_col}" DESC
        LIMIT {int(limit)}
    """

    try:
        cur.execute(query, tuple(params))
        col_names = [desc[0] for desc in cur.description]
        return [dict(zip(col_names, row)) for row in cur.fetchall()]
    except Exception as e:
        try:
            if not getattr(conn, 'autocommit', False):
                conn.rollback()
        except Exception:
            pass
        try:
            fallback_q = f"SELECT * FROM {table_name} WHERE CAST({id_columns[0]} AS TEXT) = %s LIMIT {int(limit)}"
            cur.execute(fallback_q, (clean_id,))
            col_names = [desc[0] for desc in cur.description]
            return [dict(zip(col_names, row)) for row in cur.fetchall()]
        except Exception as e2:
            try:
                if not getattr(conn, 'autocommit', False):
                    conn.rollback()
            except Exception:
                pass
            logger.error(f"⚠️ [history_db] خطأ قراءة جدول {table_name}: {e2}")
            return []


def get_user_transaction_history(user_id, force_refresh: bool = False):
    """جلب كافة سجلات الإيداع والسحب الخاصة بالمستخدم من Supabase مع دعم كامل لسحوبات ZNX"""
    clean_id = _sanitize_id(user_id)
    if not clean_id or not get_db_connection:
        return []

    init_history_tables()

    transactions = []
    seen_tx_ids = set()

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                if force_refresh or not _TABLE_COLUMNS_CACHE:
                    _load_schema_cache(conn, cur)

                # 1. جلب المعاملات (سحب ZNX أو إيداع USDT) من جدول processed_txs
                rows = _fetch_table_rows_for_user(conn, cur, 'processed_txs', clean_id)
                for d in rows:
                    raw_id = d.get('tx_id') or d.get('tx_hash') or d.get('id') or d.get('memo')
                    if not raw_id:
                        continue
                    tx_id = str(raw_id).strip()
                    if tx_id in seen_tx_ids:
                        continue
                    seen_tx_ids.add(tx_id)
                    if d.get('memo'):
                        seen_tx_ids.add(f"memo_{d.get('memo')}")

                    raw_type = str(d.get('type') or '').lower().strip()
                    currency = str(d.get('currency') or ('ZNX' if d.get('coins') else 'USDT')).upper()
                    is_withdraw = ('withdraw' in raw_type) or (currency == 'ZNX' and not d.get('memo'))

                    tx_type = 'withdraw' if is_withdraw else 'deposit'
                    default_st = 'pending' if is_withdraw else 'completed'
                    status_code, status_ar = normalize_status(d.get('status'), default_status=default_st)

                    ts = parse_timestamp(d.get('created_at') or d.get('updated_at') or d.get('processed_at'))
                    amount = float(d.get('coins') or d.get('amount') or d.get('usdt_amount') or 0.0)
                    wallet_addr = d.get('wallet_address') or d.get('sender_address') or None
                    memo = d.get('memo')

                    if is_withdraw:
                        short_w = f"{wallet_addr[:6]}...{wallet_addr[-4:]}" if wallet_addr and len(str(wallet_addr)) > 12 else (wallet_addr or 'محفظة TON')
                        fallback_details = f"سحب إلى المحفظة: {short_w}"
                        failure_msg = d.get('failure_reason') or ('تم رفض الطلب وإعادة الرصيد لحسابك' if status_code == 'failed' else None)
                    else:
                        fallback_details = f"إيداع عبر شبكة TON (الفاتورة: {memo})" if memo else "إيداع تلقائي عبر شبكة TON"
                        failure_msg = d.get('failure_reason') or d.get('error') or None

                    details_text = _clean_details_value(d.get('details'), fallback_details)

                    transactions.append({
                        'id': tx_id,
                        'type': tx_type,
                        'type_ar': 'سحب' if is_withdraw else 'إيداع',
                        'amount': amount,
                        'currency': currency,
                        'status': status_code,
                        'status_ar': status_ar,
                        'failure_reason': failure_msg,
                        'timestamp': ts,
                        'formatted_date': format_exact_datetime(ts),
                        'wallet_address': wallet_addr,
                        'details': details_text
                    })

                # 2. جلب فواتير وطلبات الإيداع من جدول deposit_invoices
                rows = _fetch_table_rows_for_user(conn, cur, 'deposit_invoices', clean_id)
                for d in rows:
                    memo = d.get('memo')
                    tx_hash = d.get('tx_hash')
                    inv_id = d.get('invoice_id') or d.get('id')

                    if (tx_hash and str(tx_hash) in seen_tx_ids) or (memo and f"memo_{memo}" in seen_tx_ids):
                        continue

                    tx_id = str(tx_hash or inv_id or memo or f"INV-{d.get('id')}").strip()
                    if tx_id in seen_tx_ids:
                        continue
                    seen_tx_ids.add(tx_id)

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
                rows = _fetch_table_rows_for_user(conn, cur, 'withdraw_requests', clean_id)
                for d in rows:
                    raw_id = d.get('tx_id') or d.get('tx_hash') or d.get('request_id') or f"WD-{d.get('id')}"
                    tx_id = str(raw_id).strip()
                    if tx_id in seen_tx_ids:
                        continue
                    seen_tx_ids.add(tx_id)

                    status_code, status_ar = normalize_status(d.get('status'), default_status='pending')
                    ts = parse_timestamp(d.get('created_at') or d.get('updated_at') or d.get('processed_at'))
                    amount = float(d.get('coins') or d.get('amount') or d.get('usdt_amount') or 0.0)
                    currency = str(d.get('currency') or 'ZNX').upper()
                    wallet_addr = d.get('wallet_address') or d.get('address') or 'محفظة TON'
                    short_w = f"{wallet_addr[:6]}...{wallet_addr[-4:]}" if wallet_addr and len(str(wallet_addr)) > 12 else wallet_addr

                    fallback_details = f"سحب إلى المحفظة: {short_w}"
                    details_text = _clean_details_value(d.get('details'), fallback_details)
                    failure_msg = (
                        d.get('failure_reason')
                        or d.get('reject_reason')
                        or d.get('admin_note')
                        or ('تم رفض الطلب وإعادة الرصيد لحسابك' if status_code == 'failed' else None)
                    )

                    transactions.append({
                        'id': tx_id,
                        'type': 'withdraw',
                        'type_ar': 'سحب',
                        'amount': amount,
                        'currency': currency,
                        'status': status_code,
                        'status_ar': status_ar,
                        'failure_reason': failure_msg,
                        'timestamp': ts,
                        'formatted_date': format_exact_datetime(ts),
                        'wallet_address': wallet_addr,
                        'details': details_text
                    })

                # 4. جلب أي سجلات إضافية من جدول المعاملات العام transactions
                rows = _fetch_table_rows_for_user(conn, cur, 'transactions', clean_id)
                for d in rows:
                    raw_id = d.get('tx_id') or d.get('tx_hash') or f"TX-{d.get('id')}"
                    tx_id = str(raw_id).strip()
                    memo = d.get('memo')
                    if tx_id in seen_tx_ids or (memo and f"memo_{memo}" in seen_tx_ids):
                        continue
                    seen_tx_ids.add(tx_id)

                    raw_type = str(d.get('type') or 'withdraw').lower().strip()
                    tx_type = 'withdraw' if 'withdraw' in raw_type else 'deposit'
                    default_st = 'pending' if tx_type == 'withdraw' else 'completed'
                    status_code, status_ar = normalize_status(d.get('status'), default_status=default_st)
                    ts = parse_timestamp(d.get('created_at') or d.get('updated_at'))
                    amount = float(d.get('coins') or d.get('amount') or d.get('usdt_amount') or 0.0)
                    currency = str(d.get('currency') or ('ZNX' if tx_type == 'withdraw' else 'USDT')).upper()
                    wallet_addr = d.get('wallet_address')
                    short_w = f"{wallet_addr[:6]}...{wallet_addr[-4:]}" if wallet_addr and len(str(wallet_addr)) > 12 else (wallet_addr or 'محفظة TON')

                    fallback_details = f"سحب إلى المحفظة: {short_w}" if tx_type == 'withdraw' else f"إيداع {currency} عبر شبكة TON"
                    details_text = _clean_details_value(d.get('details'), fallback_details)
                    failure_msg = d.get('failure_reason') or ('تم رفض الطلب وإعادة الرصيد لحسابك' if (tx_type == 'withdraw' and status_code == 'failed') else None)

                    transactions.append({
                        'id': tx_id,
                        'type': tx_type,
                        'type_ar': 'سحب' if tx_type == 'withdraw' else 'إيداع',
                        'amount': amount,
                        'currency': currency,
                        'status': status_code,
                        'status_ar': status_ar,
                        'failure_reason': failure_msg,
                        'timestamp': ts,
                        'formatted_date': format_exact_datetime(ts),
                        'wallet_address': wallet_addr,
                        'details': details_text
                    })

    except Exception as e:
        logger.error(f"❌ [history_db] خطأ في الاتصال بقاعدة بيانات Supabase: {e}")

    transactions.sort(key=lambda x: x.get('timestamp', 0), reverse=True)
    return transactions


def record_transaction(user_id, tx_type: str, amount: float, currency: str = 'USDT',
                       status: str = 'pending', tx_id: str = None, wallet_address: str = None,
                       memo: str = None, details: str = None, failure_reason: str = None) -> bool:
    """تسجيل أي عملية إيداع أو سحب مباشرة في Supabase"""
    init_history_tables()
    clean_id = _sanitize_id(user_id)
    if not clean_id or not get_db_connection:
        return False

    details_json = json.dumps({"text": details or ""}, ensure_ascii=False) if details else None

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                _exec_safe(conn, cur, """
                    INSERT INTO transactions 
                    (tx_id, user_id, type, coins, amount, currency, status, wallet_address, memo, details, failure_reason, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """, (
                    tx_id, clean_id, tx_type, float(amount), float(amount), currency,
                    status, wallet_address, memo, details_json, failure_reason
                ))
        return True
    except Exception as e:
        logger.error(f"⚠️ [history_db] فشل في تسجيل المعاملة في Supabase: {e}")
        return False
