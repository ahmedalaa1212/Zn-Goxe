import sqlite3
import os
import sys
import json
import time
import logging

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "../../"))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

DB_PATH = os.path.join(ROOT_DIR, 'database.db')
logger = logging.getLogger('history_db')

def get_db_connection():
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    return conn

def get_firestore_db():
    """الاتصال بـ Firestore جلب المرجع التلقائي"""
    try:
        import database
        if hasattr(database, 'get_db'):
            db_inst = database.get_db()
            if db_inst:
                return db_inst
    except Exception as e:
        logger.debug(f"Firestore from database.py failed: {e}")

    try:
        import firebase_admin
        from firebase_admin import credentials, firestore

        if not firebase_admin._apps:
            cred_env = os.getenv('FIREBASE_CREDENTIALS') or os.getenv('FIREBASE_SERVICE_ACCOUNT')
            if cred_env:
                if os.path.exists(cred_env):
                    cred = credentials.Certificate(cred_env)
                else:
                    try:
                        cred_dict = json.loads(cred_env)
                        cred = credentials.Certificate(cred_dict)
                    except Exception:
                        cred = credentials.Certificate(cred_env)
                firebase_admin.initialize_app(cred)
            else:
                service_key_path = os.path.join(ROOT_DIR, "serviceAccountKey.json")
                if os.path.exists(service_key_path):
                    cred = credentials.Certificate(service_key_path)
                    firebase_admin.initialize_app(cred)

        if firebase_admin._apps:
            return firestore.client()
    except Exception as e:
        logger.warning(f"⚠️ [history_db] Firestore access warning: {e}")

    return None

def parse_timestamp(val):
    """تحويل أوقات Firestore المتنوعة إلى Timestamp نقي"""
    if val is None:
        return time.time()
    if hasattr(val, 'timestamp'):
        try:
            return float(val.timestamp())
        except Exception:
            pass
    if isinstance(val, (int, float)):
        val_f = float(val)
        if val_f > 1e11:  # Milliseconds timestamp
            return val_f / 1000.0
        return val_f
    if isinstance(val, str):
        try:
            val_f = float(val)
            if val_f > 1e11:
                return val_f / 1000.0
            return val_f
        except ValueError:
            pass
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(val.replace('Z', '+00:00'))
            return dt.timestamp()
        except Exception:
            pass
    return time.time()

