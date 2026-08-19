from datetime import datetime, timezone
import firebase_admin
from firebase_admin import firestore

db = firestore.client()

def get_withdraw_config():
    doc = db.collection('settings').document('withdraw_config').get()
    if doc.exists:
        return doc.to_dict()
    # افتراضي في حال عدم وجود المستند
    return {
        "rate_coins_per_usd": 100000,
        "fee_percent": 3,
        "levels": [
            {"level": 1, "type": "auto", "min": 10, "max": 100},
            {"level": 2, "type": "auto", "min": 500, "max": 1500},
            {"level": 3, "type": "auto", "min": 10000, "max": 50000},
            {"level": 4, "type": "manual", "min": 100000, "max": 200000},
            {"level": 5, "type": "manual", "min": 400000, "max": 800000},
            {"level": 6, "type": "manual", "min": 1000000, "max": 1500000}
        ]
    }

def has_withdrawn_today(user_id):
    today_utc = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    user_doc = db.collection('users').document(str(user_id)).get()
    if user_doc.exists:
        last_date = user_doc.to_dict().get('last_withdraw_date')
        return last_date == today_utc
    return False

def process_withdraw_db(user_id, coins_amount, ton_amount, level_info, wallet_address):
    user_ref = db.collection('users').document(str(user_id))
    user_doc = user_ref.get()
    if not user_doc.exists:
        return False, "المستخدم غير موجود"
    
    user_data = user_doc.to_dict()
    if user_data.get('balance', 0) < coins_amount:
        return False, "رصيدك غير كافي"

    today_utc = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    current_count = user_data.get('withdraw_count', 0) + 1
    
    # خصم الرصيد وتحديث تاريخ السحب
    user_ref.update({
        'balance': firestore.Increment(-coins_amount),
        'last_withdraw_date': today_utc,
        'withdraw_count': current_count,
        'wallet_address': wallet_address
    })

    # تسجيل المعاملة
    tx_ref = db.collection('processed_txs').document()
    tx_data = {
        'user_id': str(user_id),
        'coins': coins_amount,
        'ton_amount': ton_amount,
        'wallet': wallet_address,
        'status': 'completed' if level_info['type'] == 'auto' else 'pending',
        'level': level_info['level'],
        'created_at': firestore.SERVER_TIMESTAMP
    }
    tx_ref.set(tx_data)
    
    return True, tx_data
