from datetime import datetime, timezone
import firebase_admin
from firebase_admin import firestore

db = firestore.client()

def get_withdraw_config():
    """قراءة القواعد المستندة في Firestore"""
    doc = db.collection('settings').document('withdraw_config').get()
    if doc.exists:
        return doc.to_dict()
    
    default_config = {
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
    db.collection('settings').document('withdraw_config').set(default_config)
    return default_config

def has_withdrawn_today(user_id):
    """فحص الحد اليومي بناءً على UTC 00:00"""
    today_utc = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    user_doc = db.collection('users').document(str(user_id)).get()
    if user_doc.exists:
        return user_doc.to_dict().get('last_withdraw_date') == today_utc
    return False

def get_user_full_details(user_id):
    """جلب كشف حساب وتفاصيل المستخدم الكاملة لكشف محاولات الغش"""
    user_doc = db.collection('users').document(str(user_id)).get()
    if not user_doc.exists:
        return None
    
    data = user_doc.to_dict()
    created_at = data.get('created_at')
    
    if hasattr(created_at, 'strftime'):
        joined_date = created_at.strftime('%Y-%m-%d %H:%M UTC')
    else:
        joined_date = str(created_at or 'غير محدد')

    return {
        "user_id": user_id,
        "first_name": data.get('first_name', 'غير محدد'),
        "username": data.get('username', 'لا يوجد'),
        "joined_at": joined_date,
        "referrals_count": data.get('referrals_count', 0),
        "balance": data.get('balance', 0),
        "total_earned": data.get('total_earned', 0),
        "withdraw_count": data.get('withdraw_count', 0),
        "last_withdraw_date": data.get('last_withdraw_date', 'لم يسحب من قبل'),
        "is_banned": data.get('is_banned', False)
    }

def process_withdraw_db(user_id, coins_amount, ton_amount, level_info, wallet_address):
    """تحديث الرصيد وإنشاء المعاملة داخل Transaction آمنة"""
    transaction = db.transaction()
    user_ref = db.collection('users').document(str(user_id))
    
    @firestore.transactional
    def execute_in_transaction(txn, ref):
        snapshot = ref.get(transaction=txn)
        if not snapshot.exists:
            return False, "المستخدم غير موجود", None
        
        user_data = snapshot.to_dict()
        if user_data.get('balance', 0) < coins_amount:
            return False, "رصيدك الحالي غير كافٍ.", None

        today_utc = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        
        # 1. خصم الرصيد وتثبيت المحفظة وتاريخ السحب
        txn.update(ref, {
            'balance': firestore.Increment(-coins_amount),
            'last_withdraw_date': today_utc,
            'wallet_address': wallet_address
        })

        # 2. تسجيل المعاملة
        tx_ref = db.collection('processed_txs').document()
        status = "completed" if level_info['type'] == "auto" else "pending"
        
        txn.set(tx_ref, {
            'user_id': str(user_id),
            'coins': coins_amount,
            'ton_amount': ton_amount,
            'wallet': wallet_address,
            'status': status,
            'level': level_info['level'],
            'type': level_info['type'],
            'created_at': firestore.SERVER_TIMESTAMP
        })

        msg = "تم طلب السحب بنجاح!" if level_info['type'] == 'auto' else "تم إرسال الطلب للأدمن للمراجعة."
        return True, msg, tx_ref.id

    return execute_in_transaction(transaction, user_ref)
