from datetime import datetime, timezone
import firebase_admin
from firebase_admin import firestore

def get_db():
    """جلب الاتصال الموحد المجهز بملف database.py"""
    try:
        from database import get_db as main_get_db
        return main_get_db()
    except Exception:
        if firebase_admin._apps:
            return firestore.client()
    return None

def get_user_doc(user_id):
    """دالة لجلب مستند المستخدم بسلاسة"""
    db = get_db()
    if not db:
        return None, None
    
    str_user_id = str(user_id).strip()
    doc_ref = db.collection('users').document(str_user_id)
    doc = doc_ref.get()
    
    if doc.exists:
        return doc_ref, doc.to_dict()
    
    query = db.collection('users').where('telegram_id', '==', str_user_id).limit(1).get()
    if query:
        return query[0].reference, query[0].to_dict()
        
    return None, None

def get_withdraw_config():
    """قراءة وإجبار إنشاء مستند withdraw_config داخل مجلد settings بنفس شكل الصورة"""
    default_config = {
        "rate_coins_per_usd": 100000,
        "fee_percent": 3,
        "levels": [
            {"level": 1, "type": "auto", "min": 10000, "max": 50000},
            {"level": 2, "type": "auto", "min": 50000, "max": 100000},
            {"level": 3, "type": "manual", "min": 100000, "max": 250000},
            {"level": 4, "type": "manual", "min": 250000, "max": 500000},
            {"level": 5, "type": "manual", "min": 500000, "max": 1000000},
            {"level": 6, "type": "manual", "min": 1000000, "max": 999999999}
        ]
    }
    
    db = get_db()
    if not db:
        return default_config

    try:
        doc_ref = db.collection('settings').document('withdraw_config')
        doc = doc_ref.get()
        
        if not doc.exists:
            doc_ref.set(default_config)
            print("✅ تم إنشاء مستند settings/withdraw_config بنجاح في Firebase!")
            return default_config
        
        data = doc.to_dict() or {}
        if 'levels' not in data:
            doc_ref.set(default_config, merge=True)
            return default_config

        return data
    except Exception as e:
        print(f"⚠️ Exception in get_withdraw_config: {e}")
        return default_config

def has_withdrawn_today(user_id):
    """فحص الحد اليومي للسحب بناءً على UTC 00:00"""
    try:
        today_utc = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        _, user_data = get_user_doc(user_id)
        if user_data:
            return user_data.get('last_withdraw_date') == today_utc
        return False
    except Exception as e:
        print(f"⚠️ Exception in has_withdrawn_today for {user_id}: {e}")
        return False

def get_user_full_details(user_id):
    """جلب تفاصيل المستخدم للواجهة وحساب السحب"""
    try:
        _, data = get_user_doc(user_id)
        if not data:
            return None
        
        created_at = data.get('created_at')
        if hasattr(created_at, 'strftime'):
            joined_date = created_at.strftime('%Y-%m-%d %H:%M UTC')
        else:
            joined_date = str(created_at or 'غير محدد')

        raw_bal = data.get('balance')
        if raw_bal is None:
            raw_bal = data.get('zn_balance', data.get('balance_zn', data.get('coins', 0.0)))
            
        try:
            real_balance = float(raw_bal)
        except (ValueError, TypeError):
            real_balance = 0.0

        return {
            "user_id": str(user_id),
            "first_name": data.get('first_name', 'غير محدد'),
            "username": data.get('username', 'لا يوجد'),
            "joined_date": joined_date,
            "referrals_count": data.get('referrals_count', 0),
            "balance": real_balance,
            "total_earned": data.get('total_earned', 0),
            "withdraw_count": int(data.get('withdraw_count', 0) or 0),
            "last_withdraw_date": data.get('last_withdraw_date', 'لم يسحب من قبل'),
            "is_banned": data.get('is_banned', False)
        }
    except Exception as e:
        print(f"❌ Error getting user full details for {user_id}: {e}")
        return None

def process_withdraw_db(user_id, coins_amount, ton_amount, level_info, wallet_address):
    """خصم الرصيد وتسجيل السحب فوراً في processed_txs"""
    db = get_db()
    if not db:
        return False, "تعذر الاتصال بقاعدة البيانات.", None

    try:
        user_ref, user_data = get_user_doc(user_id)
        if not user_ref or not user_data:
            return False, "المستخدم غير موجود", None

        transaction = db.transaction()
        
        @firestore.transactional
        def execute_in_transaction(txn, ref):
            snapshot = ref.get(transaction=txn)
            if not snapshot.exists:
                return False, "المستخدم غير موجود", None
            
            u_data = snapshot.to_dict() or {}
            raw_bal = u_data.get('balance')
            if raw_bal is None:
                raw_bal = u_data.get('zn_balance', u_data.get('balance_zn', 0.0))
                
            try:
                current_bal = float(raw_bal)
            except (ValueError, TypeError):
                current_bal = 0.0
            
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
            status = "completed" if level_info.get('type') == "auto" else "pending"
            
            txn.set(tx_ref, {
                'user_id': str(user_id),
                'coins': coins_amount,
                'ton_amount': ton_amount,
                'usdt_amount': ton_amount,
                'wallet': wallet_address,
                'status': status,
                'level': level_info.get('level', 1),
                'withdraw_type': level_info.get('type', 'manual'),
                'type': "withdraw",
                'processed_at': firestore.SERVER_TIMESTAMP,
                'created_at': firestore.SERVER_TIMESTAMP
            })

            return True, "تم طلب السحب بنجاح وتسجيل المعاملة!", tx_ref.id

        return execute_in_transaction(transaction, user_ref)
    except Exception as e:
        print(f"❌ Error in process_withdraw_db for {user_id}: {e}")
        return False, f"حدث خطأ أثناء تنفيذ عملية السحب: {str(e)}", None
