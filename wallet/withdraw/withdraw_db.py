from datetime import datetime, timezone
import firebase_admin
from firebase_admin import firestore

FEE_USD_FIXED = 0.02

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
        return "0.0000"
    try:
        val = float(amount)
        if val == 0:
            return "0.0000"
        return f"{val:,.4f}"
    except Exception:
        return str(amount)

def extract_user_balance(data):
    """جلب رصيد ZNX للمستخدم بشكل دقيق مع أولوية قصوى لـ znx_balance"""
    if not isinstance(data, dict):
        return 0.0
    
    balance_keys = ['znx_balance', 'total_znx_earned', 'znx', 'balance']
    for key in balance_keys:
        if key in data and data[key] is not None:
            try:
                val = float(data[key])
                if val >= 0:
                    return val
            except (ValueError, TypeError):
                pass
    return 0.0

def extract_user_usd_balance(data):
    """جلب رصيد الدولار للمستخدم بشكل دقيق"""
    if not isinstance(data, dict):
        return 0.0
    
    usd_keys = ['usd_balance', 'usd', 'usd_amount']
    for key in usd_keys:
        if key in data and data[key] is not None:
            try:
                val = float(data[key])
                if val >= 0:
                    return val
            except (ValueError, TypeError):
                pass
    return 0.0

def get_global_znx_state():
    """جلب إجمالي ZNX المحول كلياً لتحديد الشريحة الحالية"""
    db = safe_get_db()
    if not db:
        return {"total_converted_znx": 0.0}
    try:
        doc = db.collection('znx_global_state').document('summary').get()
        if doc.exists:
            d = doc.to_dict() or {}
            return {
                "total_converted_znx": float(d.get('total_converted_znx', 0.0))
            }
    except Exception as e:
        print(f"⚠️ خطأ جلب znx_global_state: {e}")
    return {"total_converted_znx": 0.0}

def get_active_tier_info(total_converted):
    """حساب الشريحة الحالية بناءً على total_converted_znx"""
    total = float(total_converted or 0.0)
    
    if total < 1500000:
        return {
            "tier": 1,
            "name": "الشريحة الأولى (0 حتى 1.5M ZNX)",
            "min_znx": 1000.0,
            "rate": 10,
            "quota": 1500000,
            "fee_usd": FEE_USD_FIXED
        }
    elif total < 2000000:
        return {
            "tier": 2,
            "name": "الشريحة الثانية (1.5M إلى 2M ZNX)",
            "min_znx": 350.0,
            "rate": 30,
            "quota": 2000000,
            "fee_usd": FEE_USD_FIXED
        }
    elif total < 2500000:
        return {
            "tier": 3,
            "name": "الشريحة الثالثة (2M إلى 2.5M ZNX)",
            "min_znx": 125.0,
            "rate": 80,
            "quota": 2500000,
            "fee_usd": FEE_USD_FIXED
        }
    elif total < 4000000:
        return {
            "tier": 4,
            "name": "الشريحة الرابعة (2.5M إلى 4M ZNX)",
            "min_znx": 50.0,
            "rate": 200,
            "quota": 4000000,
            "fee_usd": FEE_USD_FIXED
        }
    elif total < 5500000:
        return {
            "tier": 5,
            "name": "الشريحة الخامسة (4M إلى 5.5M ZNX)",
            "min_znx": 20.0,
            "rate": 600,
            "quota": 5500000,
            "fee_usd": FEE_USD_FIXED
        }
    elif total < 8000000:
        return {
            "tier": 6,
            "name": "الشريحة السادسة (5.5M إلى 8M ZNX)",
            "min_znx": 6.0,
            "rate": 1600,
            "quota": 8000000,
            "fee_usd": FEE_USD_FIXED
        }
    else:
        return {
            "tier": 7,
            "name": "الشريحة السابعة (فوق 8M ZNX)",
            "min_znx": 2.5,
            "rate": 4000,
            "quota": 9000000,
            "fee_usd": FEE_USD_FIXED
        }

def get_user_doc(user_id):
    """البحث عن مستند المستخدم برقم الـ ID أو tg_id"""
    db = safe_get_db()
    if not db:
        return None, None
    
    str_user_id = str(user_id).strip()
    
    # 1. البحث المباشر برقم Document ID
    doc_ref = db.collection('users').document(str_user_id)
    doc = doc_ref.get()
    if doc.exists:
        return doc_ref, doc.to_dict()
    
    # 2. البحث بحقول tg_id أو user_id أو telegram_id
    for field in ['tg_id', 'user_id', 'telegram_id']:
        q = db.collection('users').where(field, '==', str_user_id).limit(1).get()
        if q:
            return q[0].reference, q[0].to_dict()
        if str_user_id.isdigit():
            q_int = db.collection('users').where(field, '==', int(str_user_id)).limit(1).get()
            if q_int:
                return q_int[0].reference, q_int[0].to_dict()

    return None, None

def get_user_full_details(user_id):
    try:
        _, data = get_user_doc(user_id)
        if not data:
            return None
        
        real_znx_balance = extract_user_balance(data)
        real_usd_balance = extract_user_usd_balance(data)
        global_state = get_global_znx_state()
        active_tier = get_active_tier_info(global_state.get('total_converted_znx', 0.0))

        raw_wallets = data.get('wallets')
        wallets = raw_wallets if isinstance(raw_wallets, dict) else {}
        wallet_addr = data.get('wallet_address') or wallets.get('ZNX', '')

        return {
            "user_id": str(user_id),
            "first_name": data.get('first_name', 'غير محدد'),
            "username": data.get('username', 'لا يوجد'),
            "balance": real_znx_balance,
            "znx_balance": real_znx_balance,
            "usd_balance": real_usd_balance,
            "total_converted_znx": global_state.get('total_converted_znx', 0.0),
            "active_tier": active_tier,
            "is_banned": data.get('is_banned', False),
            "wallets": wallets,
            "wallet_address": wallet_addr
        }
    except Exception as e:
        print(f"⚠️ خطأ get_user_full_details: {e}")
        return None

def save_user_wallet(user_id, currency, wallet_address):
    db = safe_get_db()
    if not db:
        return False, "تعذر الاتصال بقاعدة البيانات."

    try:
        user_ref, _ = get_user_doc(user_id)
        if not user_ref:
            return False, "المستخدم غير موجود في قاعدة البيانات."

        user_ref.set({
            'wallets': {'ZNX': wallet_address},
            'wallet_address': wallet_address
        }, merge=True)
        return True, "تم حفظ المحفظة بنجاح."
    except Exception as e:
        print(f"⚠️ خطأ حفظ المحفظة في Firestore: {e}")
        return False, f"خطأ أثناء الحفظ: {str(e)}"
