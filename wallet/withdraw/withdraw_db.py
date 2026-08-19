import os
import sys
import datetime

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.abspath(os.path.join(CURRENT_DIR, "../../"))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from wallet.wallet_db import get_user_wallet_balances, update_user_balance, get_firestore_db, get_sqlite_conn

def process_withdraw_request(user_id: int, address: str, amount_zn: float) -> dict:
    """خصم الرصيد وتسجيل العملية في Firestore و SQLite بدقة"""
    balances = get_user_wallet_balances(user_id)
    current_zn = balances.get('zn_balance', 0.0)

    if current_zn < amount_zn:
        return {'success': False, 'error': 'الرصيد غير كافٍ لإتمام السحب'}

    # 100,000 ZN = $1.00 USD
    net_zn = amount_zn * 0.97
    usd_value = net_zn / 100000.0

    # 1. خصم الرصيد عبر دالة التحديث الموحدة
    deduct_success = update_user_balance(user_id, amount_zn, currency='zn', operation='subtract')
    if not deduct_success:
        return {'success': False, 'error': 'فشل خصم الرصيد من قاعدة البيانات'}

    tx_data = {
        'user_id': str(user_id),
        'address': address,
        'amount_zn': amount_zn,
        'net_zn': net_zn,
        'usd_value': usd_value,
        'status': 'pending',
        'type': 'withdraw',
        'created_at': datetime.datetime.utcnow().isoformat()
    }

    # 2. حفظ السجل في Firestore
    db = get_firestore_db()
    if db:
        try:
            db.collection('withdrawals').add(tx_data)
        except Exception as e:
            print(f"⚠️ خطأ حفظ طلب السحب في Firestore: {e}")

    # 3. حفظ السجل في SQLite
    conn = get_sqlite_conn()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS withdraw_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT,
                    address TEXT,
                    amount_zn REAL,
                    usd_value REAL,
                    status TEXT,
                    created_at TEXT
                )
            ''')
            cursor.execute('''
                INSERT INTO withdraw_history (user_id, address, amount_zn, usd_value, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (str(user_id), address, amount_zn, usd_value, 'pending', tx_data['created_at']))
            conn.commit()
        except Exception as e:
            print(f"⚠️ خطأ حفظ طلب السحب في SQLite: {e}")
        finally:
            conn.close()

    new_balances = get_user_wallet_balances(user_id)
    return {
        'success': True,
        'message': 'تم تقديم طلب السحب بنجاح!',
        'new_balance': new_balances.get('zn_balance', 0.0)
    }
