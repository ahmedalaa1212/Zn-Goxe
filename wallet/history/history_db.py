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
    """
    الاتصال بـ Firestore جلب المرجع التلقائي
    """
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

def get_user_transaction_history(user_id: int):
    """
    تجميع وطباعة سجلات الإيداع والسحب الخاصة بالمستخدم ودمجها مع أسباب الفشل والتأخير
    """
    transactions = []
    seen_ids = set()

    if not user_id:
        return transactions

    # -------------------------------------------------------------
    # 1. الاستعلام من Firebase / Firestore
    # -------------------------------------------------------------
    fs_db = get_firestore_db()
    if fs_db:
        try:
            user_ref = fs_db.collection('users').document(str(user_id))
            
            # (أ) سجلات الإيداع (Deposits)
            dep_docs = user_ref.collection('deposit_history').limit(50).get()
            for doc in dep_docs:
                d = doc.to_dict() or {}
                tx_id = d.get('tx_hash') or d.get('memo') or doc.id
                if tx_id in seen_ids:
                    continue
                seen_ids.add(tx_id)

                status = d.get('status', 'completed')
                status_ar = 'مكتمل' if status in ['completed', 'success'] else ('فاشل' if status in ['failed', 'rejected'] else 'قيد الانتظار')
                
                created_at = d.get('processed_at') or d.get('created_at') or time.time()
                ts = created_at.timestamp() if hasattr(created_at, 'timestamp') else (float(created_at) if isinstance(created_at, (int, float)) else time.time())

                transactions.append({
                    'id': str(tx_id),
                    'type': 'deposit',
                    'type_ar': 'إيداع',
                    'amount': float(d.get('usdt_amount') or d.get('amount') or 0.0),
                    'currency': 'USDT',
                    'status': status,
                    'status_ar': status_ar,
                    'failure_reason': d.get('failure_reason') or d.get('error') or None,
                    'timestamp': ts,
                    'details': d.get('memo') or 'إيداع USDT تلقائي عبر شبكة TON'
                })

            # (ب) سجلات السحب (Withdrawals)
            with_docs = user_ref.collection('withdraw_history').limit(50).get()
            for doc in with_docs:
                d = doc.to_dict() or {}
                tx_id = d.get('tx_id') or d.get('request_id') or doc.id
                if tx_id in seen_ids:
                    continue
                seen_ids.add(tx_id)

                status = d.get('status', 'pending')
                status_ar = 'ناجح' if status in ['completed', 'success'] else ('مرفوض' if status in ['failed', 'rejected'] else 'قيد الانتظار')

                created_at = d.get('created_at') or time.time()
                ts = created_at.timestamp() if hasattr(created_at, 'timestamp') else (float(created_at) if isinstance(created_at, (int, float)) else time.time())

                transactions.append({
                    'id': str(tx_id),
                    'type': 'withdraw',
                    'type_ar': 'سحب',
                    'amount': float(d.get('amount') or d.get('usdt_amount') or 0.0),
                    'currency': d.get('currency', 'USDT'),
                    'status': status,
                    'status_ar': status_ar,
                    'failure_reason': d.get('failure_reason') or d.get('reject_reason') or d.get('note') or None,
                    'timestamp': ts,
                    'details': f"سحب إلى: {d.get('wallet_address', 'محفظة TON')}"
                })
        except Exception as e:
            logger.error(f"⚠️ [history_db] Firestore query error: {e}")

    # -------------------------------------------------------------
    # 2. الاستعلام الاحتياطي المكمل من SQLite
    # -------------------------------------------------------------
    try:
        if os.path.exists(DB_PATH):
            conn = get_db_connection()
            cursor = conn.cursor()

            # الإيداعات في SQLite
            try:
                cursor.execute("SELECT tx_hash, usdt_amount, memo, created_at FROM processed_txs WHERE user_id = ? ORDER BY id DESC LIMIT 50", (user_id,))
                rows = cursor.fetchall()
                for r in rows:
                    tx_id = r['tx_hash'] or r['memo']
                    if tx_id in seen_ids:
                        continue
                    seen_ids.add(tx_id)

                    transactions.append({
                        'id': str(tx_id),
                        'type': 'deposit',
                        'type_ar': 'إيداع',
                        'amount': float(r['usdt_amount'] or 0.0),
                        'currency': 'USDT',
                        'status': 'completed',
                        'status_ar': 'مكتمل',
                        'failure_reason': None,
                        'timestamp': time.time(),
                        'details': r['memo'] or 'إيداع عبر شبكة TON'
                    })
            except Exception:
                pass

            # السحوبات في SQLite
            try:
                cursor.execute("SELECT id, amount, currency, status, wallet_address, failure_reason, created_at FROM withdraw_requests WHERE user_id = ? ORDER BY id DESC LIMIT 50", (user_id,))
                w_rows = cursor.fetchall()
                for r in w_rows:
                    tx_id = f"WD-{r['id']}"
                    if tx_id in seen_ids:
                        continue
                    seen_ids.add(tx_id)

                    st = r['status'] or 'pending'
                    st_ar = 'ناجح' if st in ['completed', 'success'] else ('مرفوض' if st in ['failed', 'rejected'] else 'قيد الانتظار')

                    transactions.append({
                        'id': str(tx_id),
                        'type': 'withdraw',
                        'type_ar': 'سحب',
                        'amount': float(r['amount'] or 0.0),
                        'currency': r['currency'] or 'USDT',
                        'status': st,
                        'status_ar': st_ar,
                        'failure_reason': r['failure_reason'] if 'failure_reason' in r.keys() else None,
                        'timestamp': time.time(),
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
