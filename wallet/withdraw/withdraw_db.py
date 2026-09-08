import os
import time
from datetime import datetime, timezone
import firebase_admin
from firebase_admin import firestore

# قراءة عنوان عقد العملة الذكي من متغيرات بيئة Railway
ZNX_CONTRACT_ADDRESS = os.getenv("ZNX_CONTRACT_ADDRESS", "EQCp7mIbe-eR-j6b7opnHBtCbl74gnyYAP2XZlSpHkERkwdJ")

# --- نظام Caching لتوفير قراءات الفايربيس وتسريع الاستجابة ---
_TIER_CACHE = {
    "data": None,
    "timestamp": 0
}
CACHE_TTL_SECONDS = 5  # خفض الكاش إلى 5 ثوانٍ لضمان مزامنة الأرصدة فوراً

def safe_get_db():
    try:
        if firebase_admin._apps:
            return firestore.client()
        else:
            firebase_admin.initialize_app()
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
        if val <= 0:
            return "0.0000"
        return f"{val:,.4f}"
    except Exception:
        return str(amount)

def extract_user_balance(data):
    """جلب رصيد ZNX للمستخدم بشكل دقيق واعتماد حقل znx_balance فقط لمنع تكرار أو تضارب الأرصدة"""
    if not isinstance(data, dict):
        return 0.0
    
    if 'znx_balance' in data and data['znx_balance'] is not None:
        try:
            val = float(data['znx_balance'])
            if val >= 0:
                return val
        except (ValueError, TypeError):
            pass
            
    return 0.0

def extract_usd_balance(data):
    """جلب رصيد الدولار للمستخدم"""
    if not isinstance(data, dict):
        return 0.0
    try:
        return float(data.get('usd_balance', 0.0))
    except (ValueError, TypeError):
        return 0.0

def get_current_withdraw_tier():
    """جلب بيانات الشريحة الحالية لسحب العملات مع Caching فائق السرعة لتخفيف الضغط على الفايربيس"""
    now = time.time()
    if _TIER_CACHE["data"] and (now - _TIER_CACHE["timestamp"] < CACHE_TTL_SECONDS):
        return _TIER_CACHE["data"]

    db = safe_get_db()
    default_tier = {
        "tier": 1,
        "name": "الشريحة الأولى",
        "min_withdraw_znx": 1000.0,
        "fixed_fee_usd": 0.02
    }
    if not db:
        return default_tier

    try:
        stats_doc = db.collection('znx_global_stats').document('summary').get()
        if not stats_doc.exists:
            _TIER_CACHE["data"] = default_tier
            _TIER_CACHE["timestamp"] = now
            return default_tier
        
        stats = stats_doc.to_dict() or {}
        total_global_znx = float(stats.get('total_converted_znx', 0.0))
        tiers = stats.get('tiers_config') or []

        res_tier = default_tier
        for item in tiers:
            min_v = float(item.get("min_pts", 0.0))
            raw_max = item.get("max_pts")
            max_v = float('inf') if str(raw_max).lower() in ("inf", "infinity", "none") else float(raw_max)
            if min_v <= total_global_znx < max_v:
                res_tier = {
                    "tier": int(item.get('tier', 1)),
                    "name": str(item.get('name', 'الشريحة الحالية')),
                    "min_withdraw_znx": float(item.get('min_withdraw_znx', 1000.0)),
                    "fixed_fee_usd": float(item.get('fixed_fee_usd', 0.02))
                }
                break
        else:
            if tiers:
                last = tiers[-1]
                res_tier = {
                    "tier": int(last.get('tier', 7)),
                    "name": str(last.get('name', 'الشريحة السابعة')),
                    "min_withdraw_znx": float(last.get('min_withdraw_znx', 2.5)),
                    "fixed_fee_usd": float(last.get('fixed_fee_usd', 0.02))
                }
        
        _TIER_CACHE["data"] = res_tier
        _TIER_CACHE["timestamp"] = now
        return res_tier
    except Exception as e:
        print(f"⚠️ خطأ جلب شريحة السحب: {e}")
    
    return default_tier

def get_user_doc(user_id):
    """البحث عن مستند المستخدم برقم الـ ID أو tg_id بسرعة وحماية"""
    db = safe_get_db()
    if not db:
        return None, None
    
    str_user_id = str(user_id).strip()
    
    doc_ref = db.collection('users').document(str_user_id)
    doc = doc_ref.get()
    if doc.exists:
        return doc_ref, doc.to_dict()
    
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
        usd_balance = extract_usd_balance(data)
        raw_wallets = data.get('wallets')
        wallets = raw_wallets if isinstance(raw_wallets, dict) else {}
        wallet_addr = data.get('wallet_address') or wallets.get('ZNX', '')

        return {
            "user_id": str(user_id),
            "first_name": data.get('first_name', 'غير محدد'),
            "username": data.get('username', 'لا يوجد'),
            "balance": real_balance,
            "znx_balance": real_balance,
            "usd_balance": usd_balance,
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
