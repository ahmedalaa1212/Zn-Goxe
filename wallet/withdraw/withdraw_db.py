from datetime import datetime, timezone
import firebase_admin
from firebase_admin import firestore

db = firestore.client()

def get_withdraw_config():
    """قراءة الخطة المعتمدة لمستويات السحب من Firebase وإنشائها تلقائياً إذا لم توجد"""
    doc_ref = db.collection('settings').document('withdraw_config')
    doc = doc_ref.get()
    
    default_config = {
        "rate_coins_per_usd": 100000,
        "fee_percent": 3,
        "levels": [
            {"level": 1, "type": "auto", "min": 10, "max": 100},
            {"level": 2, "type": "auto", "min": 500, "max": 1500},
            {"level": 3, "type": "auto", "min": 10000, "max": 50000},
            {"level": 4, "type": "manual", "min": 100000, "max": 200000},
            {"level": 5, "type": "manual", "min": 400000, "max": 800000},
            {"level": 6, "type": "manual", "min": 1000000, "max": 999999999}
        ]
    }
    
    if not doc.exists:
        doc_ref.set(default_config)
        return default_config
    
    data = doc.to_dict() or {}
    if 'levels' not in data or not isinstance(data.get('levels'), list):
        doc_ref.set(default_config)
        return default_config

    return data

def has_withdrawn_today(user_id):
    """فحص الحد اليومي للسحب بناءً على UTC 00:00"""
    today_utc = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    user_doc = db.collection('users').document(str(user_id)).get()
    if user_doc.exists:
        return user_doc.to_dict().get('last_withdraw_date') == today_utc
    return False

def get_user_full_details(user_id):
    """جلب تفاصيل المستخدم وفحص كافة خانات الرصيد المتاحة"""
    user_ref = db.collection('users').document(str(user_id))
    user_doc = user_ref.get()
    
    if not user_doc.exists:
        return None
    
    data = user_doc.to_dict() or {}
    created_at = data.get('created_at')
    
    if hasattr(created_at, 'strftime'):
        joined_date = created_at.strftime('%Y-%m-%d %H:%M UTC')
    else:
        joined_date = str(created_at or 'غير محدد')

    raw_bal = data.get('balance')
    if raw_bal is None:
        raw_bal = data.get('balance_zn', data.get('coins', 0.0))
        
    real_balance = float(raw_bal)

    return {
        "user_id": str(user_id),
        "first_name": data.get('first_name', 'غير محدد'),
        "username": data.get('username', 'لا يوجد'),
        "joined_date": joined_date,
        "referrals_count": data.get('referrals_count', 0),
        "balance": real_balance,
        "total_earned": data.get('total_earned', 0),
        "withdraw_count": data.get('withdraw_count', 0),
        "last_withdraw_date": data.get('last_withdraw_date', 'لم يسحب من قبل'),
        "is_banned": data.get('is_banned', False)
    }

def process_withdraw_db(user_id, coins_amount, ton_amount, level_info, wallet_address):
    """خصم الرصيد وتسجيل السحب فوراً في processed_txs ليظهر في قسيمة السجلات"""
    transaction = db.transaction()
    user_ref = db.collection('users').document(str(user_id))
    
    @firestore.transactional
    def execute_in_transaction(txn, ref):
        snapshot = ref.get(transaction=txn)
        if not snapshot.exists:
            return False, "المستخدم غير موجود", None
        
        user_data = snapshot.to_dict() or {}
        raw_bal = user_data.get('balance')
        if raw_bal is None:
            raw_bal = user_data.get('balance_zn', user_data.get('coins', 0.0))
            
        current_bal = float(raw_bal)
        
        if current_bal < coins_amount:
            return False, "رصيدك الحالي غير كافٍ.", None

        today_utc = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        
        txn.update(ref, {
            'balance': firestore.Increment(-coins_amount),
            'last_withdraw_date': today_utc,
            'wallet_address': wallet_address,
            'withdraw_count': firestore.Increment(1)
        })

        tx_ref = db.collection('processed_txs').document()
        status = "completed" if level_info['type'] == "auto" else "pending"
        
        # التسجيل في processed_txs مع ضبط type="withdraw" لضمان ظهوره في قسم السجلات بالواجهة
        txn.set(tx_ref, {
            'user_id': str(user_id),
            'coins': coins_amount,
            'ton_amount': ton_amount,
            'usdt_amount': ton_amount,
            'wallet': wallet_address,
            'status': status,
            'level': level_info['level'],
            'withdraw_type': level_info['type'],
            'type': "withdraw",
            'processed_at': firestore.SERVER_TIMESTAMP,
            'created_at': firestore.SERVER_TIMESTAMP
        })

        msg = "تم طلب السحب بنجاح وتسجيل المعاملة!"
        return True, msg, tx_ref.id

    return execute_in_transaction(transaction, user_ref)
