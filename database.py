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
    
    firebase_creds_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT', '').strip()
    if firebase_creds_json:
        # تنظيف علامات التنصيص الزائدة تلقائياً
        if (firebase_creds_json.startswith("'") and firebase_creds_json.endswith("'")) or \
           (firebase_creds_json.startswith('"') and firebase_creds_json.endswith('"')):
            firebase_creds_json = firebase_creds_json[1:-1].strip()
        try:
            creds_dict = json.loads(firebase_creds_json)
            cred = credentials.Certificate(creds_dict)
            # تجنب إعادة التهيئة لو منشط مسبقاً
            if not firebase_admin._apps:
                firebase_admin.initialize_app(cred)
            db = firestore.client()
            print("✅ [Firebase-Database] Connected successfully!")
        except Exception as e:
            print(f"❌ [Firebase-Database] Failed to initialize: {e}")
    else:
        print("⚠️ [Firebase-Database] FIREBASE_SERVICE_ACCOUNT variable is missing!")
    return db

# تشغيل التهيئة فوراً عند استدعاء الملف
initialize_firebase()

def create_tables():
    # الفايربيس سحابي ومرن ولا يحتاج لإنشاء جداول مسبقة كقواعد البيانات التقليدية
    print("Firestore is ready! No SQL tables needed.")

def init_user(telegram_id):
    global db
    if db is None:
        initialize_firebase()
    if db is None:
        return
    
    user_ref = db.collection('users').document(str(telegram_id))
    try:
        doc = user_ref.get()
        if not doc.exists:
            user_data = {
                'telegram_id': int(telegram_id),
                'balance': 0,
                'is_banned': False,
                'last_claim_time': datetime.utcnow().isoformat()
            }
            # تهيئة مستويات الترقية من 1 لـ 10 بقيمة 0
            for i in range(1, 11):
                user_data[f'lvl{i}_count'] = 0
            user_ref.set(user_data)
            print(f"Initialized new user in Firebase: {telegram_id}")
    except Exception as e:
        print(f"Error in init_user: {e}")

def get_user_data(telegram_id):
    global db
    if db is None:
        initialize_firebase()
    if db is None:
        return None
    
    init_user(telegram_id)
    try:
        user_ref = db.collection('users').document(str(telegram_id))
        doc = user_ref.get()
        if doc.exists:
            data = doc.to_dict()
            # التأكد من وجود خانات المستويات لتجنب أي مشاكل بالبوت
            for i in range(1, 11):
                col = f'lvl{i}_count'
                if col not in data:
                    data[col] = 0
            return data
        return None
    except Exception as e:
        print(f"Error in get_user_data: {e}")
        return None

def update_balance(telegram_id, new_balance):
    global db
    if db is None:
        initialize_firebase()
    if db is None:
        return
    try:
        user_ref = db.collection('users').document(str(telegram_id))
        user_ref.update({'balance': int(new_balance)})
        print(f"Successfully updated balance to {new_balance} for user {telegram_id}")
    except Exception as e:
        print(f"Error in update_balance: {e}")

def update_upgrade_level(telegram_id, lvl_column, new_level):
    global db
    if db is None:
        initialize_firebase()
    if db is None:
        return
    allowed_columns = [f"lvl{i}_count" for i in range(1, 11)]
    if lvl_column not in allowed_columns:
        return
    try:
        user_ref = db.collection('users').document(str(telegram_id))
        user_ref.update({lvl_column: int(new_level)})
        print(f"Successfully updated {lvl_column} to {new_level} for user {telegram_id}")
    except Exception as e:
        print(f"Error in update_upgrade_level: {e}")

def update_claim_time(telegram_id):
    global db
    if db is None:
        initialize_firebase()
    if db is None:
        return
    try:
        user_ref = db.collection('users').document(str(telegram_id))
        user_ref.update({'last_claim_time': datetime.utcnow().isoformat()})
    except Exception as e:
        print(f"Error in update_claim_time: {e}")
