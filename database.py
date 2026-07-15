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
    
    # جلب المتغير
    firebase_creds_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT')
    
    if not firebase_creds_json:
        print("❌ [ERROR] FIREBASE_SERVICE_ACCOUNT is NOT SET in environment variables!")
        return None

    try:
        # تنظيف محتمل لعلامات التنصيص
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

# تشغيل التهيئة
initialize_firebase()

def create_tables():
    print("Firestore is ready! No SQL tables needed.")

def init_user(telegram_id):
    global db
    if db is None: initialize_firebase()
    if db is None: return
    
    user_ref = db.collection('users').document(str(telegram_id))
    try:
        doc = user_ref.get()
        if not doc.exists:
            user_data = {
                'telegram_id': int(telegram_id),
                'balance': 0,
                'is_banned': False,
                'last_claim_time': datetime.utcnow().isoformat(),
                'storage_level': 0  # أضفتها عشان نتجنب الخطأ في السيرفر
            }
            for i in range(1, 11):
                user_data[f'lvl{i}_count'] = 0
            user_ref.set(user_data)
            print(f"🚀 New user created in Firebase: {telegram_id}")
    except Exception as e:
        print(f"❌ Error in init_user: {e}")

def get_user_data(telegram_id):
    global db
    if db is None: initialize_firebase()
    if db is None: return None
    
    # التأكد من وجود المستخدم قبل جلب البيانات
    init_user(telegram_id)
    try:
        user_ref = db.collection('users').document(str(telegram_id))
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
        db.collection('users').document(str(telegram_id)).update({'balance': int(new_balance)})
    except Exception as e:
        print(f"❌ Error in update_balance: {e}")

def update_upgrade_level(telegram_id, lvl_column, new_level):
    global db
    if db is None: initialize_firebase()
    try:
        db.collection('users').document(str(telegram_id)).update({lvl_column: int(new_level)})
    except Exception as e:
        print(f"❌ Error in update_upgrade_level: {e}")

def update_claim_time(telegram_id):
    global db
    if db is None: initialize_firebase()
    try:
        db.collection('users').document(str(telegram_id)).update({'last_claim_time': datetime.utcnow().isoformat()})
    except Exception as e:
        print(f"❌ Error in update_claim_time: {e}")
