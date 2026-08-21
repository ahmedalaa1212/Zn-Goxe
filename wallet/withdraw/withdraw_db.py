from datetime import datetime, timezone
import firebase_admin
from firebase_admin import firestore

def safe_get_db():
    try:
        if firebase_admin._apps:
            return firestore.client()
    except Exception as e:
        print(f"⚠️ خطأ الاتصال بـ Firestore في withdraw_db: {e}")
    return None

get_db = safe_get_db

def auto_create_withdraw_config():
    db = safe_get_db()
    if not db:
        return
    try:
        doc_ref = db.collection('settings').document('withdraw_config')
        doc = doc_ref.get()
        default_config = {
            "rate_coins_per_usd": 100000,
            "fee_percent": 3,
            "network_fee_gram": 0.0015,
            "levels": [
                {"level": 1, "type": "auto", "min": 10, "max": 100},
                {"level": 2, "type": "auto", "min": 500, "max": 1500},
                {"level": 3, "type": "auto", "min": 10000, "max": 50000},
                {"level": 4, "type": "manual", "min": 100000, "max": 200000},
                {"level": 5, "type": "manual", "min": 400000, "max": 800000},
                {"level": 6, "type": "manual", "min": 1000000, "max": 999999999}
            ]
        }
        doc_ref.set(default_config, merge=True)
        print("✅ [FIREBASE] تم تحديث مستند settings/withdraw_config بنجاح!")
    except Exception as e:
        print(f"⚠️ [FIREBASE ERROR] تعذر إنشاء مستند withdraw_config: {e}")

try:
    auto_create_withdraw_config()
except Exception as e:
    print(f"⚠️ تنبيه تشغيل auto_create_withdraw_config: {e}")

def get_user_doc(user_id):
    db = safe_get_db()
    if not db:
        return None, None
    
    str_user_id = str(user_id).strip()
    
    doc_ref = db.collection('users').document(str_user_id)
    doc = doc_ref.get()
    if doc.exists:
        return doc_ref, doc.to_dict()
    
    q1 = db.collection('users').where('user_id', '==', str_user_id).limit(1).get()
    if q1:
        return q1[0].reference, q1[0].to_dict()

    q2 = db.collection('users').where('telegram_id', '==', str_user_id).limit(1).get()
    if q2:
        return q2[0].reference, q2[0].to_dict()
        
    if str_user_id.isdigit():
        q3 = db.collection('users').where('telegram_id', '==', int(str_user_id)).limit(1).get()
        if q3:
            return q3[0].reference, q3[0].to_dict()

    return None, None

def get_withdraw_config():
    default_config = {
        "rate_coins_per_usd": 100000,
        "fee_percent": 3,
        "network_fee_gram": 0.0015,
        "levels": [
            {"level": 1, "type": "auto", "min": 10, "max": 100},
            {"level": 2, "type": "auto", "min": 500, "max": 1500},
            {"level": 3, "type": "auto", "min": 10000, "max": 50000},
            {"level": 4, "type": "manual", "min": 100000, "max": 200000},
            {"level": 5, "type": "manual", "min": 400000, "max": 800000},
            {"level": 6, "type": "manual", "min": 1000000, "max": 999999999}
        ]
    }
    
    db = safe_get_db()
    if not db:
        return default_config

    try:
        doc_ref = db.collection('settings').document('withdraw_config')
        doc = doc_ref.get()
        
        if not doc.exists:
            doc_ref.set(default_config)
            return default_config
        
        data = doc.to_dict() or {}
        data['levels'] = default_config['levels']
        data['rate_coins_per_usd'] = 100000
        return data
    except Exception as e:
        print(f"⚠️ Exception in get_withdraw_config: {e}")
        return default_config

def has_withdrawn_today(user_id):
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

        withdraw_count = int(data.get('withdraw_count', 0) or 0)

        return {
            "user_id": str(user_id),
            "first_name": data.get('first_name', 'غير محدد'),
            "username": data.get('username', 'لا يوجد'),
            "joined_date": joined_date,
            "referrals_count": data.get('referrals_count', 0),
            "balance": real_balance,
            "total_earned": data.get('total_earned', 0),
            "withdraw_count": withdraw_count,
            "last_withdraw_date": data.get('last_withdraw_date', 'لم يسحب من قبل'),
            "is_banned": data.get('is_banned', False)
        }
    except Exception as e:
        print(f"❌ Error getting user full details for {user_id}: {e}")
        return None

def process_withdraw_db(user_id, coins_amount, gram_amount, level_info, wallet_address):
    db = safe_get_db()
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
                raw_bal = u_data.get('zn_balance', u_data.get('balance_zn', u_data.get('coins', 0.0)))
                
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
            
            initial_status = "processing" if level_info.get('type') == "auto" else "pending"
            
            txn.set(tx_ref, {
                'user_id': str(user_id),
                'coins': coins_amount,
                'gram_amount': gram_amount,
                'amount_gram': gram_amount,
                'currency': 'GRAM',
                'asset': 'GRAM',
                'wallet': wallet_address,
                'status': initial_status,
                'level': level_info.get('level', 1),
                'withdraw_type': level_info.get('type', 'manual'),
                'type': "withdraw",
                'title': "سحب GRAM",
                'description': f"سحب {gram_amount:.4f} GRAM",
                'processed_at': firestore.SERVER_TIMESTAMP,
                'created_at': firestore.SERVER_TIMESTAMP
            })

            return True, "تم تسجيل الطلب وبدء المعالجة!", tx_ref.id

        return execute_in_transaction(transaction, user_ref)
    except Exception as e:
        print(f"❌ Error in process_withdraw_db for {user_id}: {e}")
        return False, f"حدث خطأ أثناء تنفيذ عملية السحب: {str(e)}", None
