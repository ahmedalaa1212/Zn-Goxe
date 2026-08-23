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

def format_crypto_display(amount):
    if amount is None:
        return "0"
    try:
        val = float(amount)
        if val == 0:
            return "0"
        formatted = f"{val:,.8f}".rstrip('0').rstrip('.')
        return formatted if formatted else "0"
    except Exception:
        return str(amount)

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
            "supported_currencies": ["DOGE", "TRX", "PEPE", "LTC"],
            "levels": [
                {"level": 1, "type": "auto", "min": 10, "max": 10},
                {"level": 2, "type": "auto", "min": 50, "max": 200},
                {"level": 3, "type": "auto", "min": 500, "max": 2000},
                {"level": 4, "type": "auto", "min": 5000, "max": 20000},
                {"level": 5, "type": "manual", "min": 50000, "max": 100000},
                {"level": 6, "type": "manual", "min": 150000, "max": 300000},
                {"level": 7, "type": "manual", "min": 400000, "max": 600000},
                {"level": 8, "type": "manual", "min": 700000, "max": 900000},
                {"level": 9, "type": "manual", "min": 1000000, "max": 1500000}
            ]
        }
        if not doc.exists:
            doc_ref.set(default_config)
            print("✅ [FIREBASE] تم إنشاء مستند settings/withdraw_config بالخرائط الجديدة بنجاح!")
        else:
            doc_ref.set({"levels": default_config["levels"], "rate_coins_per_usd": 100000}, merge=True)
    except Exception as e:
        print(f"⚠️ [FIREBASE ERROR] تعذر إنشاء مستند withdraw_config: {e}")

try:
    auto_create_withdraw_config()
