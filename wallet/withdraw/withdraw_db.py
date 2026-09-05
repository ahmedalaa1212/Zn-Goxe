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

def extract_user_balance(data):
    """جلب رصيد ZNX للمستخدم بشكل دقيق مع دعم الحقول المختلفة"""
    if not isinstance(data, dict):
        return 0.0
    
    balance_keys = ['znx_balance', 'balance', 'zn_balance', 'coins', 'user_balance', 'zn_coins']
    for key in balance_keys:
        if key in data and data[key] is not None:
            try:
                val = float(data[key])
                if val >= 0:
                    return val
            except (ValueError, TypeError):
                pass
    return 0.0

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
        
        real_balance = extract_user_balance(data)
        raw_wallets = data.get('wallets')
        wallets = raw_wallets if isinstance(raw_wallets, dict) else {}
        wallet_addr = data.get('wallet_address') or wallets.get('ZNX', '')

        return {
            "user_id": str(user_id),
            "first_name": data.get('first_name', 'غير محدد'),
            "username": data.get('username', 'لا يوجد'),
            "balance": real_balance,
            "znx_balance": real_balance,
            "is_banned": data.get('is_banned', False),
            "wallets": wallets,
            "wallet_address": wallet_addr
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

        user_ref.set({
            'wallets': {'ZNX': wallet_address},
            'wallet_address': wallet_address
        }, merge=True)
        return True, "تم حفظ المحفظة بنجاح."
    except Exception as e:
        print(f"⚠️ خطأ حفظ المحفظة في Firestore: {e}")
        return False, f"خطأ أثناء الحفظ: {str(e)}"
