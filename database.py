import os
import json
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime

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

def create_tables():
    pass # No SQL tables needed

def init_user(telegram_id, referred_by=None, first_name="صديق"):
    global db
    if db is None: initialize_firebase()
    if db is None: return
    
    telegram_id = str(telegram_id).strip()
    user_ref = db.collection('users').document(telegram_id)
    
    try:
        doc = user_ref.get()
        if not doc.exists:
            # تنظيف الـ referred_by عشان لو جي بكلمة startapp أو ref
            if referred_by:
                referred_by = str(referred_by).replace('ref_', '').strip()
                if referred_by == telegram_id:
                    referred_by = None
                    
            user_data = {
                'telegram_id': telegram_id,
                'user_name': first_name,
                'balance': 0.0,
                'ad_balance': 0.0,
                'is_banned': False,
                'last_claim_time': datetime.utcnow().isoformat(),
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
                
            # حفظ المستخدم الجديد
            user_ref.set(user_data)
            print(f"🚀 New user created: {telegram_id} | Referred by: {referred_by}")
            
            # تحديث بيانات الداعي فوراً
            if referred_by:
                ref_user_ref = db.collection('users').document(referred_by)
                if ref_user_ref.get().exists:
                    ref_user_ref.update({
                        'invited_friends_count': firestore.Increment(1),
                        f'referral_details.{telegram_id}': {'name': first_name, 'earned': 0.0}
                    })
        else:
            # لو المستخدم موجود، نتأكد إن الحقول الجديدة موجودة
            data = doc.to_dict()
            updates = {}
            if 'pending_ref_earnings' not in data: updates['pending_ref_earnings'] = 0.0
            if 'invited_friends_count' not in data: updates['invited_friends_count'] = 0
            if 'referral_details' not in data: updates['referral_details'] = {}
            if updates:
                user_ref.update(updates)
                
    except Exception as e:
        print(f"❌ Error in init_user: {e}")

def get_user_data(telegram_id):
    global db
    if db is None: initialize_firebase()
    if db is None: return None
    
    telegram_id = str(telegram_id).strip()
    try:
        user_ref = db.collection('users').document(telegram_id)
        doc = user_ref.get()
        if doc.exists:
            return doc.to_dict()
        return None
    except Exception as e:
        print(f"❌ Error in get_user_data: {e}")
        return None

def update_balance(telegram_id, new_balance):
    global db
    if db is None: initialize_firebase()
    try:
        db.collection('users').document(str(telegram_id).strip()).update({'balance': float(new_balance)})
    except Exception as e:
        pass

def update_claim_time(telegram_id):
    global db
    if db is None: initialize_firebase()
    try:
        db.collection('users').document(str(telegram_id).strip()).update({'last_claim_time': datetime.utcnow().isoformat()})
    except Exception as e:
        pass

# الدالة السحرية لإضافة الـ 10%
def add_referral_bonus(telegram_id, claimed_amount):
    global db
    if db is None: initialize_firebase()
    if db is None or claimed_amount <= 0: return
    
    try:
        telegram_id = str(telegram_id).strip()
        user_ref = db.collection('users').document(telegram_id)
        doc = user_ref.get()
        if doc.exists:
            user_data = doc.to_dict()
            referred_by = user_data.get('referred_by')
            
            if referred_by:
                bonus = float(claimed_amount) * 0.10
                referrer_ref = db.collection('users').document(str(referred_by))
                
                if referrer_ref.get().exists:
                    referrer_ref.update({
                        'pending_ref_earnings': firestore.Increment(bonus),
                        f'referral_details.{telegram_id}.earned': firestore.Increment(bonus)
                    })
                    print(f"💰 10% Bonus ({bonus} ZN) added to referrer {referred_by}")
    except Exception as e:
        print(f"❌ Error adding referral bonus: {e}")
