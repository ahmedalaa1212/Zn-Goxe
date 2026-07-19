import os
import json
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timezone

db = None

def initialize_firebase():
    global db
    if db is not None:
        return db
    
    firebase_creds_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT')
    if not firebase_creds_json:
        print("❌ [ERROR] FIREBASE_SERVICE_ACCOUNT is NOT SET!")
        return None

    try:
        creds_data = firebase_creds_json.strip()
        if (creds_data.startswith("'") and creds_data.endswith("'")) or \
           (creds_data.startswith('"') and creds_data.endswith('"')):
            creds_data = creds_data[1:-1]
            
        creds_dict = json.loads(creds_data)
        cred = credentials.Certificate(creds_dict)
        
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)
        
        db = firestore.client()
        print("✅ [Firebase-Database] Connected successfully!")
    except Exception as e:
        print(f"❌ [Firebase-Database] Initialization failed: {e}")
    
    return db

def init_user(telegram_id, referred_by=None, first_name="صديق"):
    global db
    if db is None: initialize_firebase()
    if db is None: return False
    
    telegram_id = str(telegram_id).strip()
    user_ref = db.collection('users').document(telegram_id)
    is_new_referral = False
    
    try:
        doc = user_ref.get()
        # تنظيف كود الإحالة
        if referred_by:
            referred_by = str(referred_by).replace('ref_', '').strip()
            if referred_by == telegram_id:
                referred_by = None
                
        if not doc.exists:
            user_data = {
                'telegram_id': telegram_id,
                'user_name': first_name,
                'balance': 0.0,
                'ad_balance': 0.0,
                'is_banned': False,
                'last_claim_time': datetime.now(timezone.utc).isoformat(),
                'storage_level': 0,
                'daily_day': 1,
                'last_daily_claim_time': "2000-01-01T00:00:00+00:00",
                'referred_by': referred_by,
                'pending_ref_earnings': 0.0,
                'invited_friends_count': 0,
                'claimed_ref_tasks': [],
                'referral_details': {}
            }
            for i in range(1, 11):
                user_data[f'lvl{i}_count'] = 0
                
            user_ref.set(user_data)
            
            # تسجيل الصديق عند صاحب الرابط
            if referred_by:
                ref_user_ref = db.collection('users').document(referred_by)
                if ref_user_ref.get().exists:
                    ref_user_ref.update({
                        'invited_friends_count': firestore.Increment(1),
                        f'referral_details.{telegram_id}.name': first_name,
                        f'referral_details.{telegram_id}.earned': 0.0
                    })
                    is_new_referral = True 
        else:
            # لو الحساب موجود بس مكنش عنده مُحيل، ودخل من رابط دلوقتي
            data = doc.to_dict()
            updates = {}
            if not data.get('referred_by') and referred_by:
                updates['referred_by'] = referred_by
                ref_user_ref = db.collection('users').document(referred_by)
                if ref_user_ref.get().exists:
                    ref_user_ref.update({
                        'invited_friends_count': firestore.Increment(1),
                        f'referral_details.{telegram_id}.name': data.get('user_name', first_name),
                        f'referral_details.{telegram_id}.earned': 0.0
                    })
                    is_new_referral = True

            if 'pending_ref_earnings' not in data: updates['pending_ref_earnings'] = 0.0
            if 'invited_friends_count' not in data: updates['invited_friends_count'] = 0
            if 'claimed_ref_tasks' not in data: updates['claimed_ref_tasks'] = []
            if 'referral_details' not in data: updates['referral_details'] = {}
            
            if updates:
                user_ref.update(updates)
                
        return is_new_referral
    except Exception as e:
        print(f"❌ Error in init_user: {e}")
        return False
