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
    def _sanitize_id(val):
        if val is None:
            return None
        s = str(val).strip()
        return s[:-2] if s.endswith('.0') else s

_TABLES_INITIALIZED = False


def init_history_tables():
    """
    تهيئة الجداول الأساسية فقط مرة واحدة وإنهاء أي اتصال معلق في Supabase
    بدون استخدام ALTER TABLE التي تسبب قفل الجداول (Locks).
    """
    global _TABLES_INITIALIZED
    if _TABLES_INITIALIZED:
        return True

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # فك أي جلسة معلقة سابقاً في Supabase كانت تسبب بطء أو توقف القراءة
                try:
                    cur.execute("""
                        SELECT pg_terminate_backend(pid)
                        FROM pg_stat_activity
                        WHERE datname = current_database()
                          AND pid <> pg_backend_pid()
                          AND (state = 'idle in transaction' OR query LIKE '%ALTER TABLE%');
                    """)
                except Exception:
                    conn.rollback()

                # التأكد من وجود جدول طلبات السحب وجدول المعاملات العام فقط
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

            conn.commit()
        _TABLES_INITIALIZED = True
        return True
    except Exception as e:
        logger.error(f"⚠️ [history_db] خطأ أثناء تهيئة جداول السجلات: {e}")
        return False


def _clean_details_value(val, fallback: str) -> str:
    """استخراج النص العربي للتفاصيل سواء كان العمود في Supabase من نوع JSONB أو TEXT"""
    if not val:
        return fallback
    if isinstance(val, dict):
        return str(val.get('text') or val.get('details') or val.get('memo') or fallback)
    if isinstance(val, str):
        s = val.strip()
        if not s or s in ['{}', 'null', 'None', '""']:
            return fallback
        if (s.startswith('{') and s.endswith('}')) or (s.startswith('"') and s.endswith('"')):
            try:
                parsed = json.loads(s)
                if isinstance(parsed, dict):
                    return str(parsed.get('text') or parsed.get('details') or parsed.get('memo') or fallback)
                if isinstance(parsed, str) and parsed.strip():
                    return parsed.strip()
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


def _query_user_rows(conn, table_name: str, clean_id: str, order_col: str = 'created_at', limit: int = 100):
    """جلب صفوف المستخدم مباشرة من الجدول مع معالجة آمنة لأي خطأ دون تعطيل الاتصال"""
    try:
        with conn.cursor() as cur:
            query = f"""
                SELECT * FROM {table_name}
                WHERE CAST(user_id AS TEXT) = %s
                ORDER BY {order_col} DESC
                LIMIT {int(limit)}
            """
            cur.execute(query, (clean_id,))
            col_names = [desc[0] for desc in cur.description]
            rows = [dict(zip(col_names, row)) for row in cur.fetchall()]
        conn.commit()
        return rows
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        # محاولة احتياطية بدون ORDER BY created_at في حال عدم وجود عمود created_at
        try:
            with conn.cursor() as cur:
                query = f"""
                    SELECT * FROM {table_name}
                    WHERE CAST(user_id AS TEXT) = %s
                    LIMIT {int(limit)}
                """
                cur.execute(query, (clean_id,))
                col_names = [desc[0] for desc in cur.description]
                rows = [dict(zip(col_names, row)) for row in cur.fetchall()]
            conn.commit()
            return rows
        except Exception as e2:
            try:
                conn.rollback()
            except Exception:
                pass
            logger.debug(f"⚠️ [history_db] تخطي جدول {table_name}: {e2}")
            return []


def get_user_transaction_history(user_id, force_refresh: bool = False):
    """جلب كافة سجلات الإيداع والسحب الخاصة بالمستخدم من Supabase مباشرة"""
    init_history_tables()

    transactions = []
    seen_keys = set()

    clean_id = _sanitize_id(user_id)
    if not clean_id:
        return transactions

    try:
        with get_db_connection() as conn:
            # 1. جلب الإيداعات المؤكدة من جدول processed_txs
            rows = _query_user_rows(conn, 'processed_txs', clean_id, 'created_at')
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

                fallback_details = f"إيداع باقة ${amount:g} USDT عبر شبكة TON" + (f" ({memo})" if memo else "")
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
            rows = _query_user_rows(conn, 'deposit_invoices', clean_id, 'created_at')
            for d in rows:
                memo = d.get('memo')
                tx_hash = d.get('tx_hash')
                inv_id = d.get('invoice_id') or d.get('id')

                if (tx_hash and f"dep_{tx_hash}" in seen_keys) or (memo and f"memo_{memo}" in seen_keys):
                    continue

                tx_id = str(tx_hash or memo or inv_id or f"INV-{d.get('id')}")
                dedup_key = f"inv_{tx_id}"
                if dedup_key in seen_keys:
                    continue
                seen_keys.add(dedup_key)
                if memo:
                    seen_keys.add(f"memo_{memo}")

                status_code, status_ar = normalize_status(d.get('status'), default_status='pending')
                ts = parse_timestamp(d.get('updated_at') or d.get('created_at'))
                amount = float(d.get('usdt_amount') or d.get('amount') or 0.0)
                ton_val = float(d.get('ton_amount') or 0.0)
                currency = str(d.get('currency') or 'USDT').upper()

                if ton_val > 0:
                    fallback_details = f"إيداع باقة ${amount:g} USDT (~{ton_val:.4f} TON) عبر شبكة TON"
                else:
                    fallback_details = f"طلب إيداع باقة ${amount:g} USDT عبر شبكة TON"
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
            rows = _query_user_rows(conn, 'withdraw_requests', clean_id, 'created_at')
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

            # 4. جلب المعاملات الإضافية من جدول transactions
            rows = _query_user_rows(conn, 'transactions', clean_id, 'created_at')
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

                fallback_details = f"سحب إلى المحفظة: {wallet_addr or 'محفظة TON'}" if tx_type == 'withdraw' else f"إيداع بقيمة ${amount:g} {currency} عبر شبكة TON"
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
    return transactions


def record_transaction(user_id, tx_type: str, amount: float, currency: str = 'USDT',
                       status: str = 'pending', tx_id: str = None, wallet_address: str = None,
                       memo: str = None, details: str = None, failure_reason: str = None) -> bool:
    """تسجيل أي عملية إيداع أو سحب مباشرة في Supabase"""
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
