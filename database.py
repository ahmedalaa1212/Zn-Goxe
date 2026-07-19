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
        print("❌ [ERROR] FIREBASE_SERVICE_ACCOUNT is NOT SET in environment variables!")
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

initialize_firebase()

def create_tables():
    print("Firestore is ready! No SQL tables needed.")

def init_user(telegram_id, referred_by=None, first_name="صديق"):
    global db
    if db is None: initialize_firebase()
    if db is None: return
    
    telegram_id = str(telegram_id).strip()
    user_ref = db.collection('users').document(telegram_id)
    try:
        doc = user_ref.get()
        if not doc.exists:
            user_data = {
                'telegram_id': telegram_id,
                'first_name': first_name,
                'balance': 0.0,
                'ad_balance': 0.0, 
                'is_banned': False,
                'last_claim_time': datetime.utcnow().isoformat(),
                'storage_level': 0,
                'referred_by': referred_by if referred_by and referred_by != telegram_id else None,
                'pending_ref_earnings': 0.0,
                'invited_friends_count': 0,
                'claimed_ref_tasks': [],
                'referral_details': {} # 🔥 خريطة لتسجيل أرباح كل صديق بالـ ID
            }
            for i in range(1, 11):
                user_data[f'lvl{i}_count'] = 0
            user_ref.set(user_data)
            print(f"🚀 New user created in Firebase: {telegram_id}")
            
            # 🔥 لو فيه شخص دعاه، نزود عدد أصدقاء الشخص ده ونسجل بياناته
            if user_data['referred_by']:
                ref_user_ref = db.collection('users').document(user_data['referred_by'])
                ref_doc = ref_user_ref.get()
                if ref_doc.exists:
                    # إضافة الصديق الجديد بصفر أرباح كبداية عشان يظهر في القائمة
                    ref_user_ref.update({
                        'invited_friends_count': firestore.Increment(1),
                        f'referral_details.{telegram_id}': {'name': first_name, 'earned': 0.0}
                    })
        else:
            data = doc.to_dict()
            updates = {}
            if 'ad_balance' not in data: updates['ad_balance'] = 0.0
            if 'pending_ref_earnings' not in data: updates['pending_ref_earnings'] = 0.0
            if 'invited_friends_count' not in data: updates['invited_friends_count'] = 0
            if 'claimed_ref_tasks' not in data: updates['claimed_ref_tasks'] = []
            if 'referral_details' not in data: updates['referral_details'] = {}
            if 'first_name' not in data: updates['first_name'] = first_name
            
            if updates:
                user_ref.update(updates)
    except Exception as e:
        print(f"❌ Error in init_user: {e}")

def get_user_data(telegram_id):
    global db
    if db is None: initialize_firebase()
    if db is None: return None
    
    telegram_id = str(telegram_id).strip()
    init_user(telegram_id)
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
        telegram_id = str(telegram_id).strip()
        db.collection('users').document(telegram_id).update({'balance': float(new_balance)})
    except Exception as e:
        print(f"❌ Error in update_balance: {e}")

def update_upgrade_level(telegram_id, lvl_column, new_level):
    global db
    if db is None: initialize_firebase()
    try:
        telegram_id = str(telegram_id).strip()
        db.collection('users').document(telegram_id).update({lvl_column: int(new_level)})
    except Exception as e:
        print(f"❌ Error in update_upgrade_level: {e}")

def update_claim_time(telegram_id):
    global db
    if db is None: initialize_firebase()
    try:
        telegram_id = str(telegram_id).strip()
        db.collection('users').document(telegram_id).update({'last_claim_time': datetime.utcnow().isoformat()})
    except Exception as e:
        print(f"❌ Error in update_claim_time: {e}")