def get_user_transaction_history(user_id):
    """
    تجميع سجلات الإيداع والسحب الخاصة بالمستخدم والبحث بكل الطرق الممكنة (String / Int / Root / Subcollections)
    """
    transactions = []
    seen_ids = set()

    if not user_id:
        return transactions

    tg_str = str(user_id).strip()
    tg_int = int(tg_str) if tg_str.isdigit() else None
    
    search_ids = [tg_str]
    if tg_int is not None:
        search_ids.append(tg_int)

    # -------------------------------------------------------------
    # 1. الاستعلام الشامل من Firebase / Firestore
    # -------------------------------------------------------------
    fs_db = get_firestore_db()
    if fs_db:
        # (أ) الاستعلام من المجموعة الرئيسية processed_txs (الإيداعات)
        try:
            for s_id in search_ids:
                docs = fs_db.collection('processed_txs').where('user_id', '==', s_id).get()
                for doc in docs:
                    d = doc.to_dict() or {}
                    tx_id = str(d.get('tx_hash') or d.get('memo') or doc.id)
                    if tx_id in seen_ids:
                        continue
                    seen_ids.add(tx_id)

                    tx_type = d.get('type', 'deposit')
                    status = d.get('status', 'completed')
                    status_ar = 'مكتمل' if status in ['completed', 'success'] else ('فاشل' if status in ['failed', 'rejected'] else 'قيد الانتظار')
                    ts = parse_timestamp(d.get('processed_at') or d.get('created_at'))

                    transactions.append({
                        'id': tx_id,
                        'type': tx_type,
                        'type_ar': 'إيداع' if tx_type == 'deposit' else 'سحب',
                        'amount': float(d.get('usdt_amount') or d.get('amount') or 0.0),
                        'currency': d.get('currency', 'USDT'),
                        'status': status,
                        'status_ar': status_ar,
                        'failure_reason': d.get('failure_reason') or d.get('error') or None,
                        'timestamp': ts,
                        'details': d.get('memo') or d.get('details') or ('إيداع USDT تلقائي عبر شبكة TON' if tx_type == 'deposit' else 'سحب USDT')
                    })
        except Exception as e:
            logger.error(f"⚠️ [history_db] Firestore processed_txs query error: {e}")

        # (ب) الاستعلام من طلبات السحب withdraw_requests / withdrawals / transactions
        for col_name in ['withdraw_requests', 'withdrawals', 'transactions']:
            try:
                for s_id in search_ids:
                    docs = fs_db.collection(col_name).where('user_id', '==', s_id).get()
                    for doc in docs:
                        d = doc.to_dict() or {}
                        tx_id = str(d.get('tx_id') or d.get('tx_hash') or d.get('request_id') or doc.id)
                        if tx_id in seen_ids:
                            continue
                        seen_ids.add(tx_id)

                        tx_type = d.get('type', 'withdraw')
                        status = d.get('status', 'pending')
                        status_ar = 'مكتمل' if status in ['completed', 'success'] else ('مرفوض/فاشل' if status in ['failed', 'rejected'] else 'قيد الانتظار')
                        ts = parse_timestamp(d.get('created_at') or d.get('timestamp') or d.get('processed_at'))

                        transactions.append({
                            'id': tx_id,
                            'type': tx_type,
                            'type_ar': 'إيداع' if tx_type == 'deposit' else 'سحب',
                            'amount': float(d.get('amount') or d.get('usdt_amount') or 0.0),
                            'currency': d.get('currency', 'USDT'),
                            'status': status,
                            'status_ar': status_ar,
                            'failure_reason': d.get('failure_reason') or d.get('reject_reason') or d.get('note') or None,
                            'timestamp': ts,
                            'details': d.get('details') or (f"سحب إلى: {d.get('wallet_address', 'محفظة TON')}" if tx_type == 'withdraw' else 'إيداع عبر TON')
                        })
            except Exception as e:
                logger.error(f"⚠️ [history_db] Firestore {col_name} error: {e}")

        # (جـ) الاستعلام الاحتياطي من المجلدات الفرعية داخل users/{user_id}/...
        try:
            user_ref = fs_db.collection('users').document(tg_str)
            
            for sub_col in ['deposit_history', 'withdraw_history', 'transactions']:
                sub_docs = user_ref.collection(sub_col).limit(50).get()
                for doc in sub_docs:
                    d = doc.to_dict() or {}
                    tx_id = str(d.get('tx_hash') or d.get('tx_id') or d.get('memo') or doc.id)
                    if tx_id in seen_ids:
                        continue
                    seen_ids.add(tx_id)

                    is_dep = 'deposit' in sub_col or d.get('type') == 'deposit'
                    tx_type = 'deposit' if is_dep else 'withdraw'
                    status = d.get('status', 'completed' if is_dep else 'pending')
                    status_ar = 'مكتمل' if status in ['completed', 'success'] else ('فاشل' if status in ['failed', 'rejected'] else 'قيد الانتظار')
                    ts = parse_timestamp(d.get('processed_at') or d.get('created_at') or d.get('timestamp'))

                    transactions.append({
                        'id': tx_id,
                        'type': tx_type,
                        'type_ar': 'إيداع' if is_dep else 'سحب',
                        'amount': float(d.get('usdt_amount') or d.get('amount') or 0.0),
                        'currency': d.get('currency', 'USDT'),
                        'status': status,
                        'status_ar': status_ar,
                        'failure_reason': d.get('failure_reason') or d.get('error') or None,
                        'timestamp': ts,
                        'details': d.get('memo') or d.get('details') or ('إيداع USDT تلقائي' if is_dep else f"سحب إلى: {d.get('wallet_address', 'محفظة TON')}")
                    })
        except Exception as e:
            logger.error(f"⚠️ [history_db] Firestore user subcollections query error: {e}")

    # -------------------------------------------------------------
    # 2. الاستعلام الاحتياطي من SQLite
    # -------------------------------------------------------------
    try:
        if os.path.exists(DB_PATH):
            conn = get_db_connection()
            cursor = conn.cursor()

            for s_id in search_ids:
                try:
                    cursor.execute("SELECT tx_hash, usdt_amount, memo, created_at FROM processed_txs WHERE user_id = ? ORDER BY id DESC LIMIT 50", (s_id,))
                    for r in cursor.fetchall():
                        tx_id = str(r['tx_hash'] or r['memo'])
                        if tx_id in seen_ids:
                            continue
                        seen_ids.add(tx_id)

                        transactions.append({
                            'id': tx_id,
                            'type': 'deposit',
                            'type_ar': 'إيداع',
                            'amount': float(r['usdt_amount'] or 0.0),
                            'currency': 'USDT',
                            'status': 'completed',
                            'status_ar': 'مكتمل',
                            'failure_reason': None,
                            'timestamp': parse_timestamp(r['created_at']),
                            'details': r['memo'] or 'إيداع عبر شبكة TON'
                        })
                except Exception:
                    pass

                try:
                    cursor.execute("SELECT id, amount, currency, status, wallet_address, failure_reason, created_at FROM withdraw_requests WHERE user_id = ? ORDER BY id DESC LIMIT 50", (s_id,))
                    for r in cursor.fetchall():
                        tx_id = f"WD-{r['id']}"
                        if tx_id in seen_ids:
                            continue
                        seen_ids.add(tx_id)

                        st = r['status'] or 'pending'
                        st_ar = 'ناجح' if st in ['completed', 'success'] else ('مرفوض' if st in ['failed', 'rejected'] else 'قيد الانتظار')

                        transactions.append({
                            'id': tx_id,
                            'type': 'withdraw',
                            'type_ar': 'سحب',
                            'amount': float(r['amount'] or 0.0),
                            'currency': r['currency'] or 'USDT',
                            'status': st,
                            'status_ar': st_ar,
                            'failure_reason': r['failure_reason'] if 'failure_reason' in r.keys() else None,
                            'timestamp': parse_timestamp(r['created_at']),
                            'details': f"سحب إلى: {r['wallet_address'] or 'محفظة TON'}"
                        })
                except Exception:
                    pass

            conn.close()

    except Exception as e:
        logger.error(f"⚠️ [history_db] SQLite query error: {e}")

    # 3. ترتيب المعاملات من الأحدث للأقدم
    transactions.sort(key=lambda x: x['timestamp'], reverse=True)
    return transactions