except Exception:
    pass

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
        "supported_currencies": ["DOGE", "TRX", "PEPE", "LTC"],
        "levels": [
            {"level": 1, "type": "auto", "min": 10, "max": 10},
            {"level": 2, "type": "auto", "min": 50, "max": 200},
            {"level": 3, "type": "auto", "min": 500, "max": 2000},
            {"level": 4, "type": "auto", "min": 5000, "max": 20000},
            {"level": 5, "type": "manual", "min": 50000, "max": 100000},
            {"level": 6, "type": "manual", "min": 150000, "max": 300000},
            {"level": 7, "type": "manual", "min": 400000, "max": 600000},
            {"level": 8, "type": "manual", "min": 700000, "max": 900000},
            {"level": 9, "type": "manual", "min": 1000000, "max": 1500000}
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
        return data
    except Exception:
        return default_config

def has_withdrawn_today(user_id):
    try:
        today_utc = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        _, user_data = get_user_doc(user_id)
        if user_data:
            return user_data.get('last_withdraw_date') == today_utc
        return False
    except Exception:
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
        current_level = min(withdraw_count + 1, 9)

        raw_wallets = data.get('wallets')
        wallets = raw_wallets if isinstance(raw_wallets, dict) else {}

        return {
            "user_id": str(user_id),
            "first_name": data.get('first_name', 'غير محدد'),
            "username": data.get('username', 'لا يوجد'),
            "joined_date": joined_date,
            "referrals_count": data.get('referrals_count', 0),
            "balance": real_balance,
            "total_earned": data.get('total_earned', 0),
            "withdraw_count": withdraw_count,
            "current_level": current_level,
            "last_withdraw_date": data.get('last_withdraw_date', 'لم يسحب من قبل'),
            "is_banned": data.get('is_banned', False),
            "wallets": wallets,
            "last_wallet_address": data.get('last_wallet_address', '')
        }
    except Exception:
        return None

def save_user_wallet(user_id, currency, wallet_address):
    db = safe_get_db()
    if not db:
        return False, "تعذر الاتصال بقاعدة البيانات."

    try:
        user_ref, _ = get_user_doc(user_id)
        if not user_ref:
            return False, "المستخدم غير موجود في قاعدة البيانات."

        curr_key = currency.upper()
        user_ref.update({
            f'wallets.{curr_key}': wallet_address,
            'last_wallet_address': wallet_address
        })
        return True, "تم حفظ المحفظة بنجاح."
    except Exception as e:
        try:
            user_ref.set({
                'wallets': {
                    curr_key: wallet_address
                },
                'last_wallet_address': wallet_address
            }, merge=True)
            return True, "تم حفظ المحفظة بنجاح."
        except Exception as set_err:
            print(f"⚠️ خطأ حفظ المحفظة في Firestore: {set_err}")
            return False, f"خطأ أثناء الحفظ: {str(set_err)}"

def process_withdraw_db(user_id, coins_amount, currency, wallet_address, crypto_net_amount, level_info):
    db = safe_get_db()
    if not db:
        return False, "تعذر الاتصال بقاعدة البيانات.", None, 0

    try:
        user_ref, user_data = get_user_doc(user_id)
        if not user_ref or not user_data:
            return False, "المستخدم غير موجود", None, 0

        today_utc = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        if user_data.get('last_withdraw_date') == today_utc:
            return False, "يسمح بعملية سحب واحدة فقط يومياً. حاول بعد 00:00 UTC.", None, 0

        transaction = db.transaction()
        
        @firestore.transactional
        def execute_in_transaction(txn, ref):
            snapshot = ref.get(transaction=txn)
            if not snapshot.exists:
                return False, "المستخدم غير موجود", None, 0
            
            u_data = snapshot.to_dict() or {}
            raw_bal = u_data.get('balance')
            if raw_bal is None:
                raw_bal = u_data.get('zn_balance', u_data.get('balance_zn', u_data.get('coins', 0.0)))
                
            try:
                current_bal = float(raw_bal)
            except (ValueError, TypeError):
                current_bal = 0.0
            
            if current_bal < coins_amount:
                return False, "رصيدك الحالي غير كافٍ.", None, current_bal

            curr_key = str(currency).upper()
            new_bal = current_bal - coins_amount

            txn.update(ref, {
                'balance': firestore.Increment(-coins_amount),
                'last_withdraw_date': today_utc,
                'last_wallet_address': wallet_address,
                f'wallets.{curr_key}': wallet_address,
                'withdraw_count': firestore.Increment(1)
            })

            tx_ref = db.collection('processed_txs').document()
            
            initial_status = "processing" if level_info.get('type') == "auto" else "pending"
            usd_value = coins_amount / 100000.0
            formatted_crypto_str = format_crypto_display(crypto_net_amount)

            txn.set(tx_ref, {
                'user_id': str(user_id),
                'coins': coins_amount,
                'coins_amount': coins_amount,
                'usd_value': usd_value,
                'currency': curr_key,
                'asset': curr_key,
                'coin': curr_key,
                'symbol': curr_key,
                'amount': crypto_net_amount,
                'crypto_amount': crypto_net_amount,
                'crypto_net_amount': crypto_net_amount,
                'amount_crypto': crypto_net_amount,
                'net_amount': crypto_net_amount,
                'final_amount': crypto_net_amount,
                'payout_amount': crypto_net_amount,
                'fee_percent': 3,
                'wallet': wallet_address,
                'wallet_address': wallet_address,
                'address': wallet_address,
                'status': initial_status,
                'level': level_info.get('level', 1),
                'withdraw_type': level_info.get('type', 'manual'),
                'type': "withdraw",
                'provider': "FaucetPay",
                'title': f"سحب {curr_key}",
                'details': f"سحب {curr_key}",
                'details_text': f"سحب {curr_key}",
                'note': f"سحب {curr_key}",
                'description': f"{formatted_crypto_str} {curr_key}",
                'processed_at': firestore.SERVER_TIMESTAMP,
                'created_at': firestore.SERVER_TIMESTAMP,
                'updated_at': firestore.SERVER_TIMESTAMP
            })

            return True, "تم تسجيل الطلب وبدء المعالجة بنجاح!", tx_ref.id, new_bal

        return execute_in_transaction(transaction, user_ref)
    except Exception as e:
        return False, f"حدث خطأ أثناء تنفيذ عملية السحب: {str(e)}", None, 0
